"""Réseau de la supervision : abonnement aux STATE, heartbeat et réglage de la régulation.

Le travailleur tourne dans un QThread et ne touche aucun widget : il transmet ce qu'il
reçoit par des signaux Qt, que l'IHM traite dans son propre thread.
"""

from __future__ import annotations

import logging
import queue
import select
import socket
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from cherrypie.client.client_usager import TAILLE_LECTURE, EtatConnexion
from cherrypie.commun.config import Configuration
from cherrypie.commun.erreurs import CherryPieError
from cherrypie.commun.protocole import Enveloppe, Message, TypeMessage
from cherrypie.commun.securite import GardeAntiRejeu, Signataire
from cherrypie.commun.trame import DecoupeurTrames

IDENTIFIANT_SUPERVISION = "supervision"
# Attente maximale de la boucle : un réglage demandé par l'IHM, ou l'arrêt, part dans ce délai.
ATTENTE_MAX = 0.1
CLES_ETAT = frozenset({"usagers", "densite", "vp_actif", "segments_reserves", "entrees_bloquees", "regulation"})

journal = logging.getLogger(__name__)


class ReseauSupervision(QObject):
    """Connexion de la supervision au serveur, à faire tourner dans un QThread.

    tourner() se connecte et s'abonne aux STATE (ABONNEMENT). Elle envoie ensuite un PING
    toutes les intervalle_ping secondes, sans quoi le serveur retirerait la supervision,
    et transmet chaque STATE reçu par le signal etat_recu. Si la connexion tombe, elle
    réessaie avec le même backoff que les clients. arreter() et demander_reglage() sont
    appelées depuis le thread de l'IHM : la boucle les prend en compte en moins de
    ATTENTE_MAX secondes.

    Signals:
        etat_recu (dict): données d'un STATE reçu du serveur.
        connexion_changee (str, str): nouvel état de la connexion (valeur de EtatConnexion) et détail.
        termine (): émis quand tourner() a fini, après la fermeture de la connexion.
    """

    etat_recu = pyqtSignal(dict)
    connexion_changee = pyqtSignal(str, str)
    termine = pyqtSignal()

    def __init__(self, config: Configuration) -> None:
        """Prépare le travailleur ; la connexion ne s'ouvre qu'à l'appel de tourner().

        Args:
            config (Configuration): configuration partagée avec le serveur.
        """
        super().__init__()
        self.__config = config
        self.__signataire = Signataire(config.cle_hmac)
        self.__garde = GardeAntiRejeu(config.fenetre_anti_rejeu)
        self.__arret = threading.Event()
        self.__reglages: queue.SimpleQueue[bool] = queue.SimpleQueue()
        self.__socket: socket.socket | None = None
        self.__decoupeur = DecoupeurTrames()
        self.__etat = EtatConnexion.DECONNECTE

    @property
    def config(self) -> Configuration:
        """Configuration: configuration de la supervision."""
        return self.__config

    @property
    def etat(self) -> EtatConnexion:
        """EtatConnexion: dernier état de la connexion."""
        return self.__etat

    @property
    def arret_demande(self) -> bool:
        """bool: True dès que arreter() a été appelée."""
        return self.__arret.is_set()

    def demander_reglage(self, regulation: bool) -> None:
        """Demande au serveur d'activer ou de couper la régulation (message REGLAGE).

        Peut être appelée depuis le thread de l'IHM. Un réglage demandé hors connexion
        est abandonné à la connexion suivante : l'IHM reprend alors l'état du serveur.

        Args:
            regulation (bool): True pour activer la régulation, False pour la couper.
        """
        self.__reglages.put(regulation)

    def arreter(self) -> None:
        """Demande l'arrêt du travailleur, qui se désabonne (BYE) s'il est connecté.

        Peut être appelée depuis n'importe quel thread.
        """
        self.__arret.set()

    @pyqtSlot()
    def tourner(self) -> None:
        """Corps du travailleur : connexions successives jusqu'à l'arrêt ; à relier au signal started du QThread."""
        raison = "arrêt demandé"
        try:
            self.__boucler()
        except Exception:
            # Frontière du thread : une erreur imprévue est journalisée, jamais propagée.
            journal.exception("erreur inattendue dans le réseau de la supervision")
            raison = "erreur inattendue"
        finally:
            self.__fermer()
            self.__changer_etat(EtatConnexion.TERMINE, raison)
            self.termine.emit()

    def __boucler(self) -> None:
        """Enchaîne les connexions et les attentes de backoff jusqu'à l'arrêt."""
        delai = self.__config.backoff_initial
        while not self.__arret.is_set():
            try:
                self.__connecter()
            except OSError as erreur:
                self.__changer_etat(EtatConnexion.DECONNECTE, f"connexion impossible : {erreur}")
            else:
                delai = self.__config.backoff_initial
                try:
                    self.__ecouter()
                except (OSError, CherryPieError) as erreur:
                    self.__changer_etat(EtatConnexion.DECONNECTE, f"connexion perdue : {erreur}")
            finally:
                self.__fermer()
            # Attente interruptible : arreter() réveille le travailleur sans attendre la fin du délai.
            if self.__arret.wait(delai):
                break
            delai = min(2 * delai, self.__config.backoff_max)

    def __connecter(self) -> None:
        """Ouvre la connexion TCP et abonne la supervision aux STATE.

        Raises:
            OSError: si le serveur est injoignable ou coupe la connexion.
        """
        hote, port = self.__config.hote, self.__config.port_tcp
        self.__changer_etat(EtatConnexion.CONNEXION, f"vers {hote}:{port}")
        self.__socket = socket.create_connection((hote, port), timeout=self.__config.timeout_client)
        self.__decoupeur = DecoupeurTrames()
        self.__abandonner_reglages()
        self.__envoyer(Message(TypeMessage.ABONNEMENT, IDENTIFIANT_SUPERVISION))
        self.__changer_etat(EtatConnexion.CONNECTE, "abonnée aux STATE")

    def __ecouter(self) -> None:
        """Envoie réglages et PING, et lit les STATE tant que la connexion tient ; se désabonne à l'arrêt.

        Raises:
            OSError: si la connexion est coupée ou si le serveur ne donne plus de nouvelles.
            TrameInvalideError: si le flux du serveur devient illisible.
        """
        prochain_ping = time.monotonic() + self.__config.intervalle_ping
        derniere_nouvelle = time.monotonic()
        while not self.__arret.is_set():
            self.__envoyer_reglages()
            maintenant = time.monotonic()
            if maintenant >= prochain_ping:
                prochain_ping = maintenant + self.__config.intervalle_ping
                self.__envoyer(Message(TypeMessage.PING, IDENTIFIANT_SUPERVISION))
            # Le serveur répond aux PING et diffuse des STATE : un long silence veut dire
            # qu'il est tombé, même si la connexion TCP n'a pas encore cassé.
            if maintenant - derniere_nouvelle > self.__config.timeout_client:
                raise TimeoutError(f"aucune nouvelle du serveur depuis plus de {self.__config.timeout_client:g} s")
            if self.__lire(min(ATTENTE_MAX, max(0.0, prochain_ping - maintenant))):
                derniere_nouvelle = time.monotonic()
        self.__envoyer(Message(TypeMessage.BYE, IDENTIFIANT_SUPERVISION))

    def __lire(self, attente: float) -> bool:
        """Attend des données du serveur, au plus `attente` secondes, et transmet les STATE valides.

        Une trame refusée (JSON, HMAC, rejeu) est journalisée puis ignorée.

        Returns:
            bool: True si au moins un message valide est arrivé.

        Raises:
            ConnectionError: si le serveur a fermé ou coupé la connexion.
            TrameInvalideError: si le flux annonce une trame démesurée.
        """
        lisibles, _, _ = select.select([self.__socket], [], [], attente)
        if not lisibles:
            return False
        octets = self.__socket.recv(TAILLE_LECTURE)
        if not octets:
            raise ConnectionError("connexion fermée par le serveur")
        nouvelles = False
        for trame in self.__decoupeur.ajouter(octets):
            try:
                message = self.__ouvrir(trame)
            except CherryPieError as erreur:
                journal.warning("trame du serveur refusée par la supervision : %s", erreur)
                continue
            nouvelles = True
            if message.type is TypeMessage.STATE:
                self.__transmettre_etat(message)
        return nouvelles

    def __transmettre_etat(self, message: Message) -> None:
        """Transmet un STATE à l'IHM ; un STATE incomplet est ignoré pour ne pas la faire échouer."""
        manquantes = CLES_ETAT - message.donnees.keys()
        if manquantes:
            journal.warning("STATE ignoré, il manque : %s", ", ".join(sorted(manquantes)))
            return
        self.etat_recu.emit(message.donnees)

    def __ouvrir(self, octets: bytes) -> Message:
        """Lit une enveloppe reçue, vérifie son HMAC puis sa fraîcheur, et renvoie son message."""
        enveloppe = Enveloppe.depuis_octets(octets)
        self.__signataire.verifier(enveloppe)
        self.__garde.controler(enveloppe, time.time())
        return enveloppe.message

    def __envoyer_reglages(self) -> None:
        """Envoie au serveur les réglages demandés par l'IHM depuis le dernier tour."""
        while True:
            try:
                regulation = self.__reglages.get_nowait()
            except queue.Empty:
                return
            self.__envoyer(Message(TypeMessage.REGLAGE, IDENTIFIANT_SUPERVISION, {"regulation": regulation}))
            journal.info("régulation %s demandée au serveur", "active" if regulation else "inactive")

    def __abandonner_reglages(self) -> None:
        """Vide les réglages demandés avant la connexion : ils portaient sur un état du serveur périmé."""
        while True:
            try:
                self.__reglages.get_nowait()
            except queue.Empty:
                return

    def __envoyer(self, message: Message) -> None:
        """Signe un message et l'envoie au serveur.

        Raises:
            OSError: si la connexion est coupée (BrokenPipeError, ConnectionResetError) ou bloquée (TimeoutError).
        """
        self.__socket.sendall(DecoupeurTrames.encoder(self.__signataire.signer(message).vers_octets()))

    def __fermer(self) -> None:
        """Ferme la connexion en cours, s'il y en a une."""
        if self.__socket is not None:
            self.__socket.close()
            self.__socket = None

    def __changer_etat(self, etat: EtatConnexion, detail: str) -> None:
        """Note le nouvel état de la connexion et le signale à l'IHM."""
        self.__etat = etat
        journal.info("supervision : %s (%s)", etat.value, detail)
        self.connexion_changee.emit(etat.value, detail)
