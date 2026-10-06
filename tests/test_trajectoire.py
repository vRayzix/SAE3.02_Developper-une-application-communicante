"""Tests des trajectoires : chaussées des branches, voies de l'anneau, positions, étapes et segments."""

import math

import pytest
from geometrie import ALBERT_CAMUS, JEAN_DE_LA_BRUYERE, NATIONS_NORD, NATIONS_SUD, rond_point_bel_air

from cherrypie.commun.erreurs import BrancheInconnueError
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import (
    LONGUEUR_TROTTOIR,
    MARGE_BORD_CHAUSSEE,
    Etape,
    Trajectoire,
    TronconArc,
    TronconDroit,
)

# Pas utilisé pour parcourir une trajectoire et vérifier qu'elle ne fait pas de saut, en mètres.
PAS_DE_PARCOURS = 0.1
# Dans un raccord, la position avance un peu plus vite ou moins vite que l'avancement.
TOLERANCE_VITESSE = 1.05


@pytest.fixture
def rond_point() -> RondPoint:
    return rond_point_bel_air()


@pytest.fixture
def sud_vers_nord(rond_point: RondPoint) -> Trajectoire:
    return Trajectoire.pour_vehicule(rond_point, NATIONS_SUD, NATIONS_NORD)


def coordonnees(position: Position) -> tuple[float, float]:
    return (position.x, position.y)


def distance_au_centre(position: Position) -> float:
    return math.hypot(position.x, position.y)


def arcs(trajectoire: Trajectoire) -> list[TronconArc]:
    return [troncon for troncon in trajectoire.troncons if isinstance(troncon, TronconArc)]


def rayons_des_voies_suivies(trajectoire: Trajectoire) -> dict[str, float]:
    """Rayon de chaque morceau de l'anneau parcouru à distance constante du centre, par segment."""
    return {arc.segment.nom: arc.rayon_debut for arc in arcs(trajectoire) if arc.rayon_debut == arc.rayon_fin}


def avancement_au_milieu(trajectoire: Trajectoire, cherche: TronconArc) -> float:
    avancement = 0.0
    for troncon in trajectoire.troncons:
        if troncon is cherche:
            return avancement + troncon.longueur / 2
        avancement += troncon.longueur
    raise AssertionError("tronçon absent de la trajectoire")


# ---------- Découpage en tronçons ----------

def test_vehicule_approche_anneau_puis_sortie(sud_vers_nord: Trajectoire) -> None:
    etapes = [troncon.etape for troncon in sud_vers_nord.troncons]
    assert etapes[0] is Etape.APPROCHE and etapes[-1] is Etape.SORTIE
    assert set(etapes[1:-1]) == {Etape.ANNEAU}


def test_approche_sur_la_chaussee_d_entree(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    sud = rond_point.branche(NATIONS_SUD)
    approche = sud_vers_nord.troncons[0]
    bord = rond_point.rayon_bord
    assert coordonnees(approche.depart) == pytest.approx(coordonnees(sud.point(bord + 50.0, sud.decalage_voie)))
    assert coordonnees(approche.arrivee) == pytest.approx(coordonnees(sud.point(bord, sud.decalage_voie)))
    assert sud_vers_nord.longueur_approche == pytest.approx(50.0)


def test_sortie_sur_la_chaussee_de_sortie(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    nord = rond_point.branche(NATIONS_NORD)
    sortie = sud_vers_nord.troncons[-1]
    bord = rond_point.rayon_bord
    assert coordonnees(sortie.depart) == pytest.approx(coordonnees(nord.point(bord, -nord.decalage_voie)))
    assert coordonnees(sortie.arrivee) == pytest.approx(coordonnees(nord.point(bord + 50.0, -nord.decalage_voie)))


def test_segments_parcourus_dans_l_ordre(sud_vers_nord: Trajectoire) -> None:
    noms = [segment.nom for segment in sud_vers_nord.segments]
    assert noms == [f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}", f"{JEAN_DE_LA_BRUYERE}-{NATIONS_NORD}"]


def test_demi_tour_fait_le_tour_de_l_anneau(rond_point: RondPoint) -> None:
    assert len(Trajectoire.pour_vehicule(rond_point, JEAN_DE_LA_BRUYERE, JEAN_DE_LA_BRUYERE).segments) == 4


def test_chaque_morceau_reste_dans_son_segment(rond_point: RondPoint) -> None:
    for entree in [NATIONS_NORD, JEAN_DE_LA_BRUYERE, NATIONS_SUD, ALBERT_CAMUS]:
        for sortie in [NATIONS_NORD, JEAN_DE_LA_BRUYERE, NATIONS_SUD, ALBERT_CAMUS]:
            for arc in arcs(Trajectoire.pour_vehicule(rond_point, entree, sortie)):
                depart = arc.segment.depart.angle
                assert (arc.angle_debut - depart) % 360 <= arc.segment.ouverture + 1e-9
                assert 0 < (arc.angle_fin - depart) % 360 or arc.angle_fin - depart == pytest.approx(360.0)


@pytest.mark.parametrize(
    ("entree", "sortie"),
    [(NATIONS_SUD, NATIONS_NORD), (NATIONS_NORD, ALBERT_CAMUS), (ALBERT_CAMUS, ALBERT_CAMUS)],
    ids=["en-face", "premiere-sortie", "demi-tour"],
)
@pytest.mark.parametrize("rayon", [20.0, 10.0], ids=["bel-air", "petit-anneau"])
def test_trajet_sans_saut(entree: str, sortie: str, rayon: float) -> None:
    trajectoire = Trajectoire.pour_vehicule(rond_point_bel_air(rayon=rayon), entree, sortie)
    precedente = trajectoire.position_a(0.0)
    avancement = PAS_DE_PARCOURS
    while avancement <= trajectoire.longueur:
        position = trajectoire.position_a(avancement)
        assert position.distance(precedente) <= PAS_DE_PARCOURS * TOLERANCE_VITESSE
        precedente, avancement = position, avancement + PAS_DE_PARCOURS


def test_branche_inconnue_refusee(rond_point: RondPoint) -> None:
    with pytest.raises(BrancheInconnueError):
        Trajectoire.pour_vehicule(rond_point, NATIONS_SUD, "x")


def test_trajectoire_sans_approche_refusee() -> None:
    with pytest.raises(ValueError, match="approche"):
        Trajectoire([TronconDroit(Etape.SORTIE, Position(0.0, 20.0), Position(0.0, 70.0))])


def test_trajectoire_vide_refusee() -> None:
    with pytest.raises(ValueError, match="approche"):
        Trajectoire([])


def test_troncon_de_longueur_nulle_refuse() -> None:
    with pytest.raises(ValueError, match="distincts"):
        TronconDroit(Etape.APPROCHE, Position(0.0, 20.0), Position(0.0, 20.0))


def test_arc_parcouru_a_l_envers_refuse(rond_point: RondPoint) -> None:
    with pytest.raises(ValueError, match="angles croissants"):
        TronconArc(rond_point.segments[0], 40.0, 30.0, 20.0, 20.0)


# ---------- Voies de l'anneau ----------

def test_voie_interieure_puis_exterieure_avant_la_sortie(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    assert rayons_des_voies_suivies(sud_vers_nord) == {
        f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}": pytest.approx(rond_point.rayon_voie_interieure),
        f"{JEAN_DE_LA_BRUYERE}-{NATIONS_NORD}": pytest.approx(rond_point.rayon_voie_exterieure),
    }


def test_premiere_sortie_sur_la_voie_exterieure(rond_point: RondPoint) -> None:
    trajectoire = Trajectoire.pour_vehicule(rond_point, NATIONS_NORD, ALBERT_CAMUS)
    rayons = rayons_des_voies_suivies(trajectoire).values()
    assert rayons and all(rayon == pytest.approx(rond_point.rayon_voie_exterieure) for rayon in rayons)


def test_vp_sur_la_voie_interieure_de_bout_en_bout(rond_point: RondPoint) -> None:
    trajectoire = Trajectoire.pour_vehicule(rond_point, NATIONS_SUD, NATIONS_NORD, prioritaire=True)
    rayons = rayons_des_voies_suivies(trajectoire).values()
    assert rayons and all(rayon == pytest.approx(rond_point.rayon_voie_interieure) for rayon in rayons)


def test_raccords_entre_chaussees_et_anneau(sud_vers_nord: Trajectoire) -> None:
    troncons = sud_vers_nord.troncons
    premier, dernier = arcs(sud_vers_nord)[0], arcs(sud_vers_nord)[-1]
    assert coordonnees(premier.position_a(0.0, 0.0)) == pytest.approx(coordonnees(troncons[0].arrivee))
    assert coordonnees(dernier.position_a(dernier.longueur, 0.0)) == pytest.approx(coordonnees(troncons[-1].depart))


# ---------- Positions ----------

def test_position_au_dela_de_la_fin_reste_au_bout(sud_vers_nord: Trajectoire) -> None:
    fin = sud_vers_nord.position_a(sud_vers_nord.longueur)
    assert coordonnees(sud_vers_nord.position_a(sud_vers_nord.longueur + 10.0)) == pytest.approx(coordonnees(fin))


@pytest.mark.parametrize("avancement", [-1.0, float("nan")], ids=["negatif", "nan"])
def test_avancement_invalide_refuse(sud_vers_nord: Trajectoire, avancement: float) -> None:
    with pytest.raises(ValueError, match="avancement"):
        sud_vers_nord.position_a(avancement)


# ---------- Décalage latéral ----------

def test_decalage_en_approche_vers_la_droite(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    sud = rond_point.branche(NATIONS_SUD)
    attendue = sud.point(rond_point.rayon_bord + 50.0, sud.decalage_voie + 2.0)
    assert coordonnees(sud_vers_nord.position_a(0.0, decalage=2.0)) == pytest.approx(coordonnees(attendue))


def test_decalage_sur_l_anneau_vers_l_exterieur(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    sur_la_voie_interieure = next(arc for arc in arcs(sud_vers_nord) if arc.rayon_debut == arc.rayon_fin)
    position = sud_vers_nord.position_a(avancement_au_milieu(sud_vers_nord, sur_la_voie_interieure), decalage=2.0)
    assert distance_au_centre(position) == pytest.approx(rond_point.rayon_voie_interieure + 2.0)


def test_decalage_en_sortie_vers_la_droite(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    nord = rond_point.branche(NATIONS_NORD)
    attendue = nord.point(rond_point.rayon_bord + 50.0, -nord.decalage_voie - 2.0)
    assert coordonnees(sud_vers_nord.position_a(sud_vers_nord.longueur, decalage=2.0)) == pytest.approx(coordonnees(attendue))


# ---------- Place pour se ranger ----------

def test_place_au_bord_de_la_chaussee(sud_vers_nord: Trajectoire) -> None:
    assert sud_vers_nord.place_a_droite_a(10.0) == pytest.approx(5.0 / 2 - MARGE_BORD_CHAUSSEE)


def test_place_d_une_voie_sur_la_voie_interieure(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    sur_la_voie_interieure = next(arc for arc in arcs(sud_vers_nord) if arc.rayon_debut == arc.rayon_fin)
    avancement = avancement_au_milieu(sud_vers_nord, sur_la_voie_interieure)
    assert sud_vers_nord.place_a_droite_a(avancement) == pytest.approx(rond_point.largeur_voie_anneau)


def test_pas_de_place_sur_la_voie_exterieure(sud_vers_nord: Trajectoire) -> None:
    sur_la_voie_exterieure = [arc for arc in arcs(sud_vers_nord) if arc.rayon_debut == arc.rayon_fin][-1]
    assert sud_vers_nord.place_a_droite_a(avancement_au_milieu(sud_vers_nord, sur_la_voie_exterieure)) == 0.0


# ---------- Étapes et segments ----------

def test_etape_et_segment_selon_l_avancement(sud_vers_nord: Trajectoire) -> None:
    attendus = [
        (0.0, Etape.APPROCHE, None),
        (50.0, Etape.APPROCHE, None),
        (51.0, Etape.ANNEAU, f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}"),
        (sud_vers_nord.longueur - 50.0 - 1.0, Etape.ANNEAU, f"{JEAN_DE_LA_BRUYERE}-{NATIONS_NORD}"),
        (sud_vers_nord.longueur - 1.0, Etape.SORTIE, None),
    ]
    for avancement, etape, segment in attendus:
        assert sud_vers_nord.etape_a(avancement) is etape
        segment_trouve = sud_vers_nord.segment_a(avancement)
        assert (segment_trouve.nom if segment_trouve else None) == segment


def test_passe_par_les_seuls_segments_du_trajet(rond_point: RondPoint, sud_vers_nord: Trajectoire) -> None:
    segments = {segment.nom: segment for segment in rond_point.segments}
    assert sud_vers_nord.passe_par(segments[f"{JEAN_DE_LA_BRUYERE}-{NATIONS_NORD}"])
    assert not sud_vers_nord.passe_par(segments[f"{NATIONS_NORD}-{ALBERT_CAMUS}"])


# ---------- Traversée d'un piéton ----------

@pytest.fixture
def traversee_nord(rond_point: RondPoint) -> Trajectoire:
    return Trajectoire.pour_pieton(rond_point, NATIONS_NORD)


def test_pieton_rejoint_le_bord_traverse_puis_repart(traversee_nord: Trajectoire) -> None:
    etapes = [troncon.etape for troncon in traversee_nord.troncons]
    assert etapes == [Etape.APPROCHE, Etape.TRAVERSEE, Etape.SORTIE]


def test_pieton_ne_prend_pas_l_anneau(traversee_nord: Trajectoire) -> None:
    assert traversee_nord.segments == []
    assert traversee_nord.segment_a(traversee_nord.longueur / 2) is None


def test_pieton_traverse_toute_la_branche(rond_point: RondPoint, traversee_nord: Trajectoire) -> None:
    nord = rond_point.branche(NATIONS_NORD)
    assert traversee_nord.longueur == pytest.approx(2 * nord.demi_largeur + 2 * LONGUEUR_TROTTOIR)
    assert traversee_nord.longueur_approche == pytest.approx(LONGUEUR_TROTTOIR)


def test_pieton_attend_au_bord_de_la_chaussee_d_entree(rond_point: RondPoint, traversee_nord: Trajectoire) -> None:
    nord = rond_point.branche(NATIONS_NORD)
    bord = traversee_nord.position_a(traversee_nord.longueur_approche)
    attendu = nord.point(rond_point.rayon_bord + nord.passage_pieton, nord.demi_largeur)
    assert coordonnees(bord) == pytest.approx(coordonnees(attendu))
    assert traversee_nord.etape_a(traversee_nord.longueur_approche) is Etape.APPROCHE


def test_pieton_sur_le_terre_plein_en_traversee(rond_point: RondPoint, traversee_nord: Trajectoire) -> None:
    nord = rond_point.branche(NATIONS_NORD)
    milieu = traversee_nord.longueur_approche + nord.demi_largeur
    assert traversee_nord.etape_a(milieu) is Etape.TRAVERSEE
    attendu = nord.point(rond_point.rayon_bord + nord.passage_pieton)
    assert coordonnees(traversee_nord.position_a(milieu)) == pytest.approx(coordonnees(attendu))


def test_passage_pieton_croise_l_approche_des_vehicules(rond_point: RondPoint, traversee_nord: Trajectoire) -> None:
    nord = rond_point.branche(NATIONS_NORD)
    vehicule = Trajectoire.pour_vehicule(rond_point, NATIONS_NORD, NATIONS_SUD)
    avancement_au_passage = rond_point.longueur_branche - nord.passage_pieton
    au_milieu_de_la_chaussee = traversee_nord.longueur_approche + nord.demi_largeur - nord.decalage_voie
    assert vehicule.etape_a(avancement_au_passage) is Etape.APPROCHE
    croisement = traversee_nord.position_a(au_milieu_de_la_chaussee)
    assert vehicule.position_a(avancement_au_passage).distance(croisement) == pytest.approx(0.0, abs=1e-9)
