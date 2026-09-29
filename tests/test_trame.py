"""Tests du découpage des trames TCP."""

import socket
import struct

import pytest

from cherrypie.commun.erreurs import TrameInvalideError
from cherrypie.commun.trame import TAILLE_MAX_TRAME, DecoupeurTrames


# ---------- Encodage ----------

def test_encoder_prefixe_la_longueur() -> None:
    assert DecoupeurTrames.encoder(b"abc") == b"\x00\x00\x00\x03abc"


def test_encoder_charge_trop_grande_refusee() -> None:
    with pytest.raises(TrameInvalideError, match="limite"):
        DecoupeurTrames.encoder(bytes(TAILLE_MAX_TRAME + 1))


# ---------- Découpage ----------

def test_trame_complete_rendue_d_un_coup() -> None:
    decoupeur = DecoupeurTrames()
    assert decoupeur.ajouter(DecoupeurTrames.encoder(b"bonjour")) == [b"bonjour"]
    assert decoupeur.tampon == b""


def test_trame_en_deux_morceaux_rendue_au_second() -> None:
    trame = DecoupeurTrames.encoder(b"bonjour")
    decoupeur = DecoupeurTrames()
    assert decoupeur.ajouter(trame[:5]) == []
    assert decoupeur.ajouter(trame[5:]) == [b"bonjour"]


def test_trame_recue_octet_par_octet() -> None:
    trame = DecoupeurTrames.encoder(b"bonjour")
    decoupeur = DecoupeurTrames()
    for position in range(len(trame) - 1):
        assert decoupeur.ajouter(trame[position:position + 1]) == []
    assert decoupeur.ajouter(trame[-1:]) == [b"bonjour"]


def test_en_tete_incomplet_garde_dans_le_tampon() -> None:
    decoupeur = DecoupeurTrames()
    assert decoupeur.ajouter(b"\x00\x00") == []
    assert decoupeur.tampon == b"\x00\x00"


def test_deux_trames_collees_rendues_ensemble() -> None:
    octets = DecoupeurTrames.encoder(b"un") + DecoupeurTrames.encoder(b"deux")
    assert DecoupeurTrames().ajouter(octets) == [b"un", b"deux"]


def test_trame_suivie_d_un_debut_de_trame() -> None:
    suivante = DecoupeurTrames.encoder(b"deux")
    decoupeur = DecoupeurTrames()
    assert decoupeur.ajouter(DecoupeurTrames.encoder(b"un") + suivante[:3]) == [b"un"]
    assert decoupeur.tampon == suivante[:3]
    assert decoupeur.ajouter(suivante[3:]) == [b"deux"]


def test_trame_vide_rendue() -> None:
    assert DecoupeurTrames().ajouter(b"\x00\x00\x00\x00") == [b""]


def test_longueur_annoncee_trop_grande_refusee() -> None:
    en_tete = struct.pack("!I", TAILLE_MAX_TRAME + 1)
    with pytest.raises(TrameInvalideError, match="limite"):
        DecoupeurTrames().ajouter(en_tete)


# ---------- Sur une vraie connexion TCP ----------

def test_lectures_partielles_sur_connexion_tcp() -> None:
    charges = [b'{"type":"PING"}', b"x" * 3000, b'{"type":"BYE"}']
    with socket.create_server(("127.0.0.1", 0)) as ecoute:
        port = ecoute.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port)) as emettrice:
            connexion, _ = ecoute.accept()
            with connexion:
                emettrice.sendall(b"".join(DecoupeurTrames.encoder(charge) for charge in charges))
                emettrice.shutdown(socket.SHUT_WR)
                decoupeur = DecoupeurTrames()
                recues = []
                # Des lectures de 7 octets obligent le découpeur à recoller les morceaux.
                while True:
                    octets = connexion.recv(7)
                    if not octets:
                        break
                    recues.extend(decoupeur.ajouter(octets))
    assert recues == charges
