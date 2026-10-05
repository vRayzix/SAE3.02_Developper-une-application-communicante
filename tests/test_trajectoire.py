"""Tests des trajectoires : découpage, positions, étapes et segments le long d'un trajet."""

import math

import pytest

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
QUART_DE_TOUR = 2 * math.pi * RAYON / 4
ENTREE_ANNEAU = LONGUEUR_BRANCHE
SORTIE_ANNEAU = LONGUEUR_BRANCHE + 2 * QUART_DE_TOUR


@pytest.fixture
def rond_point() -> RondPoint:
    return RondPoint(["N", "E", "S", "O"], RAYON, 8)


@pytest.fixture
def sud_vers_nord(rond_point: RondPoint) -> Trajectoire:
    return Trajectoire.pour_vehicule(rond_point, "S", "N")


def coordonnees(position: Position) -> tuple[float, float]:
    return (position.x, position.y)


# ---------- Découpage en tronçons ----------

def test_vehicule_approche_anneau_puis_sortie(sud_vers_nord: Trajectoire) -> None:
    etapes = [troncon.etape for troncon in sud_vers_nord.troncons]
    assert etapes == [Etape.APPROCHE, Etape.ANNEAU, Etape.ANNEAU, Etape.SORTIE]


def test_longueur_totale(sud_vers_nord: Trajectoire) -> None:
    assert sud_vers_nord.longueur == pytest.approx(2 * LONGUEUR_BRANCHE + 2 * QUART_DE_TOUR)


def test_approche_jusqu_a_l_axe_de_l_anneau(sud_vers_nord: Trajectoire) -> None:
    assert sud_vers_nord.longueur_approche == pytest.approx(LONGUEUR_BRANCHE)


def test_ligne_d_entree_au_bord_de_l_anneau(sud_vers_nord: Trajectoire) -> None:
    ligne = sud_vers_nord.position_a(sud_vers_nord.ligne_entree)
    assert coordonnees(ligne) == pytest.approx((0.0, -(RAYON + LARGEUR_CHAUSSEE / 2)), abs=1e-9)
    assert sud_vers_nord.etape_a(sud_vers_nord.ligne_entree) is Etape.APPROCHE


@pytest.mark.parametrize("recul", [-1.0, LONGUEUR_BRANCHE])
def test_ligne_hors_de_l_approche_refusee(recul: float) -> None:
    approche = TronconDroit(Etape.APPROCHE, Position(0.0, 70.0), Position(0.0, 20.0))
    with pytest.raises(ValueError, match="ligne"):
        Trajectoire([approche], recul)


def test_segments_parcourus_dans_l_ordre(sud_vers_nord: Trajectoire) -> None:
    assert [segment.nom for segment in sud_vers_nord.segments] == ["S-E", "E-N"]


def test_demi_tour_fait_le_tour_de_l_anneau(rond_point: RondPoint) -> None:
    assert len(Trajectoire.pour_vehicule(rond_point, "E", "E").segments) == 4


def test_branche_inconnue_refusee(rond_point: RondPoint) -> None:
    with pytest.raises(BrancheInconnueError):
        Trajectoire.pour_vehicule(rond_point, "S", "X")


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

@pytest.mark.parametrize(
    ("avancement", "attendu"),
    [
        (0.0, (0.0, -70.0)),
        (ENTREE_ANNEAU, (0.0, -20.0)),
        (ENTREE_ANNEAU + QUART_DE_TOUR / 2, (RAYON * math.cos(-math.pi / 4), RAYON * math.sin(-math.pi / 4))),
        (ENTREE_ANNEAU + QUART_DE_TOUR, (20.0, 0.0)),
        (SORTIE_ANNEAU, (0.0, 20.0)),
        (SORTIE_ANNEAU + LONGUEUR_BRANCHE, (0.0, 70.0)),
    ],
    ids=["bout-branche-sud", "ligne-d-entree", "milieu-premier-segment", "devant-branche-est", "sortie-anneau", "bout-branche-nord"],
)
def test_position_le_long_du_trajet(sud_vers_nord: Trajectoire, avancement: float, attendu: tuple) -> None:
    assert coordonnees(sud_vers_nord.position_a(avancement)) == pytest.approx(attendu, abs=1e-9)


def test_position_au_dela_de_la_fin_reste_au_bout(sud_vers_nord: Trajectoire) -> None:
    fin = sud_vers_nord.position_a(sud_vers_nord.longueur)
    assert coordonnees(sud_vers_nord.position_a(sud_vers_nord.longueur + 10.0)) == pytest.approx(coordonnees(fin))


@pytest.mark.parametrize("avancement", [-1.0, float("nan")], ids=["negatif", "nan"])
def test_avancement_invalide_refuse(sud_vers_nord: Trajectoire, avancement: float) -> None:
    with pytest.raises(ValueError, match="avancement"):
        sud_vers_nord.position_a(avancement)


# ---------- Décalage latéral ----------

def test_decalage_en_approche_vers_la_droite(sud_vers_nord: Trajectoire) -> None:
    # En remontant la branche sud vers le centre, la droite est à l'est.
    assert coordonnees(sud_vers_nord.position_a(0.0, decalage=2.0)) == pytest.approx((2.0, -70.0), abs=1e-9)


def test_decalage_sur_l_anneau_vers_l_exterieur(sud_vers_nord: Trajectoire) -> None:
    position = sud_vers_nord.position_a(ENTREE_ANNEAU + QUART_DE_TOUR / 2, decalage=2.0)
    assert math.hypot(position.x, position.y) == pytest.approx(RAYON + 2.0)


def test_decalage_en_sortie_vers_la_droite(sud_vers_nord: Trajectoire) -> None:
    # En quittant l'anneau vers le nord, la droite est à l'est.
    fin = sud_vers_nord.position_a(sud_vers_nord.longueur, decalage=2.0)
    assert coordonnees(fin) == pytest.approx((2.0, 70.0), abs=1e-9)


# ---------- Étapes et segments ----------

@pytest.mark.parametrize(
    ("avancement", "etape", "segment"),
    [
        (0.0, Etape.APPROCHE, None),
        (ENTREE_ANNEAU, Etape.APPROCHE, None),
        (ENTREE_ANNEAU + 1.0, Etape.ANNEAU, "S-E"),
        (ENTREE_ANNEAU + QUART_DE_TOUR + 1.0, Etape.ANNEAU, "E-N"),
        (SORTIE_ANNEAU + 1.0, Etape.SORTIE, None),
    ],
    ids=["depart", "arret-sur-la-ligne-d-entree", "premier-segment", "second-segment", "sortie"],
)
def test_etape_et_segment_selon_l_avancement(
    sud_vers_nord: Trajectoire, avancement: float, etape: Etape, segment: str | None
) -> None:
    assert sud_vers_nord.etape_a(avancement) is etape
    segment_trouve = sud_vers_nord.segment_a(avancement)
    assert (segment_trouve.nom if segment_trouve else None) == segment


def test_passe_par_les_seuls_segments_du_trajet(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    segments = {segment.nom: segment for segment in rond_point.segments}
    assert sud_vers_nord.passe_par(segments["E-N"])
    assert not sud_vers_nord.passe_par(segments["N-O"])


# ---------- Traversée d'un piéton ----------

@pytest.fixture
def traversee_nord(rond_point: RondPoint) -> Trajectoire:
    return Trajectoire.pour_pieton(rond_point, "N")


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


def test_pieton_attend_au_bord_de_la_chaussee(traversee_nord: Trajectoire) -> None:
    # Vu d'un véhicule qui arrive du nord, le trottoir de droite est à l'ouest.
    bord = traversee_nord.position_a(traversee_nord.longueur_approche)
    assert coordonnees(bord) == pytest.approx((-LARGEUR_CHAUSSEE / 2, RAYON + DISTANCE_PASSAGE_PIETON))
    assert traversee_nord.etape_a(traversee_nord.longueur_approche) is Etape.APPROCHE


def test_pieton_sur_la_chaussee_en_traversee(traversee_nord: Trajectoire) -> None:
    milieu = traversee_nord.longueur_approche + LARGEUR_CHAUSSEE / 2
    assert traversee_nord.etape_a(milieu) is Etape.TRAVERSEE
    assert coordonnees(traversee_nord.position_a(milieu)) == pytest.approx(
        (0.0, RAYON + DISTANCE_PASSAGE_PIETON), abs=1e-9
    )


def test_passage_pieton_croise_l_approche_des_vehicules(rond_point: RondPoint, traversee_nord: Trajectoire) -> None:
    vehicule = Trajectoire.pour_vehicule(rond_point, "N", "S")
    passage = traversee_nord.position_a(traversee_nord.longueur_approche + LARGEUR_CHAUSSEE / 2)
    avancement_au_passage = LONGUEUR_BRANCHE - DISTANCE_PASSAGE_PIETON
    assert vehicule.etape_a(avancement_au_passage) is Etape.APPROCHE
    assert vehicule.position_a(avancement_au_passage).distance(passage) == pytest.approx(0.0, abs=1e-9)
