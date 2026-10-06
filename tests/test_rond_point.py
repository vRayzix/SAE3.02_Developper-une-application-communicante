"""Tests de la géométrie du rond-point : branches, anneau à deux voies, segments et parcours."""

import math

import pytest
from geometrie import (
    ALBERT_CAMUS,
    JEAN_DE_LA_BRUYERE,
    NATIONS_NORD,
    NATIONS_SUD,
    config_exemple,
    rond_point_a_trois_branches,
    rond_point_bel_air,
)

from cherrypie.commun.config import ParametresBranche
from cherrypie.commun.erreurs import BrancheInconnueError
from cherrypie.modele.rond_point import Branche, RondPoint, Segment

NORD = ParametresBranche("nord", "Rue du Nord", 0.0, 2.0, 8.0)
EST = ParametresBranche("est", "Rue de l'Est", 90.0, 2.0, 8.0)
SUD = ParametresBranche("sud", "Rue du Sud", 180.0, 2.0, 8.0)


@pytest.fixture
def rond_point() -> RondPoint:
    return rond_point_bel_air()


def noms(segments: list[Segment]) -> list[str]:
    return [segment.nom for segment in segments]


def construire(branches: list[ParametresBranche], rayon: float = 20.0, largeur_voie: float = 4.5) -> RondPoint:
    return RondPoint(branches, rayon, largeur_voie, 5.0, 50.0, 8)


# ---------- Construction ----------

def test_branches_placees_a_leur_cap(rond_point: RondPoint) -> None:
    caps = {branche.nom: branche.cap for branche in rond_point.branches}
    attendus = {NATIONS_NORD: 340.0, JEAN_DE_LA_BRUYERE: 57.0, NATIONS_SUD: 147.0, ALBERT_CAMUS: 230.0}
    assert caps == pytest.approx(attendus)


@pytest.mark.parametrize(("cap", "angle"), [(0.0, 90.0), (90.0, 0.0), (180.0, 270.0), (340.0, 110.0), (57.0, 33.0)])
def test_angle_deduit_du_cap(cap: float, angle: float) -> None:
    assert Branche(ParametresBranche("b", "Rue B", cap, 2.0, 8.0), 8, 5.0).angle == pytest.approx(angle)


def test_segments_dans_le_sens_de_circulation(rond_point: RondPoint) -> None:
    assert noms(rond_point.segments) == [
        f"{JEAN_DE_LA_BRUYERE}-{NATIONS_NORD}",
        f"{NATIONS_NORD}-{ALBERT_CAMUS}",
        f"{ALBERT_CAMUS}-{NATIONS_SUD}",
        f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}",
    ]


@pytest.mark.parametrize(
    ("segment", "ouverture"),
    [
        (f"{JEAN_DE_LA_BRUYERE}-{NATIONS_NORD}", 77.0),
        (f"{NATIONS_NORD}-{ALBERT_CAMUS}", 110.0),
        (f"{ALBERT_CAMUS}-{NATIONS_SUD}", 83.0),
        (f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}", 90.0),
    ],
)
def test_longueur_des_segments_sur_l_axe(rond_point: RondPoint, segment: str, ouverture: float) -> None:
    longueurs = {troncon.nom: troncon.longueur for troncon in rond_point.segments}
    assert longueurs[segment] == pytest.approx(20.0 * math.radians(ouverture))


def test_tour_complet(rond_point: RondPoint) -> None:
    assert sum(segment.longueur for segment in rond_point.segments) == pytest.approx(2 * math.pi * 20.0)


def test_ordre_de_la_configuration_sans_effet_sur_les_segments() -> None:
    branches = rond_point_bel_air().branches
    parametres = config_exemple().branches
    a_l_envers = construire(list(reversed(parametres)))
    assert noms(a_l_envers.segments) == noms(rond_point_bel_air().segments)
    assert [branche.nom for branche in a_l_envers.branches] == [branche.nom for branche in reversed(branches)]


def test_trois_branches_reparties_regulierement() -> None:
    angles = [branche.angle for branche in rond_point_a_trois_branches().branches]
    assert angles == pytest.approx([90.0, 330.0, 210.0])


def test_capacite_donnee_a_chaque_branche(rond_point: RondPoint) -> None:
    assert {branche.capacite for branche in rond_point.branches} == {8}


def test_construction_depuis_la_configuration() -> None:
    rond_point = RondPoint.depuis_config(config_exemple())
    noms_branches = [branche.nom for branche in rond_point.branches]
    assert noms_branches == [NATIONS_NORD, JEAN_DE_LA_BRUYERE, NATIONS_SUD, ALBERT_CAMUS]
    assert rond_point.branche(NATIONS_NORD).libelle == "Bd des Nations (nord)"
    assert rond_point.longueur_branche == pytest.approx(50.0)


def test_branches_modifiees_de_l_exterieur_sans_effet(rond_point: RondPoint) -> None:
    rond_point.branches.clear()
    assert len(rond_point.branches) == 4


@pytest.mark.parametrize(
    ("branches", "rayon", "largeur_voie", "motif"),
    [
        ([NORD, SUD], 20.0, 4.5, "au moins 3"),
        ([NORD, NORD, EST], 20.0, 4.5, "même nom"),
        ([NORD, EST, ParametresBranche("x", "Rue X", 360.0, 2.0, 8.0)], 20.0, 4.5, "même cap"),
        ([NORD, EST, SUD], 0.0, 4.5, "positifs"),
        ([NORD, EST, SUD], 20.0, 20.0, "voie de l'anneau"),
    ],
    ids=["trop-peu-de-branches", "noms-en-double", "caps-en-double", "rayon-nul", "voie-plus-large-que-le-rayon"],
)
def test_rond_point_incoherent_refuse(
    branches: list[ParametresBranche], rayon: float, largeur_voie: float, motif: str
) -> None:
    with pytest.raises(ValueError, match=motif):
        construire(branches, rayon, largeur_voie)


# ---------- Anneau à deux voies ----------

def test_rayons_des_deux_voies(rond_point: RondPoint) -> None:
    assert rond_point.rayon_voie_interieure == pytest.approx(17.75)
    assert rond_point.rayon_voie_exterieure == pytest.approx(22.25)


def test_ilot_et_bord_de_l_anneau(rond_point: RondPoint) -> None:
    assert rond_point.rayon_ilot == pytest.approx(15.5)
    assert rond_point.rayon_bord == pytest.approx(24.5)


# ---------- Recherche d'une branche ----------

def test_branche_retrouvee_par_son_nom(rond_point: RondPoint) -> None:
    assert rond_point.branche(NATIONS_SUD).cap == pytest.approx(147.0)


def test_branche_inconnue_refusee(rond_point: RondPoint) -> None:
    with pytest.raises(BrancheInconnueError, match="'x'"):
        rond_point.branche("x")


# ---------- Parcours sur l'anneau ----------

@pytest.mark.parametrize(
    ("entree", "sortie", "attendu"),
    [
        (NATIONS_NORD, ALBERT_CAMUS, [f"{NATIONS_NORD}-{ALBERT_CAMUS}"]),
        (NATIONS_SUD, NATIONS_NORD, [f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}", f"{JEAN_DE_LA_BRUYERE}-{NATIONS_NORD}"]),
        (
            NATIONS_NORD, JEAN_DE_LA_BRUYERE,
            [f"{NATIONS_NORD}-{ALBERT_CAMUS}", f"{ALBERT_CAMUS}-{NATIONS_SUD}", f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}"],
        ),
        (
            NATIONS_NORD, NATIONS_NORD,
            [
                f"{NATIONS_NORD}-{ALBERT_CAMUS}", f"{ALBERT_CAMUS}-{NATIONS_SUD}",
                f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}", f"{JEAN_DE_LA_BRUYERE}-{NATIONS_NORD}",
            ],
        ),
    ],
    ids=["branche-suivante", "en-face", "trois-segments", "demi-tour"],
)
def test_segments_entre_deux_branches(rond_point: RondPoint, entree: str, sortie: str, attendu: list[str]) -> None:
    assert noms(rond_point.segments_entre(entree, sortie)) == attendu


def test_segments_entre_branche_inconnue_refuses(rond_point: RondPoint) -> None:
    with pytest.raises(BrancheInconnueError):
        rond_point.segments_entre(NATIONS_NORD, "x")


# ---------- Branches ----------

def test_point_sur_l_axe_d_une_branche() -> None:
    point = Branche(EST, 8, 5.0).point(20.0)
    assert (point.x, point.y) == pytest.approx((20.0, 0.0))


def test_point_decale_a_droite_d_un_usager_qui_arrive() -> None:
    # En arrivant du nord vers le centre, on roule vers le sud : la droite est à l'ouest.
    point = Branche(NORD, 8, 5.0).point(20.0, decalage=1.0)
    assert (point.x, point.y) == pytest.approx((-1.0, 20.0))


def test_chaussees_de_part_et_d_autre_du_terre_plein(rond_point: RondPoint) -> None:
    nord = rond_point.branche(NATIONS_NORD)
    assert nord.decalage_voie == pytest.approx(8.0 / 2 + 5.0 / 2)
    assert nord.demi_largeur == pytest.approx(8.0 / 2 + 5.0)


def test_raccord_au_bord_de_l_anneau(rond_point: RondPoint) -> None:
    nord = rond_point.branche(NATIONS_NORD)
    assert rond_point.ecart_raccord(nord) == pytest.approx(math.degrees(math.atan2(6.5, 24.5)))


def test_branche_sans_nom_refusee() -> None:
    with pytest.raises(ValueError, match="nom"):
        Branche(ParametresBranche("", "Rue", 0.0, 2.0, 8.0), 8, 5.0)


def test_branche_sans_capacite_refusee() -> None:
    with pytest.raises(ValueError, match="capacité"):
        Branche(NORD, 0, 5.0)


@pytest.mark.parametrize(
    ("parametres", "largeur_chaussee"),
    [
        (ParametresBranche("nord", "Rue", 0.0, 0.0, 8.0), 5.0),
        (ParametresBranche("nord", "Rue", 0.0, 2.0, -1.0), 5.0),
        (NORD, 0.0),
    ],
    ids=["terre-plein-nul", "passage-negatif", "chaussee-nulle"],
)
def test_branche_aux_dimensions_incoherentes_refusee(parametres: ParametresBranche, largeur_chaussee: float) -> None:
    with pytest.raises(ValueError, match="dimension positive"):
        Branche(parametres, 8, largeur_chaussee)


def test_segment_d_une_branche_vers_elle_meme_refuse() -> None:
    nord = Branche(NORD, 8, 5.0)
    with pytest.raises(ValueError, match="deux branches différentes"):
        Segment(nord, nord, 10.0)
