"""Tests du régulateur : qui reçoit quelle consigne."""

import math

import pytest

from cherrypie.client.deplacement import Deplacement
from cherrypie.commun.protocole import CodeNotification
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import LONGUEUR_BRANCHE, LONGUEUR_TROTTOIR
from cherrypie.modele.usager import Pieton, Usager, VehiculePrioritaire, Voiture
from cherrypie.serveur.notifications import TEXTE_ATTENDEZ_PIETON, TEXTE_ATTENDEZ_VP, TEXTE_OK_PASSER
from cherrypie.serveur.passages import PassageEnCours
from cherrypie.serveur.registre import Registre
from cherrypie.serveur.regulateur import Regulateur

RAYON = 20.0
QUART = 2 * math.pi * RAYON / 4
ANNEAU = LONGUEUR_BRANCHE
SANS_CHARGE = {"N": 0.0, "E": 0.0, "S": 0.0, "O": 0.0}

ATTENDEZ = CodeNotification.ATTENDEZ
CHANGEZ_VOIE = CodeNotification.CHANGEZ_VOIE
DEGAGEZ = CodeNotification.DEGAGEZ
OK_PASSER = CodeNotification.OK_PASSER


@pytest.fixture
def rond_point() -> RondPoint:
    return RondPoint(["N", "E", "S", "O"], RAYON, 8)


@pytest.fixture
def registre() -> Registre:
    return Registre()


@pytest.fixture
def regulateur(rond_point: RondPoint) -> Regulateur:
    return Regulateur(rond_point)


@pytest.fixture
def placer(rond_point: RondPoint, registre: Registre):
    """Place un usager à un avancement donné de sa trajectoire et l'inscrit au registre."""

    def placer_usager(usager: Usager, avancement: float) -> Usager:
        deplacement = Deplacement(usager, usager.calculer_trajectoire(rond_point))
        deplacement.avancer(avancement / usager.VITESSE_MAX)
        registre.ajouter(usager)
        return usager

    return placer_usager


@pytest.fixture
def vp_sud_nord(rond_point: RondPoint, placer) -> PassageEnCours:
    """VP qui va du sud au nord : il réserve S-E puis E-N. Il est placé en approche."""
    vp = placer(VehiculePrioritaire("vp_1", "S", "N"), 10.0)
    segments = [segment.nom for segment in vp.calculer_trajectoire(rond_point).segments]
    return PassageEnCours("vp_1", "S", "N", segments, annonce=0.0, regulation=True)


def consignes(regulateur: Regulateur, registre: Registre, passages: list[PassageEnCours]) -> dict:
    return {notification.destinataire: notification.code for notification in regulateur.decider(registre, passages, SANS_CHARGE)}


# ---------- Sans VP ----------

def test_sans_vp_aucune_consigne(regulateur: Regulateur, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "N", "S"), 10.0)
    assert regulateur.decider(registre, [], SANS_CHARGE) == []


# ---------- VP en approche ----------

@pytest.mark.parametrize(
    ("usager", "avancement", "attendue"),
    [
        (Voiture("voiture_1", "E", "O"), ANNEAU + 5.0, DEGAGEZ),
        (Voiture("voiture_2", "O", "E"), ANNEAU + 5.0, DEGAGEZ),
        (Voiture("voiture_3", "O", "S"), ANNEAU + 5.0, None),
        (Voiture("voiture_4", "S", "E"), 20.0, CHANGEZ_VOIE),
        (Voiture("voiture_5", "E", "O"), 20.0, ATTENDEZ),
        (Voiture("voiture_6", "N", "E"), 20.0, ATTENDEZ),
        (Voiture("voiture_7", "O", "S"), 20.0, None),
    ],
    ids=[
        "sur-un-segment-reserve",
        "va-passer-sur-un-segment-reserve",
        "ne-croise-pas-le-vp",
        "en-file-sur-l-entree-du-vp",
        "entree-qui-debouche-sur-un-segment-reserve",
        "trajet-qui-passe-par-un-segment-reserve",
        "trajet-hors-reservation",
    ],
)
def test_consigne_selon_la_position_par_rapport_au_vp(
    regulateur: Regulateur,
    registre: Registre,
    placer,
    vp_sud_nord: PassageEnCours,
    usager: Usager,
    avancement: float,
    attendue: CodeNotification | None,
) -> None:
    placer(usager, avancement)
    assert consignes(regulateur, registre, [vp_sud_nord]).get(usager.identifiant) is attendue


def test_le_vp_ne_recoit_aucune_consigne(regulateur: Regulateur, registre: Registre, vp_sud_nord: PassageEnCours) -> None:
    assert "vp_1" not in consignes(regulateur, registre, [vp_sud_nord])


@pytest.mark.parametrize(
    ("branche", "avancement", "attendue"),
    [("S", 1.0, ATTENDEZ), ("N", 1.0, ATTENDEZ), ("E", 1.0, None), ("S", LONGUEUR_TROTTOIR + 2.0, None)],
    ids=["attend-sur-l-entree-du-vp", "attend-sur-la-sortie-du-vp", "loin-du-vp", "deja-en-train-de-traverser"],
)
def test_pieton_attend_pour_traverser(
    regulateur: Regulateur,
    registre: Registre,
    placer,
    vp_sud_nord: PassageEnCours,
    branche: str,
    avancement: float,
    attendue: CodeNotification | None,
) -> None:
    placer(Pieton("pieton_1", branche, branche), avancement)
    notifications = regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    assert {notification.code for notification in notifications} == ({attendue} if attendue else set())
    if attendue:
        assert notifications[0].texte == TEXTE_ATTENDEZ_PIETON


# ---------- VP sur l'anneau ----------

def test_segment_deja_quitte_par_le_vp_libere(
    rond_point: RondPoint, regulateur: Regulateur, registre: Registre, placer
) -> None:
    vp = placer(VehiculePrioritaire("vp_1", "S", "N"), ANNEAU + QUART + 5.0)
    passage = PassageEnCours("vp_1", "S", "N", ["S-E", "E-N"], annonce=0.0, regulation=True)
    placer(Voiture("voiture_1", "S", "E"), ANNEAU + 2.0)
    placer(Voiture("voiture_2", "S", "O"), 20.0)
    placer(Voiture("voiture_3", "S", "E"), 20.0)
    assert vp.segment == "E-N"
    assert consignes(regulateur, registre, [passage]) == {"voiture_2": ATTENDEZ}


# ---------- Mémoire des consignes ----------

def test_consigne_deja_envoyee_pas_renvoyee(
    regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours
) -> None:
    placer(Voiture("voiture_1", "E", "O"), 20.0)
    assert len(regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)) == 1
    assert regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE) == []


def test_fin_du_vp_libere_tout_le_monde(regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours) -> None:
    placer(Voiture("voiture_1", "E", "O"), 20.0)
    placer(Voiture("voiture_2", "S", "E"), 20.0)
    regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    liberations = regulateur.decider(registre, [], SANS_CHARGE)
    assert {notification.destinataire for notification in liberations} == {"voiture_1", "voiture_2"}
    assert {(notification.code, notification.texte) for notification in liberations} == {(OK_PASSER, TEXTE_OK_PASSER)}
    assert regulateur.consignes_envoyees == {}


def test_usager_oublie_recoit_a_nouveau_sa_consigne(
    regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours
) -> None:
    placer(Voiture("voiture_1", "E", "O"), 20.0)
    regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    regulateur.oublier("voiture_1")
    (notification,) = regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    assert (notification.code, notification.texte) == (ATTENDEZ, TEXTE_ATTENDEZ_VP)


def test_entrees_bloquees_la_ou_des_usagers_attendent(
    regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours
) -> None:
    placer(Voiture("voiture_1", "E", "O"), 20.0)
    placer(Voiture("voiture_2", "N", "E"), 20.0)
    placer(Voiture("voiture_3", "S", "E"), 20.0)
    regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    assert regulateur.entrees_bloquees == ["E", "N"]
