"""Tests du déplacement d'un usager le long de sa trajectoire, sans réseau."""

import math

import pytest
from geometrie import rond_point_bel_air

from cherrypie.client.deplacement import DISTANCE_SECURITE, VITESSE_LATERALE, Deplacement
from cherrypie.commun.protocole import CodeNotification
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import Etape
from cherrypie.modele.usager import FACTEUR_RALENTISSEMENT, Pieton, Voiture

PAS = 0.2
# La ligne d'entrée est au bout de l'approche, au bord de l'anneau.
LIGNE = rond_point_bel_air().longueur_branche
# Sur la voie intérieure du premier segment de nations_sud vers nations_nord, après le raccord.
SUR_LA_VOIE_INTERIEURE = LIGNE + 13.0


@pytest.fixture
def rond_point() -> RondPoint:
    return rond_point_bel_air()


@pytest.fixture
def voiture() -> Voiture:
    return Voiture("voiture_12", "nations_sud", "nations_nord")


@pytest.fixture
def deplacement(rond_point: RondPoint, voiture: Voiture) -> Deplacement:
    return Deplacement(voiture, voiture.calculer_trajectoire(rond_point))


def amener_a(deplacement: Deplacement, avancement: float) -> None:
    """Fait rouler l'usager librement jusqu'à un avancement donné, en un seul pas."""
    deplacement.avancer((avancement - deplacement.avancement) / Voiture.VITESSE_MAX)


# ---------- Départ et marche libre ----------

def test_usager_place_au_depart_a_l_arret(deplacement: Deplacement, voiture: Voiture) -> None:
    assert deplacement.avancement == 0.0
    assert voiture.position == deplacement.trajectoire.position_a(0.0)
    assert voiture.vitesse == 0.0
    assert not deplacement.termine


def test_pas_a_la_vitesse_maximale(deplacement: Deplacement, voiture: Voiture) -> None:
    deplacement.avancer(PAS)
    assert deplacement.avancement == pytest.approx(Voiture.VITESSE_MAX * PAS)
    assert voiture.vitesse == pytest.approx(Voiture.VITESSE_MAX)


def test_cap_suit_la_trajectoire(deplacement: Deplacement, voiture: Voiture) -> None:
    amener_a(deplacement, LIGNE + 20.0)
    assert voiture.cap == pytest.approx(deplacement.trajectoire.cap_a(deplacement.avancement))


def test_position_et_segment_suivent_l_avancement(deplacement: Deplacement, voiture: Voiture) -> None:
    amener_a(deplacement, LIGNE + 1.0)
    assert voiture.segment == "nations_sud-jean_de_la_bruyere"
    assert voiture.position == deplacement.trajectoire.position_a(deplacement.avancement)


def test_fin_de_trajet_sans_la_depasser(deplacement: Deplacement, voiture: Voiture) -> None:
    deplacement.avancer(1000.0)
    assert deplacement.termine
    assert deplacement.avancement == pytest.approx(deplacement.trajectoire.longueur)
    assert voiture.segment is None


def test_vitesse_reelle_reduite_au_dernier_pas(deplacement: Deplacement, voiture: Voiture) -> None:
    amener_a(deplacement, deplacement.trajectoire.longueur - 1.0)
    deplacement.avancer(1.0)
    assert voiture.vitesse == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("avancement", "etape"),
    [(1.0, Etape.APPROCHE), (LIGNE + 1.0, Etape.ANNEAU), (LIGNE + 80.0, Etape.SORTIE)],
    ids=["approche", "anneau", "sortie"],
)
def test_etape_suit_l_avancement(deplacement: Deplacement, voiture: Voiture, avancement: float, etape: Etape) -> None:
    amener_a(deplacement, avancement)
    assert voiture.etape is etape


@pytest.mark.parametrize("duree", [-0.1, float("nan")], ids=["negative", "nan"])
def test_duree_invalide_refusee(deplacement: Deplacement, duree: float) -> None:
    with pytest.raises(ValueError, match="durée"):
        deplacement.avancer(duree)


# ---------- ATTENDEZ et OK_PASSER ----------

def test_attendez_arrete_sur_la_ligne_d_entree(deplacement: Deplacement, voiture: Voiture) -> None:
    voiture.reagir(CodeNotification.ATTENDEZ)
    for _ in range(100):
        deplacement.avancer(PAS)
    assert deplacement.avancement == pytest.approx(LIGNE)
    assert voiture.etape is Etape.APPROCHE
    assert voiture.vitesse == 0.0
    assert voiture.segment is None


def test_attendez_arrete_au_bord_de_l_anneau(rond_point: RondPoint, deplacement: Deplacement, voiture: Voiture) -> None:
    voiture.reagir(CodeNotification.ATTENDEZ)
    for _ in range(100):
        deplacement.avancer(PAS)
    sud = rond_point.branche("nations_sud")
    ligne = sud.point(rond_point.rayon_bord, sud.decalage_voie)
    assert (voiture.position.x, voiture.position.y) == pytest.approx((ligne.x, ligne.y))


def test_ok_passer_relance_l_usager_arrete(deplacement: Deplacement, voiture: Voiture) -> None:
    voiture.reagir(CodeNotification.ATTENDEZ)
    for _ in range(100):
        deplacement.avancer(PAS)
    voiture.reagir(CodeNotification.OK_PASSER)
    deplacement.avancer(PAS)
    assert deplacement.avancement == pytest.approx(LIGNE + Voiture.VITESSE_MAX * PAS)
    assert voiture.vitesse == pytest.approx(Voiture.VITESSE_MAX)


def test_attendez_sans_effet_une_fois_la_ligne_franchie(deplacement: Deplacement, voiture: Voiture) -> None:
    amener_a(deplacement, LIGNE + 5.0)
    voiture.reagir(CodeNotification.ATTENDEZ)
    avant = deplacement.avancement
    deplacement.avancer(PAS)
    assert deplacement.avancement == pytest.approx(avant + Voiture.VITESSE_MAX * PAS)


# ---------- DEGAGEZ et CHANGEZ_VOIE ----------

def test_degagez_ralentit(deplacement: Deplacement, voiture: Voiture) -> None:
    amener_a(deplacement, SUR_LA_VOIE_INTERIEURE)
    voiture.reagir(CodeNotification.DEGAGEZ)
    avant = deplacement.avancement
    deplacement.avancer(PAS)
    assert deplacement.avancement - avant == pytest.approx(Voiture.VITESSE_MAX * FACTEUR_RALENTISSEMENT * PAS)


def test_degagez_fait_passer_sur_la_voie_exterieure(
    rond_point: RondPoint, deplacement: Deplacement, voiture: Voiture
) -> None:
    amener_a(deplacement, SUR_LA_VOIE_INTERIEURE)
    voiture.reagir(CodeNotification.DEGAGEZ)
    duree_du_changement = rond_point.largeur_voie_anneau / VITESSE_LATERALE
    for _ in range(math.ceil(duree_du_changement / PAS)):
        deplacement.avancer(PAS)
    assert voiture.segment == "nations_sud-jean_de_la_bruyere"
    assert math.hypot(voiture.position.x, voiture.position.y) == pytest.approx(rond_point.rayon_voie_exterieure)


def test_changement_de_voie_progressif(deplacement: Deplacement, voiture: Voiture) -> None:
    amener_a(deplacement, SUR_LA_VOIE_INTERIEURE)
    voiture.reagir(CodeNotification.DEGAGEZ)
    deplacement.avancer(PAS)
    assert deplacement.decalage == pytest.approx(VITESSE_LATERALE * PAS)


def test_changez_voie_range_au_bord_de_la_chaussee_sans_ralentir(deplacement: Deplacement, voiture: Voiture) -> None:
    voiture.reagir(CodeNotification.CHANGEZ_VOIE)
    for _ in range(10):
        deplacement.avancer(PAS)
    assert deplacement.avancement == pytest.approx(Voiture.VITESSE_MAX * PAS * 10)
    place = deplacement.trajectoire.place_a_droite_a(deplacement.avancement)
    assert deplacement.decalage == pytest.approx(place)
    attendue = deplacement.trajectoire.position_a(deplacement.avancement, place)
    assert (voiture.position.x, voiture.position.y) == pytest.approx((attendue.x, attendue.y))


def test_ok_passer_ramene_au_milieu_de_la_voie(deplacement: Deplacement, voiture: Voiture) -> None:
    voiture.reagir(CodeNotification.CHANGEZ_VOIE)
    for _ in range(10):
        deplacement.avancer(PAS)
    voiture.reagir(CodeNotification.OK_PASSER)
    for _ in range(10):
        deplacement.avancer(PAS)
    assert deplacement.decalage == 0.0


# ---------- Piéton ----------

def test_pieton_attend_au_bord_de_la_chaussee(rond_point: RondPoint) -> None:
    pieton = Pieton("pieton_4", "nations_nord", "nations_nord")
    deplacement = Deplacement(pieton, pieton.calculer_trajectoire(rond_point))
    pieton.reagir(CodeNotification.ATTENDEZ)
    for _ in range(50):
        deplacement.avancer(PAS)
    assert deplacement.avancement == pytest.approx(deplacement.trajectoire.longueur_approche)
    assert deplacement.trajectoire.etape_a(deplacement.avancement) is Etape.APPROCHE


# ---------- Ce que voit le conducteur ----------

def test_distance_de_securite_gardee_avec_l_obstacle(deplacement: Deplacement) -> None:
    deplacement.noter_devant(20.0, ceder=False)
    deplacement.avancer(10.0)
    assert deplacement.avancement == pytest.approx(20.0 - DISTANCE_SECURITE)


def test_obstacle_trop_proche_arrete_sans_reculer(deplacement: Deplacement, voiture: Voiture) -> None:
    amener_a(deplacement, 10.0)
    deplacement.noter_devant(2.0, ceder=False)
    deplacement.avancer(PAS)
    assert deplacement.avancement == pytest.approx(10.0)
    assert voiture.vitesse == 0.0


def test_voie_libre_leve_la_limite(deplacement: Deplacement) -> None:
    deplacement.noter_devant(8.0, ceder=False)
    deplacement.noter_devant(None, ceder=False)
    deplacement.avancer(PAS)
    assert deplacement.avancement == pytest.approx(Voiture.VITESSE_MAX * PAS)


def test_ceder_arrete_sur_la_ligne_d_entree(deplacement: Deplacement, voiture: Voiture) -> None:
    deplacement.noter_devant(None, ceder=True)
    for _ in range(100):
        deplacement.avancer(PAS)
    assert deplacement.avancement == pytest.approx(LIGNE)
    assert voiture.etape is Etape.APPROCHE


def test_anneau_libre_l_usager_entre(deplacement: Deplacement, voiture: Voiture) -> None:
    deplacement.noter_devant(None, ceder=True)
    for _ in range(100):
        deplacement.avancer(PAS)
    deplacement.noter_devant(None, ceder=False)
    deplacement.avancer(PAS)
    assert voiture.etape is Etape.ANNEAU


def test_ceder_sans_effet_une_fois_sur_l_anneau(deplacement: Deplacement) -> None:
    amener_a(deplacement, LIGNE + 3.0)
    deplacement.noter_devant(None, ceder=True)
    avant = deplacement.avancement
    deplacement.avancer(PAS)
    assert deplacement.avancement == pytest.approx(avant + Voiture.VITESSE_MAX * PAS)


def test_distance_negative_refusee(deplacement: Deplacement) -> None:
    with pytest.raises(ValueError, match="distance"):
        deplacement.noter_devant(-1.0, ceder=False)
