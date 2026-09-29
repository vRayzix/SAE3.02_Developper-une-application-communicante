"""Tests de la connexion TCP côté serveur : lectures partielles, déconnexions et envoi différé."""

import select
import socket
import struct
import time

import pytest

from cherrypie.commun.trame import DecoupeurTrames
from cherrypie.serveur.connexion import TAILLE_MAX_EN_ATTENTE, Connexion

DELAI = 2.0
# Tampons système fixés (et modestes) : la file d'envoi se remplit vite, sans
# descendre sous la taille d'un segment TCP, ce qui ferait caler la transmission.
TAMPON_SYSTEME = 65536


@pytest.fixture
def paire() -> tuple[socket.socket, Connexion]:
    """Connexion TCP sur 127.0.0.1 : la socket du client et la Connexion côté serveur."""
    with socket.create_server(("127.0.0.1", 0)) as ecoute:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, TAMPON_SYSTEME)
        client.connect(ecoute.getsockname())
        prise, adresse = ecoute.accept()
    prise.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, TAMPON_SYSTEME)
    client.settimeout(DELAI)
    connexion = Connexion(prise, adresse)
    yield client, connexion
    client.close()
    connexion.fermer()


def attendre_lisible(connexion: Connexion) -> None:
    lisibles, _, _ = select.select([connexion.socket], [], [], DELAI)
    assert lisibles, "rien n'est arrivé dans le délai"


def couper_brutalement(client: socket.socket) -> None:
    """Ferme la socket en envoyant un RST, comme un client qui plante."""
    client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    client.close()


# ---------- Réception ----------

def test_trame_complete_recue(paire: tuple[socket.socket, Connexion]) -> None:
    client, connexion = paire
    client.sendall(DecoupeurTrames.encoder(b"bonjour"))
    attendre_lisible(connexion)
    assert connexion.recevoir() == [b"bonjour"]


def test_trame_en_deux_envois_rendue_au_second(paire: tuple[socket.socket, Connexion]) -> None:
    client, connexion = paire
    trame = DecoupeurTrames.encoder(b"bonjour")
    client.sendall(trame[:3])
    attendre_lisible(connexion)
    assert connexion.recevoir() == []
    client.sendall(trame[3:])
    attendre_lisible(connexion)
    assert connexion.recevoir() == [b"bonjour"]


def test_plusieurs_trames_d_un_seul_envoi(paire: tuple[socket.socket, Connexion]) -> None:
    client, connexion = paire
    client.sendall(DecoupeurTrames.encoder(b"un") + DecoupeurTrames.encoder(b"deux"))
    recues = []
    while len(recues) < 2:
        attendre_lisible(connexion)
        recues += connexion.recevoir()
    assert recues == [b"un", b"deux"]


def test_rien_a_lire_ne_bloque_pas(paire: tuple[socket.socket, Connexion]) -> None:
    _, connexion = paire
    assert connexion.recevoir() == []


def test_fermeture_par_le_client_signalee(paire: tuple[socket.socket, Connexion]) -> None:
    client, connexion = paire
    client.close()
    attendre_lisible(connexion)
    with pytest.raises(ConnectionError, match="fermée par le client"):
        connexion.recevoir()


def test_coupure_brutale_signalee(paire: tuple[socket.socket, Connexion]) -> None:
    client, connexion = paire
    couper_brutalement(client)
    attendre_lisible(connexion)
    with pytest.raises(ConnectionResetError):
        connexion.recevoir()


# ---------- Envoi ----------

def test_trame_envoyee_au_client(paire: tuple[socket.socket, Connexion]) -> None:
    client, connexion = paire
    trame = DecoupeurTrames.encoder(b"pong")
    connexion.envoyer(trame)
    assert client.recv(64) == trame
    assert connexion.octets_en_attente == 0


def test_envoi_differe_tant_que_le_client_ne_lit_pas(paire: tuple[socket.socket, Connexion]) -> None:
    client, connexion = paire
    trame = DecoupeurTrames.encoder(bytes(600_000))
    connexion.envoyer(trame)
    assert connexion.octets_en_attente > 0
    recu = bytearray()
    limite = time.monotonic() + DELAI
    while len(recu) < len(trame) and time.monotonic() < limite:
        # Comme dans la boucle du serveur, la file se vide quand select dit que la socket peut écrire.
        lisibles, inscriptibles, _ = select.select([client], [connexion.socket], [], 0.05)
        if inscriptibles:
            connexion.vider()
        if lisibles:
            recu += client.recv(65536)
    assert bytes(recu) == trame
    assert connexion.octets_en_attente == 0


def test_client_qui_ne_lit_plus_deconnecte(paire: tuple[socket.socket, Connexion]) -> None:
    _, connexion = paire
    trame = DecoupeurTrames.encoder(bytes(65536))
    with pytest.raises(ConnectionError, match="trop lent"):
        for _ in range(2 * TAILLE_MAX_EN_ATTENTE // len(trame)):
            connexion.envoyer(trame)


def test_envoi_vers_un_client_disparu_signale(paire: tuple[socket.socket, Connexion]) -> None:
    client, connexion = paire
    couper_brutalement(client)
    attendre_lisible(connexion)
    with pytest.raises(ConnectionError):
        connexion.envoyer(DecoupeurTrames.encoder(b"pong"))
