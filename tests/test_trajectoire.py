"""Tests des trajectoires : découpage, positions, étapes et segments le long d'un trajet."""

import math

import pytest
from geometrie import JEAN_DE_LA_BRUYERE, NATIONS_NORD, NATIONS_SUD, rond_point_bel_air

from cherrypie.commun.erreurs import BrancheInconnueError
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import (
    DISTANCE_PASSAGE_PIETON,
    LARGEUR_CHAUSSEE,
    LONGUEUR_BRANCHE,
    LONGUEUR_TROTTOIR,
    Etape,
    Trajectoire,
    TronconDroit,
)

RAYON = 20.0
ENTREE_ANNEAU = LONGUEUR_BRANCHE


@pytest.fixture
def rond_point() -> RondPoint:
    return rond_point_bel_air()


@pytest.fixture
def sud_vers_nord(rond_point: RondPoint) -> Trajectoire:
    return Trajectoire.pour_vehicule(rond_point, "nations_sud", "nations_nord")


def coordonnees(position: Position) -> tuple[float, float]:
    return (position.x, position.y)


def longueurs_des_segments(rond_point: RondPoint) -> list[float]:
    return [segment.longueur for segment in rond_point.segments_entre(NATIONS_SUD, NATIONS_NORD)]


# ---------- Découpage en tronçons ----------

def test_vehicule_approche_anneau_puis_sortie(sud_vers_nord: Trajectoire) -> None:
    etapes = [troncon.etape for troncon in sud_vers_nord.troncons]
    assert etapes == [Etape.APPROCHE, Etape.ANNEAU, Etape.ANNEAU, Etape.SORTIE]


def test_longueur_totale(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    assert sud_vers_nord.longueur == pytest.approx(2 * LONGUEUR_BRANCHE + sum(longueurs_des_segments(rond_point)))


def test_approche_jusqu_a_l_axe_de_l_anneau(sud_vers_nord: Trajectoire) -> None:
    assert sud_vers_nord.longueur_approche == pytest.approx(LONGUEUR_BRANCHE)


def test_ligne_d_entree_au_bord_de_l_anneau(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    ligne = sud_vers_nord.position_a(sud_vers_nord.ligne_entree)
    attendue = rond_point.branche(NATIONS_SUD).point(RAYON + LARGEUR_CHAUSSEE / 2)
    assert coordonnees(ligne) == pytest.approx(coordonnees(attendue), abs=1e-9)
    assert sud_vers_nord.etape_a(sud_vers_nord.ligne_entree) is Etape.APPROCHE


@pytest.mark.parametrize("recul", [-1.0, LONGUEUR_BRANCHE])
def test_ligne_hors_de_l_approche_refusee(recul: float) -> None:
    approche = TronconDroit(Etape.APPROCHE, Position(0.0, 70.0), Position(0.0, 20.0))
    with pytest.raises(ValueError, match="ligne"):
        Trajectoire([approche], recul)


def test_segments_parcourus_dans_l_ordre(sud_vers_nord: Trajectoire) -> None:
    noms = [segment.nom for segment in sud_vers_nord.segments]
    assert noms == [f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}", f"{JEAN_DE_LA_BRUYERE}-{NATIONS_NORD}"]


def test_demi_tour_fait_le_tour_de_l_anneau(rond_point: RondPoint) -> None:
    assert len(Trajectoire.pour_vehicule(rond_point, "jean_de_la_bruyere", "jean_de_la_bruyere").segments) == 4


def test_branche_inconnue_refusee(rond_point: RondPoint) -> None:
    with pytest.raises(BrancheInconnueError):
        Trajectoire.pour_vehicule(rond_point, "nations_sud", "X")


def test_trajectoire_sans_approche_refusee() -> None:
    with pytest.raises(ValueError, match="approche"):
        Trajectoire([TronconDroit(Etape.SORTIE, Position(0.0, 20.0), Position(0.0, 70.0))])


def test_trajectoire_vide_refusee() -> None:
    with pytest.raises(ValueError, match="approche"):
        Trajectoire([])


def test_troncon_de_longueur_nulle_refuse() -> None:
    with pytest.raises(ValueError, match="distincts"):
        TronconDroit(Etape.APPROCHE, Position(0.0, 20.0), Position(0.0, 20.0))


# ---------- Positions ----------

def test_positions_aux_points_cles_du_trajet(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    sud, est, nord = (rond_point.branche(nom) for nom in (NATIONS_SUD, JEAN_DE_LA_BRUYERE, NATIONS_NORD))
    premier, second = longueurs_des_segments(rond_point)
    attendues = {
        0.0: sud.point(RAYON + LONGUEUR_BRANCHE),
        ENTREE_ANNEAU: sud.point(RAYON),
        ENTREE_ANNEAU + premier: est.point(RAYON),
        ENTREE_ANNEAU + premier + second: nord.point(RAYON),
        sud_vers_nord.longueur: nord.point(RAYON + LONGUEUR_BRANCHE),
    }
    for avancement, attendue in attendues.items():
        assert coordonnees(sud_vers_nord.position_a(avancement)) == pytest.approx(coordonnees(attendue), abs=1e-9)


def test_position_au_milieu_du_premier_segment(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    premier = rond_point.segments_entre(NATIONS_SUD, NATIONS_NORD)[0]
    angle = math.radians(premier.depart.angle) + premier.longueur / 2 / RAYON
    position = sud_vers_nord.position_a(ENTREE_ANNEAU + premier.longueur / 2)
    assert coordonnees(position) == pytest.approx((RAYON * math.cos(angle), RAYON * math.sin(angle)))


def test_position_au_dela_de_la_fin_reste_au_bout(sud_vers_nord: Trajectoire) -> None:
    fin = sud_vers_nord.position_a(sud_vers_nord.longueur)
    assert coordonnees(sud_vers_nord.position_a(sud_vers_nord.longueur + 10.0)) == pytest.approx(coordonnees(fin))


@pytest.mark.parametrize("avancement", [-1.0, float("nan")], ids=["negatif", "nan"])
def test_avancement_invalide_refuse(sud_vers_nord: Trajectoire, avancement: float) -> None:
    with pytest.raises(ValueError, match="avancement"):
        sud_vers_nord.position_a(avancement)


# ---------- Décalage latéral ----------

def test_decalage_en_approche_vers_la_droite(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    attendue = rond_point.branche(NATIONS_SUD).point(RAYON + LONGUEUR_BRANCHE, decalage=2.0)
    assert coordonnees(sud_vers_nord.position_a(0.0, decalage=2.0)) == pytest.approx(coordonnees(attendue), abs=1e-9)


def test_decalage_sur_l_anneau_vers_l_exterieur(sud_vers_nord: Trajectoire) -> None:
    position = sud_vers_nord.position_a(ENTREE_ANNEAU + 5.0, decalage=2.0)
    assert math.hypot(position.x, position.y) == pytest.approx(RAYON + 2.0)


def test_decalage_en_sortie_vers_la_droite(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    # En quittant l'anneau, la droite est à gauche d'un usager qui arrive par la même branche.
    fin = sud_vers_nord.position_a(sud_vers_nord.longueur, decalage=2.0)
    attendue = rond_point.branche(NATIONS_NORD).point(RAYON + LONGUEUR_BRANCHE, decalage=-2.0)
    assert coordonnees(fin) == pytest.approx(coordonnees(attendue), abs=1e-9)


# ---------- Étapes et segments ----------

def test_etape_et_segment_selon_l_avancement(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    premier, second = longueurs_des_segments(rond_point)
    attendus = [
        (0.0, Etape.APPROCHE, None),
        (ENTREE_ANNEAU, Etape.APPROCHE, None),
        (ENTREE_ANNEAU + 1.0, Etape.ANNEAU, f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}"),
        (ENTREE_ANNEAU + premier + 1.0, Etape.ANNEAU, f"{JEAN_DE_LA_BRUYERE}-{NATIONS_NORD}"),
        (ENTREE_ANNEAU + premier + second + 1.0, Etape.SORTIE, None),
    ]
    for avancement, etape, segment in attendus:
        assert sud_vers_nord.etape_a(avancement) is etape
        segment_trouve = sud_vers_nord.segment_a(avancement)
        assert (segment_trouve.nom if segment_trouve else None) == segment


def test_passe_par_les_seuls_segments_du_trajet(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    segments = {segment.nom: segment for segment in rond_point.segments}
    assert sud_vers_nord.passe_par(segments["jean_de_la_bruyere-nations_nord"])
    assert not sud_vers_nord.passe_par(segments["nations_nord-albert_camus"])


# ---------- Traversée d'un piéton ----------

@pytest.fixture
def traversee_nord(rond_point: RondPoint) -> Trajectoire:
    return Trajectoire.pour_pieton(rond_point, "nations_nord")


def test_pieton_rejoint_le_bord_traverse_puis_repart(traversee_nord: Trajectoire) -> None:
    etapes = [troncon.etape for troncon in traversee_nord.troncons]
    assert etapes == [Etape.APPROCHE, Etape.TRAVERSEE, Etape.SORTIE]


def test_pieton_ne_prend_pas_l_anneau(traversee_nord: Trajectoire) -> None:
    assert traversee_nord.segments == []
    assert traversee_nord.segment_a(traversee_nord.longueur / 2) is None


def test_longueur_de_la_traversee(traversee_nord: Trajectoire) -> None:
    assert traversee_nord.longueur == pytest.approx(LARGEUR_CHAUSSEE + 2 * LONGUEUR_TROTTOIR)
    assert traversee_nord.longueur_approche == pytest.approx(LONGUEUR_TROTTOIR)
    assert traversee_nord.ligne_entree == pytest.approx(LONGUEUR_TROTTOIR)


def test_pieton_attend_au_bord_de_la_chaussee(rond_point: RondPoint, traversee_nord: Trajectoire) -> None:
    # Le piéton part du trottoir situé à droite d'un véhicule qui arrive par sa branche.
    bord = traversee_nord.position_a(traversee_nord.longueur_approche)
    attendu = rond_point.branche(NATIONS_NORD).point(RAYON + DISTANCE_PASSAGE_PIETON, LARGEUR_CHAUSSEE / 2)
    assert coordonnees(bord) == pytest.approx(coordonnees(attendu))
    assert traversee_nord.etape_a(traversee_nord.longueur_approche) is Etape.APPROCHE


def test_pieton_sur_la_chaussee_en_traversee(rond_point: RondPoint, traversee_nord: Trajectoire) -> None:
    milieu = traversee_nord.longueur_approche + LARGEUR_CHAUSSEE / 2
    assert traversee_nord.etape_a(milieu) is Etape.TRAVERSEE
    attendu = rond_point.branche(NATIONS_NORD).point(RAYON + DISTANCE_PASSAGE_PIETON)
    assert coordonnees(traversee_nord.position_a(milieu)) == pytest.approx(coordonnees(attendu), abs=1e-9)


def test_passage_pieton_croise_l_approche_des_vehicules(rond_point: RondPoint, traversee_nord: Trajectoire) -> None:
    vehicule = Trajectoire.pour_vehicule(rond_point, "nations_nord", "nations_sud")
    passage = traversee_nord.position_a(traversee_nord.longueur_approche + LARGEUR_CHAUSSEE / 2)
    avancement_au_passage = LONGUEUR_BRANCHE - DISTANCE_PASSAGE_PIETON
    assert vehicule.etape_a(avancement_au_passage) is Etape.APPROCHE
    assert vehicule.position_a(avancement_au_passage).distance(passage) == pytest.approx(0.0, abs=1e-9)
