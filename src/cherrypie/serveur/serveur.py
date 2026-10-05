"""Boucle réseau du serveur du rond-point.

Une seule boucle select surveille la socket d'écoute TCP, la socket UDP et les
sockets des clients. Elle ne prend aucune décision : elle lit les trames, vérifie
leur signature et leur fraîcheur, les confie à LogiqueServeur et envoie ce que
celle-ci renvoie. Le délai d'attente de select court jusqu'à la prochaine cadence,
qui rythme la diffusion des STATE et le contrôle des heartbeats : aucune attente active.
"""

from __future__ import annotations

import logging
import select
import socket
import threading
import time
from collections.abc import Callable

from cherrypie.commun.config import Configuration
from cherrypie.commun.erreurs import CherryPieError, TrameInvalideError, UsagerInconnuError
from cherrypie.commun.protocole import Enveloppe, Message
from cherrypie.commun.securite import GardeAntiRejeu, Signataire
from cherrypie.commun.trame import DecoupeurTrames
from cherrypie.modele.rond_point import RondPoint
from cherrypie.serveur.connexion import Connexion
from cherrypie.serveur.logique import LogiqueServeur

# Taille maximale d'un datagramme UDP.
TAILLE_MAX_DATAGRAMME = 65535

journal = logging.getLogger(__name__)


class Serveur:
    """Serveur du rond-point : sockets TCP et UDP, connexions des clients et boucle select."""

    def __init__(self, config: Configuration) -> None:
        """Prépare le serveur, sans ouvrir de socket.

        Args:
            config (Configuration): configuration chargée depuis config.ini.
        """
        self.__config = config
        self.__logique = LogiqueServeur(RondPoint.depuis_config(config), config.timeout_client)
        self.__signataire = Signataire(config.cle_hmac)
        self.__garde = GardeAntiRejeu(config.fenetre_anti_rejeu)
        self.__arret = threading.Event()
        self.__ecoute_tcp: socket.socket | None = None
        self.__socket_udp: socket.socket | None = None
        self.__connexions: dict[int, Connexion] = {}

    @property
    def config(self) -> Configuration:
        """Configuration: configuration du serveur."""
        return self.__config

    @property
    def logique(self) -> LogiqueServeur:
        """LogiqueServeur: décisions du serveur, sessions et registre des usagers."""
        return self.__logique

    @property
    def signataire(self) -> Signataire:
        """Signataire: signe les messages envoyés et vérifie ceux reçus."""
        return self.__signataire

    @property
    def garde(self) -> GardeAntiRejeu:
        """GardeAntiRejeu: refuse les trames trop anciennes ou déjà reçues."""
        return self.__garde

    @property
    def arret_demande(self) -> bool:
        """bool: True dès que arreter() a été appelée."""
        return self.__arret.is_set()

    @property
    def ecoute_tcp(self) -> socket.socket | None:
        """socket.socket | None: socket d'écoute TCP, None avant demarrer()."""
        return self.__ecoute_tcp

    @property
    def socket_udp(self) -> socket.socket | None:
        """socket.socket | None: socket qui reçoit les positions, None avant demarrer()."""
        return self.__socket_udp

    @property
    def connexions(self) -> dict[int, Connexion]:
        """dict[int, Connexion]: connexions ouvertes, par numéro de session (copie)."""
        return dict(self.__connexions)

    def demarrer(self) -> None:
        """Ouvre la socket d'écoute TCP et la socket UDP.

        Raises:
            OSError: si un port est déjà utilisé ou si l'adresse n'est pas valable.
        """
        hote = self.__config.hote
        ecoute_tcp = socket.create_server((hote, self.__config.port_tcp))
        socket_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            socket_udp.bind((hote, self.__config.port_udp))
        except OSError:
            # Sans UDP, le serveur ne recevrait aucune position : on libère aussi le port TCP.
            socket_udp.close()
            ecoute_tcp.close()
            raise
        ecoute_tcp.setblocking(False)
        socket_udp.setblocking(False)
        self.__ecoute_tcp = ecoute_tcp
        self.__socket_udp = socket_udp
        journal.info("à l'écoute sur %s : TCP %d, UDP %d", hote, self.__config.port_tcp, self.__config.port_udp)

    def servir(self) -> None:
        """Fait tourner la boucle jusqu'à l'appel de arreter(), puis ferme toutes les sockets.

        Raises:
            RuntimeError: si demarrer() n'a pas été appelée avant.
        """
        if self.__ecoute_tcp is None or self.__socket_udp is None:
            raise RuntimeError("le serveur doit être démarré avant de servir")
        prochaine_cadence = time.monotonic()
        try:
            while not self.__arret.is_set():
                try:
                    self.__attendre_et_traiter(max(0.0, prochaine_cadence - time.monotonic()))
                    if time.monotonic() >= prochaine_cadence:
                        # Échéance suivante fixée d'abord : une erreur dans la cadence ne doit
                        # pas la faire rejouer à chaque tour.
                        prochaine_cadence = time.monotonic() + self.__config.intervalle_etat
                        self.__cadencer()
                except Exception:
                    # Frontière : une erreur imprévue est journalisée, la boucle continue.
                    journal.exception("erreur inattendue dans la boucle du serveur")
        finally:
            self.__tout_fermer()

    def arreter(self) -> None:
        """Demande l'arrêt de la boucle, effectif au plus tard au bout d'un intervalle de STATE.

        Peut être appelée depuis un autre thread que celui de servir().
        """
        self.__arret.set()

    def __attendre_et_traiter(self, attente: float) -> None:
        """Attend qu'une socket soit prête, au plus `attente` secondes, et traite ce qui est arrivé."""
        numeros = {connexion.socket: numero for numero, connexion in self.__connexions.items()}
        a_lire = [self.__ecoute_tcp, self.__socket_udp, *numeros]
        a_ecrire = [connexion.socket for connexion in self.__connexions.values() if connexion.octets_en_attente]
        lisibles, inscriptibles, _ = select.select(a_lire, a_ecrire, [], attente)
        for prise in inscriptibles:
            self.__proteger(numeros[prise], self.__vider)
        for prise in lisibles:
            if prise is self.__ecoute_tcp:
                self.__accepter()
            elif prise is self.__socket_udp:
                self.__lire_udp()
            else:
                self.__proteger(numeros[prise], self.__lire_tcp)

    def __cadencer(self) -> None:
        """Retire les clients silencieux, puis envoie ce que la logique prévoit à chaque cadence."""
        for numero in self.__logique.sessions_expirees(time.monotonic()):
            self.__fermer(numero, f"aucune nouvelle depuis plus de {self.__config.timeout_client:g} s")
        for numero, message in self.__logique.cadencer():
            self.__envoyer(numero, message)

    def __proteger(self, numero: int, action: Callable[[int], None]) -> None:
        """Exécute une action sur une session sans qu'une erreur imprévue n'arrête le serveur."""
        try:
            action(numero)
        except Exception:
            # Frontière : un bug déclenché par un client ne doit coûter que sa propre session.
            journal.exception("erreur inattendue sur la session %d", numero)
            self.__fermer(numero, "erreur inattendue")

    def __accepter(self) -> None:
        """Accepte une nouvelle connexion TCP et lui ouvre une session."""
        try:
            prise, adresse = self.__ecoute_tcp.accept()
        except (BlockingIOError, ConnectionAbortedError):
            # Le client a pu renoncer entre le signal de select et l'appel à accept.
            return
        connexion = Connexion(prise, adresse)
        numero = self.__logique.ouvrir_session(time.monotonic())
        self.__connexions[numero] = connexion
        journal.info("session %d ouverte depuis %s:%d", numero, adresse[0], adresse[1])

    def __lire_tcp(self, numero: int) -> None:
        """Lit ce qui est arrivé sur une session et traite chaque trame complète."""
        connexion = self.__connexions.get(numero)
        if connexion is None:
            return
        try:
            trames = connexion.recevoir()
        except ConnectionResetError:
            self.__fermer(numero, "connexion coupée brutalement par le client")
            return
        except ConnectionError as erreur:
            self.__fermer(numero, str(erreur))
            return
        except TrameInvalideError as erreur:
            # Une longueur aberrante désynchronise le flux : impossible de retrouver la trame suivante.
            self.__fermer(numero, f"flux illisible : {erreur}")
            return
        for trame in trames:
            self.__traiter_trame(numero, trame)
            if numero not in self.__connexions:
                return

    def __traiter_trame(self, numero: int, trame: bytes) -> None:
        """Vérifie une trame TCP, la confie à la logique et envoie la réponse."""
        try:
            reponse = self.__logique.traiter_tcp(numero, self.__ouvrir(trame), time.monotonic())
        except CherryPieError as erreur:
            journal.warning("trame refusée sur la session %d : %s", numero, erreur)
            return
        for message in reponse.messages:
            self.__envoyer(numero, message)
        if reponse.fermer:
            self.__fermer(numero, "le client a dit au revoir (BYE)")

    def __lire_udp(self) -> None:
        """Lit un datagramme et transmet la position qu'il contient à la logique."""
        try:
            octets, adresse = self.__socket_udp.recvfrom(TAILLE_MAX_DATAGRAMME)
        except BlockingIOError:
            return
        try:
            self.__logique.traiter_udp(self.__ouvrir(octets), time.monotonic())
        except UsagerInconnuError as erreur:
            # Fréquent juste après la fermeture d'une session : ses derniers POS arrivent encore.
            journal.info("position ignorée : %s", erreur)
        except CherryPieError as erreur:
            journal.warning("datagramme refusé de %s:%d : %s", adresse[0], adresse[1], erreur)

    def __ouvrir(self, octets: bytes) -> Message:
        """Lit une enveloppe reçue, vérifie son HMAC puis sa fraîcheur, et renvoie son message.

        Raises:
            TrameInvalideError: si les octets ne forment pas une enveloppe valide.
            SignatureInvalideError: si le HMAC ne correspond pas.
            RejeuDetecteError: si l'enveloppe est trop ancienne ou déjà reçue.
        """
        enveloppe = Enveloppe.depuis_octets(octets)
        self.__signataire.verifier(enveloppe)
        self.__garde.controler(enveloppe, time.time())
        return enveloppe.message

    def __envoyer(self, numero: int, message: Message) -> None:
        """Signe un message et le met en file d'envoi sur une session."""
        connexion = self.__connexions.get(numero)
        if connexion is None:
            return
        trame = DecoupeurTrames.encoder(self.__signataire.signer(message).vers_octets())
        try:
            connexion.envoyer(trame)
        except BrokenPipeError:
            self.__fermer(numero, "client injoignable")
        except ConnectionError as erreur:
            self.__fermer(numero, f"envoi impossible : {erreur}")

    def __vider(self, numero: int) -> None:
        """Envoie ce qui attend dans la file d'une session, maintenant que sa socket peut écrire."""
        connexion = self.__connexions.get(numero)
        if connexion is None:
            return
        try:
            connexion.vider()
        except ConnectionError as erreur:
            self.__fermer(numero, f"envoi impossible : {erreur}")

    def __fermer(self, numero: int, raison: str) -> None:
        """Ferme la socket d'une session et retire son usager du registre."""
        connexion = self.__connexions.pop(numero, None)
        if connexion is None:
            return
        connexion.fermer()
        usager = self.__logique.fermer_session(numero)
        if usager is None:
            journal.info("session %d fermée : %s", numero, raison)
        else:
            journal.info("session %d fermée : %s ; usager %s retiré", numero, raison, usager.identifiant)

    def __tout_fermer(self) -> None:
        """Ferme toutes les sessions, puis les sockets d'écoute."""
        for numero in list(self.__connexions):
            self.__fermer(numero, "arrêt du serveur")
        self.__ecoute_tcp.close()
        self.__socket_udp.close()
        journal.info("serveur arrêté")
