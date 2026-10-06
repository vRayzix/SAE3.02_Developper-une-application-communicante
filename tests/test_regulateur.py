"""Tests du régulateur : qui reçoit quelle consigne."""

import pytest
from geometrie import rond_point_bel_air

from cherrypie.client.deplacement import Deplacement
from cherrypie.commun.protocole import CodeNotification
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import LONGUEUR_TROTTOIR, Trajectoire
from cherrypie.modele.usager import Pieton, Usager, VehiculePrioritaire, Voiture
from cherrypie.serveur.notifications import (
    TEXTE_ATTENDEZ_DOSAGE,
    TEXTE_ATTENDEZ_PIETON,
    TEXTE_ATTENDEZ_VP,
    TEXTE_OK_PASSER,
)
from cherrypie.serveur.passages import PassageEnCours
from cherrypie.serveur.registre import Registre
from cherrypie.serveur.regulateur import Regulateur

# Avancement de la ligne d'entrée : au-delà, l'usager est sur l'anneau.
ANNEAU = rond_point_bel_air().longueur_branche
SANS_CHARGE = {"nations_nord": 0.0, "jean_de_la_bruyere": 0.0, "nations_sud": 0.0, "albert_camus": 0.0}

ATTENDEZ = CodeNotification.ATTENDEZ
CHANGEZ_VOIE = CodeNotification.CHANGEZ_VOIE
DEGAGEZ = CodeNotification.DEGAGEZ
OK_PASSER = CodeNotification.OK_PASSER


@pytest.fixture
def rond_point() -> RondPoint:
    return rond_point_bel_air()


@pytest.fixture
def registre() -> Registre:
    return Registre()


@pytest.fixture
def regulateur(rond_point: RondPoint) -> Regulateur:
    return Regulateur(rond_point)


def debut_du_segment(trajectoire: Trajectoire, segment: str) -> float:
    """Avancement où une trajectoire entre sur un segment de l'anneau."""
    avancement = 0.0
    for troncon in trajectoire.troncons:
        if troncon.segment is not None and troncon.segment.nom == segment:
            return avancement
        avancement += troncon.longueur
    raise AssertionError(f"segment {segment} absent du trajet")


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
    vp = placer(VehiculePrioritaire("vp_1", "nations_sud", "nations_nord"), 10.0)
    segments = [segment.nom for segment in vp.calculer_trajectoire(rond_point).segments]
    return PassageEnCours("vp_1", "nations_sud", "nations_nord", segments, annonce=0.0, regulation=True)


def consignes(regulateur: Regulateur, registre: Registre, passages: list[PassageEnCours]) -> dict:
    return {notification.destinataire: notification.code for notification in regulateur.decider(registre, passages, SANS_CHARGE)}


# ---------- Sans VP ----------

def test_sans_vp_aucune_consigne(regulateur: Regulateur, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "nations_nord", "nations_sud"), 10.0)
    assert regulateur.decider(registre, [], SANS_CHARGE) == []


# ---------- VP en approche ----------

@pytest.mark.parametrize(
    ("usager", "avancement", "attendue"),
    [
        (Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), ANNEAU + 5.0, DEGAGEZ),
        (Voiture("voiture_2", "albert_camus", "jean_de_la_bruyere"), ANNEAU + 5.0, DEGAGEZ),
        (Voiture("voiture_3", "albert_camus", "nations_sud"), ANNEAU + 5.0, None),
        (Voiture("voiture_4", "nations_sud", "jean_de_la_bruyere"), 20.0, CHANGEZ_VOIE),
        (Voiture("voiture_5", "jean_de_la_bruyere", "albert_camus"), 20.0, ATTENDEZ),
        (Voiture("voiture_6", "nations_nord", "jean_de_la_bruyere"), 20.0, ATTENDEZ),
        (Voiture("voiture_7", "albert_camus", "nations_sud"), 20.0, None),
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
    [("nations_sud", 1.0, ATTENDEZ), ("nations_nord", 1.0, ATTENDEZ), ("jean_de_la_bruyere", 1.0, None), ("nations_sud", LONGUEUR_TROTTOIR + 2.0, None)],
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
    vp = VehiculePrioritaire("vp_1", "nations_sud", "nations_nord")
    placer(vp, debut_du_segment(vp.calculer_trajectoire(rond_point), "jean_de_la_bruyere-nations_nord") + 5.0)
    passage = PassageEnCours("vp_1", "nations_sud", "nations_nord", ["nations_sud-jean_de_la_bruyere", "jean_de_la_bruyere-nations_nord"], annonce=0.0, regulation=True)
    placer(Voiture("voiture_1", "nations_sud", "jean_de_la_bruyere"), ANNEAU + 2.0)
    placer(Voiture("voiture_2", "nations_sud", "albert_camus"), 20.0)
    placer(Voiture("voiture_3", "nations_sud", "jean_de_la_bruyere"), 20.0)
    assert vp.segment == "jean_de_la_bruyere-nations_nord"
    assert consignes(regulateur, registre, [passage]) == {"voiture_2": ATTENDEZ}


# ---------- Mémoire des consignes ----------

def test_consigne_deja_envoyee_pas_renvoyee(
    regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours
) -> None:
    placer(Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), 20.0)
    assert len(regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)) == 1
    assert regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE) == []


def test_fin_du_vp_libere_tout_le_monde(regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours) -> None:
    placer(Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), 20.0)
    placer(Voiture("voiture_2", "nations_sud", "jean_de_la_bruyere"), 20.0)
    regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    liberations = regulateur.decider(registre, [], SANS_CHARGE)
    assert {notification.destinataire for notification in liberations} == {"voiture_1", "voiture_2"}
    assert {(notification.code, notification.texte) for notification in liberations} == {(OK_PASSER, TEXTE_OK_PASSER)}
    assert regulateur.consignes_envoyees == {}


def test_usager_oublie_recoit_a_nouveau_sa_consigne(
    regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours
) -> None:
    placer(Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), 20.0)
    regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    regulateur.oublier("voiture_1")
    (notification,) = regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    assert (notification.code, notification.texte) == (ATTENDEZ, TEXTE_ATTENDEZ_VP)


def test_entrees_bloquees_la_ou_des_usagers_attendent(
    regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours
) -> None:
    placer(Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), 20.0)
    placer(Voiture("voiture_2", "nations_nord", "jean_de_la_bruyere"), 20.0)
    placer(Voiture("voiture_3", "nations_sud", "jean_de_la_bruyere"), 20.0)
    regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    assert regulateur.entrees_bloquees == ["jean_de_la_bruyere", "nations_nord"]


# ---------- Dosage des entrées sans VP ----------

def test_entree_la_moins_chargee_temporisee_quand_une_branche_sature(
    regulateur: Regulateur, registre: Registre, placer
) -> None:
    placer(Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), 20.0)
    placer(Voiture("voiture_2", "nations_sud", "nations_nord"), 20.0)
    densites = {"nations_nord": 0.8, "jean_de_la_bruyere": 0.125, "nations_sud": 0.25, "albert_camus": 0.0}
    notifications = regulateur.decider(registre, [], densites)
    assert [(notification.destinataire, notification.code) for notification in notifications] == [("voiture_1", ATTENDEZ)]
    assert notifications[0].texte == TEXTE_ATTENDEZ_DOSAGE
    assert regulateur.entrees_bloquees == ["jean_de_la_bruyere"]


def test_pas_de_dosage_sans_branche_saturee(regulateur: Regulateur, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), 20.0)
    assert regulateur.decider(registre, [], {"nations_nord": 0.6, "jean_de_la_bruyere": 0.125, "nations_sud": 0.0, "albert_camus": 0.0}) == []


def test_entree_elle_meme_saturee_pas_temporisee(regulateur: Regulateur, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), 20.0)
    assert regulateur.decider(registre, [], {"nations_nord": 0.8, "jean_de_la_bruyere": 0.9, "nations_sud": 0.0, "albert_camus": 0.0}) == []


def test_dosage_leve_quand_la_branche_se_vide(regulateur: Regulateur, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), 20.0)
    regulateur.decider(registre, [], {"nations_nord": 0.8, "jean_de_la_bruyere": 0.125, "nations_sud": 0.0, "albert_camus": 0.0})
    (notification,) = regulateur.decider(registre, [], {"nations_nord": 0.5, "jean_de_la_bruyere": 0.125, "nations_sud": 0.0, "albert_camus": 0.0})
    assert notification.code is OK_PASSER


def test_pas_de_dosage_pendant_le_passage_d_un_vp(
    regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours
) -> None:
    placer(Voiture("voiture_1", "albert_camus", "nations_sud"), 20.0)
    assert regulateur.decider(registre, [vp_sud_nord], {"nations_nord": 0.8, "jean_de_la_bruyere": 0.0, "nations_sud": 0.125, "albert_camus": 0.125}) == []


def test_pieton_jamais_temporise_par_le_dosage(regulateur: Regulateur, registre: Registre, placer) -> None:
    placer(Pieton("pieton_1", "jean_de_la_bruyere", "jean_de_la_bruyere"), 1.0)
    assert regulateur.decider(registre, [], {"nations_nord": 0.8, "jean_de_la_bruyere": 0.125, "nations_sud": 0.0, "albert_camus": 0.0}) == []


# ---------- Régulation coupée ----------

def test_regulation_coupee_libere_une_fois_puis_se_tait(
    regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours
) -> None:
    placer(Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), 20.0)
    regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    regulateur.active = False
    (liberation,) = regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    assert (liberation.destinataire, liberation.code) == ("voiture_1", OK_PASSER)
    assert regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE) == []
    assert regulateur.entrees_bloquees == []


def test_regulation_coupee_aucune_consigne_meme_avec_un_vp(
    regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours
) -> None:
    regulateur.active = False
    placer(Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), 20.0)
    assert regulateur.decider(registre, [vp_sud_nord], {"nations_nord": 0.8, "jean_de_la_bruyere": 0.125, "nations_sud": 0.0, "albert_camus": 0.0}) == []


def test_regulation_reactivee_renvoie_les_consignes(
    regulateur: Regulateur, registre: Registre, placer, vp_sud_nord: PassageEnCours
) -> None:
    placer(Voiture("voiture_1", "jean_de_la_bruyere", "albert_camus"), 20.0)
    regulateur.active = False
    regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    regulateur.active = True
    (notification,) = regulateur.decider(registre, [vp_sud_nord], SANS_CHARGE)
    assert notification.code is ATTENDEZ


def test_interrupteur_non_booleen_refuse(regulateur: Regulateur) -> None:
    with pytest.raises(TypeError, match="active ou non"):
        regulateur.active = "non"
