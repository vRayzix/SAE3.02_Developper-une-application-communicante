"""Tests du serveur sur 127.0.0.1 : de vrais clients face à la boucle select."""

import logging
import socket
import struct
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator

import pytest
from outils import DELAI, attendre

from cherrypie.commun.config import Configuration
from cherrypie.commun.protocole import Enveloppe, Message, TypeMessage
from cherrypie.commun.securite import Signataire
from cherrypie.commun.trame import TAILLE_MAX_TRAME, DecoupeurTrames
from cherrypie.serveur.serveur import Serveur

HELLO_VOITURE = {"categorie": "voiture", "entree": "N", "sortie": "E"}


class ClientTest:
    """Client minimal qui parle le protocole, pour piloter le serveur depuis un test."""

    def __init__(self, config: Configuration, identifiant: str) -> None:
        self.__config = config
        self.__identifiant = identifiant
        self.__signataire = Signataire(config.cle_hmac)
        self.__decoupeur = DecoupeurTrames()
        self.__recus: deque[Message] = deque()
        self.__historique: list[Message] = []
        self.__socket = socket.create_connection((config.hote, config.port_tcp), timeout=DELAI)

    @property
    def config(self) -> Configuration:
        return self.__config

    @property
    def identifiant(self) -> str:
        return self.__identifiant

    @property
    def signataire(self) -> Signataire:
        return self.__signataire

    @property
    def decoupeur(self) -> DecoupeurTrames:
        return self.__decoupeur

    @property
    def recus(self) -> list[Message]:
        return list(self.__recus)

    @property
    def historique(self) -> list[Message]:
        """list[Message]: tous les messages reçus depuis la connexion, y compris ceux sautés."""
        return list(self.__historique)

    @property
    def socket(self) -> socket.socket:
        return self.__socket

    def trame(self, type_message: TypeMessage, donnees: dict | None = None) -> bytes:
        """Construit une trame signée, prête à être envoyée ou rejouée."""
        enveloppe = self.__signataire.signer(Message(type_message, self.__identifiant, donnees))
        return DecoupeurTrames.encoder(enveloppe.vers_octets())

    def envoyer(self, type_message: TypeMessage, donnees: dict | None = None) -> None:
        self.__socket.sendall(self.trame(type_message, donnees))

    def envoyer_octets(self, octets: bytes) -> None:
        self.__socket.sendall(octets)

    def envoyer_position(self, x: float, y: float, segment: str | None = None) -> None:
        """Envoie un POS signé en UDP."""
        etape = "approche" if segment is None else "anneau"
        donnees = {"x": x, "y": y, "vitesse": 5.0, "segment": segment, "etape": etape}
        enveloppe = self.__signataire.signer(Message(TypeMessage.POS, self.__identifiant, donnees))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.sendto(enveloppe.vers_octets(), (self.__config.hote, self.__config.port_udp))

    def recevoir(self, type_attendu: TypeMessage) -> Message:
        """Renvoie le prochain message du type attendu, en sautant les autres (STATE, PONG...)."""
        limite = time.monotonic() + DELAI
        while time.monotonic() < limite:
            while self.__recus:
                message = self.__recus.popleft()
                if message.type is type_attendu:
                    return message
            self.__lire()
        raise AssertionError(f"aucun {type_attendu.value} reçu en {DELAI} s")

    def attendre_etat(self, condition: Callable[[dict], bool]) -> dict:
        """Lit les STATE jusqu'au premier qui remplit la condition.

        Un PING part avant chaque lecture, pour que la session ne soit pas retirée pendant l'attente.
        """
        limite = time.monotonic() + DELAI
        while time.monotonic() < limite:
            self.envoyer(TypeMessage.PING)
            etat = self.recevoir(TypeMessage.STATE).donnees
            if condition(etat):
                return etat
        raise AssertionError("aucun STATE ne remplit la condition")

    def attendre_fermeture(self) -> None:
        """Attend que le serveur ferme la connexion, en ignorant ce qu'il envoie d'ici là."""
        limite = time.monotonic() + DELAI
        while time.monotonic() < limite:
            try:
                if not self.__socket.recv(65536):
                    return
            except ConnectionResetError:
                return
        raise AssertionError("le serveur n'a pas fermé la connexion")

    def couper_brutalement(self) -> None:
        """Ferme la socket en envoyant un RST, comme un client qui plante."""
        self.__socket.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        self.__socket.close()

    def fermer(self) -> None:
        self.__socket.close()

    def __lire(self) -> None:
        """Lit la socket et range les messages reçus, après vérification de leur signature."""
        octets = self.__socket.recv(65536)
        if not octets:
            raise ConnectionError("connexion fermée par le serveur")
        for trame in self.__decoupeur.ajouter(octets):
            enveloppe = Enveloppe.depuis_octets(trame)
            self.__signataire.verifier(enveloppe)
            self.__recus.append(enveloppe.message)
            self.__historique.append(enveloppe.message)


@pytest.fixture
def serveur(lancer_serveur: Callable[..., Serveur]) -> Serveur:
    return lancer_serveur()


@pytest.fixture
def clients(serveur: Serveur) -> Iterator[Callable[[str], ClientTest]]:
    """Ouvre des clients connectés au serveur, puis les ferme à la fin du test."""
    ouverts: list[ClientTest] = []

    def ouvrir(identifiant: str) -> ClientTest:
        client = ClientTest(serveur.config, identifiant)
        ouverts.append(client)
        return client

    yield ouvrir
    for client in ouverts:
        client.fermer()


def voiture_inscrite(clients: Callable[[str], ClientTest], identifiant: str = "voiture_12") -> ClientTest:
    client = clients(identifiant)
    client.envoyer(TypeMessage.HELLO, HELLO_VOITURE)
    assert client.recevoir(TypeMessage.HELLO_ACK).donnees == {"accepte": True}
    return client


def supervision_abonnee(clients: Callable[[str], ClientTest]) -> ClientTest:
    supervision = clients("supervision")
    supervision.envoyer(TypeMessage.ABONNEMENT)
    return supervision


def identifiants(etat: dict) -> list[str]:
    return [usager["id"] for usager in etat["usagers"]]


# ---------- Inscription et PING ----------

def test_hello_accepte_et_usager_inscrit(serveur: Serveur, clients: Callable[[str], ClientTest]) -> None:
    voiture_inscrite(clients)
    assert serveur.logique.registre.contient("voiture_12")


def test_ping_recoit_pong(clients: Callable[[str], ClientTest]) -> None:
    client = voiture_inscrite(clients)
    client.envoyer(TypeMessage.PING)
    assert client.recevoir(TypeMessage.PONG).emetteur == "serveur"


def test_identifiant_deja_connecte_refuse(clients: Callable[[str], ClientTest]) -> None:
    voiture_inscrite(clients, "voiture_12")
    intrus = clients("voiture_12")
    intrus.envoyer(TypeMessage.HELLO, HELLO_VOITURE)
    assert intrus.recevoir(TypeMessage.HELLO_ACK).donnees["accepte"] is False


def test_plusieurs_clients_servis_par_la_meme_boucle(clients: Callable[[str], ClientTest]) -> None:
    premier = voiture_inscrite(clients, "voiture_1")
    second = voiture_inscrite(clients, "voiture_2")
    premier.envoyer(TypeMessage.PING)
    second.envoyer(TypeMessage.PING)
    assert second.recevoir(TypeMessage.PONG)
    assert premier.recevoir(TypeMessage.PONG)


# ---------- Lectures partielles et multiples ----------

def test_hello_recu_en_deux_morceaux(clients: Callable[[str], ClientTest]) -> None:
    client = clients("voiture_12")
    trame = client.trame(TypeMessage.HELLO, HELLO_VOITURE)
    client.envoyer_octets(trame[:10])
    # Laisse au serveur le temps de lire le premier morceau seul.
    time.sleep(0.1)
    client.envoyer_octets(trame[10:])
    assert client.recevoir(TypeMessage.HELLO_ACK).donnees == {"accepte": True}


def test_plusieurs_trames_d_un_seul_envoi(clients: Callable[[str], ClientTest]) -> None:
    client = clients("voiture_12")
    client.envoyer_octets(client.trame(TypeMessage.HELLO, HELLO_VOITURE) + client.trame(TypeMessage.PING))
    assert client.recevoir(TypeMessage.HELLO_ACK).donnees == {"accepte": True}
    assert client.recevoir(TypeMessage.PONG)


# ---------- Trames invalides ----------

def test_trame_illisible_journalisee_puis_ignoree(
    clients: Callable[[str], ClientTest], caplog: pytest.LogCaptureFixture
) -> None:
    client = voiture_inscrite(clients)
    client.envoyer_octets(DecoupeurTrames.encoder(b"pas du json"))
    client.envoyer(TypeMessage.PING)
    assert client.recevoir(TypeMessage.PONG)
    assert "JSON invalide" in caplog.text


def test_trame_mal_signee_ignoree(clients: Callable[[str], ClientTest], caplog: pytest.LogCaptureFixture) -> None:
    client = voiture_inscrite(clients)
    fausse = Signataire(b"une_autre_cle").signer(Message(TypeMessage.PING, "voiture_12"))
    client.envoyer_octets(DecoupeurTrames.encoder(fausse.vers_octets()))
    client.envoyer(TypeMessage.PING)
    assert client.recevoir(TypeMessage.PONG)
    assert "HMAC invalide" in caplog.text


def test_trame_rejouee_ignoree(clients: Callable[[str], ClientTest], caplog: pytest.LogCaptureFixture) -> None:
    client = voiture_inscrite(clients)
    ping = client.trame(TypeMessage.PING)
    client.envoyer_octets(ping)
    assert client.recevoir(TypeMessage.PONG)
    client.envoyer_octets(ping)
    client.envoyer(TypeMessage.PING)
    assert client.recevoir(TypeMessage.PONG)
    assert "déjà reçu" in caplog.text


def test_longueur_aberrante_ferme_la_seule_session_fautive(
    serveur: Serveur, clients: Callable[[str], ClientTest]
) -> None:
    fautif = voiture_inscrite(clients, "voiture_1")
    fautif.envoyer_octets(struct.pack("!I", TAILLE_MAX_TRAME + 1))
    fautif.attendre_fermeture()
    attendre(lambda: not serveur.logique.registre.contient("voiture_1"))
    voiture_inscrite(clients, "voiture_2")


# ---------- Fin de session ----------

def test_bye_ferme_la_session_et_libere_l_identifiant(
    serveur: Serveur, clients: Callable[[str], ClientTest]
) -> None:
    client = voiture_inscrite(clients)
    client.envoyer(TypeMessage.BYE)
    client.attendre_fermeture()
    attendre(lambda: not serveur.logique.registre.contient("voiture_12"))
    voiture_inscrite(clients, "voiture_12")


def test_deconnexion_brutale_retire_l_usager(serveur: Serveur, clients: Callable[[str], ClientTest]) -> None:
    client = voiture_inscrite(clients)
    client.couper_brutalement()
    attendre(lambda: not serveur.logique.registre.contient("voiture_12"))


# ---------- Positions en UDP ----------

def test_position_d_un_usager_inscrit_prise_en_compte(
    serveur: Serveur, clients: Callable[[str], ClientTest]
) -> None:
    client = voiture_inscrite(clients)
    client.envoyer_position(3.5, -20.0, segment="S-E")
    attendre(lambda: serveur.logique.registre.obtenir("voiture_12").position is not None)
    assert serveur.logique.registre.obtenir("voiture_12").segment == "S-E"


def test_position_sans_session_tcp_ignoree(
    serveur: Serveur, clients: Callable[[str], ClientTest], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    anonyme = clients("voiture_99")
    anonyme.envoyer_position(3.5, -20.0)
    attendre(lambda: "voiture_99" in caplog.text)
    assert not serveur.logique.registre.contient("voiture_99")


def test_datagramme_illisible_ignore(
    serveur: Serveur, clients: Callable[[str], ClientTest], caplog: pytest.LogCaptureFixture
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.sendto(b"\x00\xff", (serveur.config.hote, serveur.config.port_udp))
    attendre(lambda: "datagramme refusé" in caplog.text)
    voiture_inscrite(clients)


# ---------- Arrêt ----------

def test_arret_propre_de_la_boucle(fabrique_config: Callable[..., Configuration]) -> None:
    serveur = Serveur(fabrique_config(intervalle_etat="0.05"))
    serveur.demarrer()
    fil = threading.Thread(target=serveur.servir)
    fil.start()
    client = ClientTest(serveur.config, "voiture_12")
    serveur.arreter()
    fil.join(timeout=DELAI)
    assert not fil.is_alive()
    client.attendre_fermeture()
    with pytest.raises(ConnectionRefusedError):
        socket.create_connection((serveur.config.hote, serveur.config.port_tcp), timeout=DELAI)


# ---------- Diffusion des STATE ----------

def test_supervision_recoit_les_usagers_connectes(clients: Callable[[str], ClientTest]) -> None:
    voiture_inscrite(clients, "voiture_12")
    supervision = supervision_abonnee(clients)
    etat = supervision.attendre_etat(lambda etat: identifiants(etat) == ["voiture_12"])
    assert etat["usagers"][0]["categorie"] == "voiture"


def test_state_suit_les_positions_recues(clients: Callable[[str], ClientTest]) -> None:
    voiture = voiture_inscrite(clients)
    supervision = supervision_abonnee(clients)
    voiture.envoyer_position(3.5, -20.0, segment="S-E")
    etat = supervision.attendre_etat(lambda etat: etat["usagers"][0]["x"] == 3.5)
    assert etat["usagers"][0]["segment"] == "S-E"


def test_usager_parti_disparait_du_state(clients: Callable[[str], ClientTest]) -> None:
    voiture = voiture_inscrite(clients)
    supervision = supervision_abonnee(clients)
    supervision.attendre_etat(lambda etat: identifiants(etat) == ["voiture_12"])
    voiture.envoyer(TypeMessage.BYE)
    supervision.attendre_etat(lambda etat: etat["usagers"] == [])


def test_usager_ne_recoit_pas_les_state(clients: Callable[[str], ClientTest]) -> None:
    voiture = voiture_inscrite(clients)
    supervision = supervision_abonnee(clients)
    supervision.recevoir(TypeMessage.STATE)
    supervision.recevoir(TypeMessage.STATE)
    voiture.envoyer(TypeMessage.PING)
    voiture.recevoir(TypeMessage.PONG)
    assert TypeMessage.STATE not in [message.type for message in voiture.historique]


# ---------- Heartbeat ----------

def test_client_silencieux_deconnecte_et_retire(lancer_serveur: Callable[..., Serveur]) -> None:
    serveur = lancer_serveur(intervalle_ping="0.1", timeout_client="0.3")
    client = ClientTest(serveur.config, "voiture_12")
    client.envoyer(TypeMessage.HELLO, HELLO_VOITURE)
    assert client.recevoir(TypeMessage.HELLO_ACK).donnees == {"accepte": True}
    client.attendre_fermeture()
    attendre(lambda: not serveur.logique.registre.contient("voiture_12"))
    client.fermer()


def test_client_qui_pingue_reste_connecte(lancer_serveur: Callable[..., Serveur]) -> None:
    serveur = lancer_serveur(intervalle_ping="0.1", timeout_client="0.3")
    client = ClientTest(serveur.config, "voiture_12")
    client.envoyer(TypeMessage.HELLO, HELLO_VOITURE)
    client.recevoir(TypeMessage.HELLO_ACK)
    # Huit PING espacés de 0,1 s : bien plus longtemps que le timeout de 0,3 s.
    for _ in range(8):
        client.envoyer(TypeMessage.PING)
        client.recevoir(TypeMessage.PONG)
        time.sleep(0.1)
    assert serveur.logique.registre.contient("voiture_12")
    client.fermer()
