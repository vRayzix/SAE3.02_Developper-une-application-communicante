"""Tests de la logique du serveur, sans réseau."""

import pytest

from cherrypie.commun.erreurs import TrameInvalideError, UsagerInconnuError
from cherrypie.commun.protocole import Message, TypeMessage
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import RondPoint
from cherrypie.serveur.logique import IDENTIFIANT_SERVEUR, LogiqueServeur, Reponse

TIMEOUT = 6.0


@pytest.fixture
def logique() -> LogiqueServeur:
    return LogiqueServeur(RondPoint(["N", "E", "S", "O"], 20.0, 8), TIMEOUT)


def hello(identifiant: str, categorie: str = "voiture", entree: str = "N", sortie: str = "E") -> Message:
    return Message(TypeMessage.HELLO, identifiant, {"categorie": categorie, "entree": entree, "sortie": sortie})


def session_inscrite(logique: LogiqueServeur, identifiant: str = "voiture_12") -> int:
    """Ouvre une session et y inscrit un usager."""
    numero = logique.ouvrir_session(0.0)
    logique.traiter_tcp(numero, hello(identifiant), 0.5)
    return numero


def accuse(reponse: Reponse) -> dict:
    """Données de l'unique HELLO_ACK contenu dans une réponse."""
    (message,) = reponse.messages
    assert message.type is TypeMessage.HELLO_ACK
    return message.donnees


# ---------- Sessions ----------

def test_numero_de_session_jamais_reutilise(logique: LogiqueServeur) -> None:
    premiere = logique.ouvrir_session(0.0)
    logique.fermer_session(premiere)
    assert logique.ouvrir_session(1.0) != premiere
    assert logique.total_sessions == 2


def test_fermer_session_inconnue_sans_effet(logique: LogiqueServeur) -> None:
    assert logique.fermer_session(42) is None


def test_fermer_session_anonyme_ne_retire_personne(logique: LogiqueServeur) -> None:
    assert logique.fermer_session(logique.ouvrir_session(0.0)) is None


# ---------- HELLO ----------

def test_hello_valide_accepte_et_inscrit(logique: LogiqueServeur) -> None:
    numero = logique.ouvrir_session(0.0)
    assert accuse(logique.traiter_tcp(numero, hello("voiture_12"), 1.0)) == {"accepte": True}
    assert logique.registre.contient("voiture_12")


def test_fermer_session_retire_son_usager(logique: LogiqueServeur) -> None:
    numero = session_inscrite(logique)
    assert logique.fermer_session(numero).identifiant == "voiture_12"
    assert not logique.registre.contient("voiture_12")


@pytest.mark.parametrize(
    ("message", "motif"),
    [
        (hello("tank_1", categorie="tank"), "catégorie d'usager inconnue"),
        (hello("voiture_12", sortie="X"), "branche inconnue"),
        (Message(TypeMessage.HELLO, "voiture_12", {"categorie": "voiture", "entree": "N"}), "il manque : sortie"),
        (hello("pieton_4", categorie="pieton", entree="N", sortie="E"), "une seule branche"),
    ],
    ids=["categorie-inconnue", "branche-inconnue", "hello-incomplet", "pieton-sur-deux-branches"],
)
def test_hello_invalide_refuse_avec_sa_raison(logique: LogiqueServeur, message: Message, motif: str) -> None:
    numero = logique.ouvrir_session(0.0)
    donnees = accuse(logique.traiter_tcp(numero, message, 1.0))
    assert donnees["accepte"] is False
    assert motif in donnees["raison"]
    assert logique.registre.usagers == []


def test_identifiant_deja_connecte_refuse(logique: LogiqueServeur) -> None:
    session_inscrite(logique, "voiture_12")
    seconde = logique.ouvrir_session(1.0)
    donnees = accuse(logique.traiter_tcp(seconde, hello("voiture_12"), 2.0))
    assert donnees == {"accepte": False, "raison": "l'identifiant voiture_12 est déjà connecté"}


def test_identifiant_libere_a_la_fermeture_de_sa_session(logique: LogiqueServeur) -> None:
    logique.fermer_session(session_inscrite(logique, "voiture_12"))
    seconde = logique.ouvrir_session(1.0)
    assert accuse(logique.traiter_tcp(seconde, hello("voiture_12"), 2.0)) == {"accepte": True}


def test_second_hello_sur_la_meme_session_refuse(logique: LogiqueServeur) -> None:
    numero = session_inscrite(logique, "voiture_12")
    donnees = accuse(logique.traiter_tcp(numero, hello("voiture_12"), 1.0))
    assert donnees == {"accepte": False, "raison": "cette session est déjà enregistrée"}


# ---------- PING, ABONNEMENT et BYE ----------

def test_ping_recoit_pong(logique: LogiqueServeur) -> None:
    numero = session_inscrite(logique)
    reponse = logique.traiter_tcp(numero, Message(TypeMessage.PING, "voiture_12"), 1.0)
    (pong,) = reponse.messages
    assert pong.type is TypeMessage.PONG
    assert pong.emetteur == IDENTIFIANT_SERVEUR
    assert not reponse.fermer


def test_message_recu_note_l_activite_de_la_session(logique: LogiqueServeur) -> None:
    numero = logique.ouvrir_session(0.0)
    logique.traiter_tcp(numero, Message(TypeMessage.PING, "supervision"), 4.0)
    (session,) = logique.sessions
    assert session.derniere_activite == pytest.approx(4.0)


def test_abonnement_fait_de_la_session_une_supervision(logique: LogiqueServeur) -> None:
    numero = logique.ouvrir_session(0.0)
    assert logique.traiter_tcp(numero, Message(TypeMessage.ABONNEMENT, "supervision"), 1.0) == Reponse()
    (session,) = logique.sessions
    assert session.superviseur


def test_abonnement_d_un_usager_refuse(logique: LogiqueServeur) -> None:
    numero = session_inscrite(logique)
    with pytest.raises(TrameInvalideError, match="ne peut pas s'abonner"):
        logique.traiter_tcp(numero, Message(TypeMessage.ABONNEMENT, "voiture_12"), 1.0)


def test_bye_demande_la_fermeture_de_la_session(logique: LogiqueServeur) -> None:
    numero = session_inscrite(logique)
    assert logique.traiter_tcp(numero, Message(TypeMessage.BYE, "voiture_12"), 1.0) == Reponse(fermer=True)


# ---------- Messages refusés ----------

def test_message_au_nom_d_un_autre_usager_refuse(logique: LogiqueServeur) -> None:
    numero = session_inscrite(logique, "voiture_12")
    with pytest.raises(TrameInvalideError, match="session de voiture_12"):
        logique.traiter_tcp(numero, Message(TypeMessage.PING, "moto_3"), 1.0)


def test_message_refuse_ne_compte_pas_comme_activite(logique: LogiqueServeur) -> None:
    numero = session_inscrite(logique, "voiture_12")
    with pytest.raises(TrameInvalideError):
        logique.traiter_tcp(numero, Message(TypeMessage.PING, "moto_3"), 5.0)
    (session,) = logique.sessions
    assert session.derniere_activite == pytest.approx(0.5)


def test_position_envoyee_en_tcp_refusee(logique: LogiqueServeur) -> None:
    numero = session_inscrite(logique)
    with pytest.raises(TrameInvalideError, match="inattendu"):
        logique.traiter_tcp(numero, Message(TypeMessage.POS, "voiture_12", {"x": 0.0, "y": 0.0}), 1.0)


# ---------- Positions reçues en UDP ----------

def pos(identifiant: str = "voiture_12", **modifications: object) -> Message:
    donnees = {"x": 3.5, "y": -20.0, "vitesse": 4.2, "segment": "S-E"} | modifications
    return Message(TypeMessage.POS, identifiant, donnees)


def test_pos_met_a_jour_l_usager(logique: LogiqueServeur) -> None:
    session_inscrite(logique)
    logique.traiter_udp(pos())
    usager = logique.registre.obtenir("voiture_12")
    assert usager.position == Position(3.5, -20.0)
    assert usager.vitesse == pytest.approx(4.2)
    assert usager.segment == "S-E"


def test_pos_hors_de_l_anneau_sans_segment(logique: LogiqueServeur) -> None:
    session_inscrite(logique)
    logique.traiter_udp(pos(segment=None))
    assert logique.registre.obtenir("voiture_12").segment is None


def test_pos_d_un_usager_sans_session_refuse(logique: LogiqueServeur) -> None:
    with pytest.raises(UsagerInconnuError, match="voiture_99"):
        logique.traiter_udp(pos("voiture_99"))


def test_pos_apres_fermeture_de_la_session_refuse(logique: LogiqueServeur) -> None:
    logique.fermer_session(session_inscrite(logique))
    with pytest.raises(UsagerInconnuError):
        logique.traiter_udp(pos())


@pytest.mark.parametrize(
    ("modifications", "motif"),
    [
        ({"x": float("nan")}, "fini"),
        ({"y": "loin"}, "nombre"),
        ({"vitesse": 50.0}, "hors limites"),
        ({"segment": "N-S"}, "segment inconnu"),
    ],
    ids=["x-nan", "y-texte", "trop-rapide", "segment-inconnu"],
)
def test_pos_invalide_refuse_sans_toucher_l_usager(
    logique: LogiqueServeur, modifications: dict, motif: str
) -> None:
    session_inscrite(logique)
    with pytest.raises(TrameInvalideError, match=motif):
        logique.traiter_udp(pos(**modifications))
    usager = logique.registre.obtenir("voiture_12")
    assert usager.position is None
    assert usager.vitesse == 0.0


def test_pos_incomplet_refuse(logique: LogiqueServeur) -> None:
    session_inscrite(logique)
    incomplet = Message(TypeMessage.POS, "voiture_12", {"x": 0.0, "y": 0.0, "vitesse": 1.0})
    with pytest.raises(TrameInvalideError, match="il manque : segment"):
        logique.traiter_udp(incomplet)


def test_autre_message_qu_un_pos_refuse_en_udp(logique: LogiqueServeur) -> None:
    session_inscrite(logique)
    with pytest.raises(TrameInvalideError, match="seuls les POS"):
        logique.traiter_udp(Message(TypeMessage.PING, "voiture_12"))
