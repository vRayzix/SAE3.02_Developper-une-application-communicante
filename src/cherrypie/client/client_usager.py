"""Client d'un usager : connexion au serveur, heartbeat, reconnexion et déplacement.

Chaque client tourne dans son propre thread, avec ses propres sockets. Il ne dépend
pas de Qt : il signale ce qui lui arrive par des fonctions de rappel, appelées depuis
son thread. L'IHM pourra les relier à des signaux Qt sans que le client touche jamais
un widget.
"""

from __future__ import annotations

import logging
import select
import socket
import threading
import time
from collections.abc import Callable
from enum import Enum

from cherrypie.client.deplacement import Deplacement
from cherrypie.commun.config import Configuration
from cherrypie.commun.erreurs import CherryPieError, InscriptionRefuseeError
from cherrypie.commun.protocole import CodeNotification, Enveloppe, Message, TypeMessage
from cherrypie.commun.securite import GardeAntiRejeu, Signataire
from cherrypie.commun.trame import DecoupeurTrames
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.usager import Usager

# Octets demandés à chaque lecture de la socket TCP.
TAILLE_LECTURE = 65536

journal = logging.getLogger(__name__)


class EtatConnexion(Enum):
    """État de la connexion d'un client, signalé à chaque changement."""

    CONNEXION = "connexion"
    CONNECTE = "connecte"
    DECONNECTE = "deconnecte"
    TERMINE = "termine"


class ClientUsager(threading.Thread):
    """Client d'un usager, dans son propre thread.

    Il se connecte au serveur, inscrit son usager (HELLO), envoie un PING toutes les
    intervalle_ping secondes et se reconnecte avec un délai qui double à chaque échec
    (backoff, plafonné à backoff_max) quand la connexion tombe ou que l'inscription est
    refusée pour l'instant. Il dit au revoir (BYE) quand on l'arrête.

    Les fonctions de rappel sont appelées depuis le thread du client : elles ne doivent
    jamais toucher un widget directement.
    """

    def __init__(
        self,
        config: Configuration,
        usager: Usager,
        sur_connexion: Callable[[EtatConnexion, str], None] | None = None,
    ) -> None:
        """Prépare le client ; la connexion ne s'ouvre qu'au lancement du thread.

        Args:
            config (Configuration): configuration partagée avec le serveur.
            usager (Usager): usager que le client fait circuler.
            sur_connexion (Callable[[EtatConnexion, str], None] | None): appelée à chaque
                changement d'état de la connexion, avec un détail lisible.

        Raises:
            BrancheInconnueError: si l'entrée ou la sortie de l'usager n'existe pas dans la configuration.
        """
        super().__init__(name=f"client-{usager.identifiant}", daemon=True)
        self.__config = config
        self.__deplacement = Deplacement(usager, usager.calculer_trajectoire(RondPoint.depuis_config(config)))
        self.__signataire = Signataire(config.cle_hmac)
        self.__garde = GardeAntiRejeu(config.fenetre_anti_rejeu)
        self.__arret = threading.Event()
        self.__socket_tcp: socket.socket | None = None
        self.__decoupeur = DecoupeurTrames()
        self.__etat = EtatConnexion.DECONNECTE
        self.__sur_connexion = sur_connexion

    @property
    def config(self) -> Configuration:
        """Configuration: configuration du client."""
        return self.__config

    @property
    def usager(self) -> Usager:
        """Usager: usager que le client fait circuler."""
        return self.__deplacement.usager

    @property
    def deplacement(self) -> Deplacement:
        """Deplacement: avancée de l'usager sur sa trajectoire."""
        return self.__deplacement

    @property
    def signataire(self) -> Signataire:
        """Signataire: signe les messages envoyés et vérifie ceux reçus."""
        return self.__signataire

    @property
    def garde(self) -> GardeAntiRejeu:
        """GardeAntiRejeu: refuse les trames du serveur trop anciennes ou déjà reçues."""
        return self.__garde

    @property
    def arret_demande(self) -> bool:
        """bool: True dès que arreter() a été appelée."""
        return self.__arret.is_set()

    @property
    def socket_tcp(self) -> socket.socket | None:
        """socket.socket | None: connexion TCP en cours, None entre deux connexions."""
        return self.__socket_tcp

    @property
    def decoupeur(self) -> DecoupeurTrames:
        """DecoupeurTrames: tampon des octets reçus sur la connexion en cours."""
        return self.__decoupeur

    @property
    def etat(self) -> EtatConnexion:
        """EtatConnexion: dernier état de la connexion."""
        return self.__etat

    @property
    def sur_connexion(self) -> Callable[[EtatConnexion, str], None] | None:
        """Callable | None: fonction appelée à chaque changement d'état de la connexion."""
        return self.__sur_connexion

    def arreter(self) -> None:
        """Demande l'arrêt du client, qui dit au revoir au serveur s'il est connecté.

        Peut être appelée depuis n'importe quel thread.
        """
        self.__arret.set()

    def run(self) -> None:
        """Corps du thread : connexions successives, jusqu'à l'arrêt."""
        raison = "arrêt demandé"
        try:
            raison = self.__rouler()
        except Exception:
            # Frontière du thread : une erreur imprévue est journalisée, jamais propagée.
            journal.exception("erreur inattendue dans le client %s", self.usager.identifiant)
            raison = "erreur inattendue"
        finally:
            self.__fermer_connexion()
            self.__changer_etat(EtatConnexion.TERMINE, raison)

    def __rouler(self) -> str:
        """Enchaîne les connexions et les attentes de backoff ; renvoie la raison de l'arrêt."""
        delai = self.__config.backoff_initial
        while not self.__arret.is_set():
            try:
                self.__connecter()
            except InscriptionRefuseeError as refus:
                if not refus.reessayer:
                    return f"inscription refusée : {refus}"
                self.__changer_etat(EtatConnexion.DECONNECTE, f"inscription refusée pour l'instant : {refus}")
            except (OSError, CherryPieError) as erreur:
                self.__changer_etat(EtatConnexion.DECONNECTE, f"connexion impossible : {erreur}")
            else:
                delai = self.__config.backoff_initial
                try:
                    self.__circuler()
                except (OSError, CherryPieError) as erreur:
                    self.__changer_etat(EtatConnexion.DECONNECTE, f"connexion perdue : {erreur}")
            finally:
                self.__fermer_connexion()
            # Attente interruptible : arreter() réveille le client sans attendre la fin du délai.
            if self.__arret.wait(delai):
                break
            delai = min(2 * delai, self.__config.backoff_max)
        return "arrêt demandé"

    def __connecter(self) -> None:
        """Ouvre la connexion TCP et inscrit l'usager auprès du serveur.

        Raises:
            OSError: si le serveur est injoignable, ne répond pas ou coupe la connexion.
            InscriptionRefuseeError: si le serveur refuse l'usager.
        """
        hote, port = self.__config.hote, self.__config.port_tcp
        self.__changer_etat(EtatConnexion.CONNEXION, f"vers {hote}:{port}")
        self.__socket_tcp = socket.create_connection((hote, port), timeout=self.__config.timeout_client)
        # Chaque connexion repart d'un tampon vide : un reste de l'ancienne n'aurait plus de sens.
        self.__decoupeur = DecoupeurTrames()
        usager = self.usager
        description = {"categorie": usager.CATEGORIE, "entree": usager.branche_entree, "sortie": usager.branche_sortie}
        self.__envoyer(Message(TypeMessage.HELLO, usager.identifiant, description))
        accuse = self.__attendre(TypeMessage.HELLO_ACK)
        if accuse.donnees.get("accepte") is not True:
            raison = str(accuse.donnees.get("raison", "sans raison"))
            raise InscriptionRefuseeError(raison, accuse.donnees.get("reessayer") is True)
        # Une nouvelle session repart sans consigne : le serveur renverra celles qui valent encore.
        usager.reagir(CodeNotification.OK_PASSER)
        self.__changer_etat(EtatConnexion.CONNECTE, "inscrit auprès du serveur")

    def __circuler(self) -> None:
        """Envoie les PING et lit les messages du serveur tant que la connexion tient.

        Revient après avoir dit au revoir (BYE) quand l'arrêt est demandé.

        Raises:
            OSError: si la connexion est coupée ou si le serveur ne donne plus de nouvelles.
            TrameInvalideError: si le flux du serveur devient illisible.
        """
        prochain_ping = time.monotonic() + self.__config.intervalle_ping
        derniere_nouvelle = time.monotonic()
        while not self.__arret.is_set():
            maintenant = time.monotonic()
            if maintenant >= prochain_ping:
                prochain_ping = maintenant + self.__config.intervalle_ping
                self.__envoyer(Message(TypeMessage.PING, self.usager.identifiant))
            # Le serveur répond à chaque PING : un silence plus long que le timeout veut
            # dire qu'il est tombé, même si la connexion TCP n'a pas encore cassé.
            if maintenant - derniere_nouvelle > self.__config.timeout_client:
                raise TimeoutError(f"aucune nouvelle du serveur depuis plus de {self.__config.timeout_client:g} s")
            # La boucle se réveille au moins à chaque intervalle de position, pour rester réactive.
            prochain_reveil = min(prochain_ping, maintenant + self.__config.intervalle_position)
            if self.__lire(max(0.0, prochain_reveil - time.monotonic())):
                derniere_nouvelle = time.monotonic()
        self.__envoyer(Message(TypeMessage.BYE, self.usager.identifiant))

    def __attendre(self, type_attendu: TypeMessage) -> Message:
        """Attend un message d'un type donné, au plus timeout_client secondes, en ignorant les autres.

        Raises:
            TimeoutError: si le message n'arrive pas à temps.
            ConnectionError: si le serveur ferme la connexion.
        """
        limite = time.monotonic() + self.__config.timeout_client
        while time.monotonic() < limite:
            for message in self.__lire(max(0.0, limite - time.monotonic())):
                if message.type is type_attendu:
                    return message
        raise TimeoutError(f"pas de {type_attendu.value} du serveur à temps")

    def __lire(self, attente: float) -> list[Message]:
        """Attend des données du serveur, au plus `attente` secondes, et renvoie les messages valides.

        Une trame refusée (JSON, HMAC, rejeu) est journalisée puis ignorée.

        Raises:
            ConnectionError: si le serveur a fermé ou coupé la connexion.
            TrameInvalideError: si le flux annonce une trame démesurée.
        """
        lisibles, _, _ = select.select([self.__socket_tcp], [], [], attente)
        if not lisibles:
            return []
        octets = self.__socket_tcp.recv(TAILLE_LECTURE)
        if not octets:
            raise ConnectionError("connexion fermée par le serveur")
        messages = []
        for trame in self.__decoupeur.ajouter(octets):
            try:
                messages.append(self.__ouvrir(trame))
            except CherryPieError as erreur:
                journal.warning("trame du serveur refusée par %s : %s", self.usager.identifiant, erreur)
        return messages

    def __ouvrir(self, octets: bytes) -> Message:
        """Lit une enveloppe reçue, vérifie son HMAC puis sa fraîcheur, et renvoie son message."""
        enveloppe = Enveloppe.depuis_octets(octets)
        self.__signataire.verifier(enveloppe)
        self.__garde.controler(enveloppe, time.time())
        return enveloppe.message

    def __envoyer(self, message: Message) -> None:
        """Signe un message et l'envoie au serveur sur la connexion TCP.

        Raises:
            OSError: si la connexion est coupée (BrokenPipeError, ConnectionResetError) ou bloquée (TimeoutError).
        """
        self.__socket_tcp.sendall(DecoupeurTrames.encoder(self.__signataire.signer(message).vers_octets()))

    def __fermer_connexion(self) -> None:
        """Ferme la connexion TCP en cours, s'il y en a une."""
        if self.__socket_tcp is not None:
            self.__socket_tcp.close()
            self.__socket_tcp = None

    def __changer_etat(self, etat: EtatConnexion, detail: str) -> None:
        """Note le nouvel état de la connexion et le signale."""
        self.__etat = etat
        journal.info("client %s : %s (%s)", self.usager.identifiant, etat.value, detail)
        self.__appeler(self.__sur_connexion, etat, detail)

    def __appeler(self, rappel: Callable[..., None] | None, *arguments: object) -> None:
        """Appelle une fonction de rappel sans qu'une erreur de sa part arrête le client."""
        if rappel is None:
            return
        try:
            rappel(*arguments)
        except Exception:
            journal.exception("erreur dans une fonction de rappel du client %s", self.usager.identifiant)
