"""Tests de la géométrie du rond-point : branches, segments et parcours sur l'anneau."""

import math
from pathlib import Path

import pytest

from cherrypie.commun.config import Configuration
from cherrypie.commun.erreurs import BrancheInconnueError
from cherrypie.modele.rond_point import Branche, RondPoint, Segment

CHEMIN_EXEMPLE = Path(__file__).resolve().parent.parent / "config.exemple.ini"


@pytest.fixture
def rond_point() -> RondPoint:
    return RondPoint(["N", "E", "S", "O"], 20.0, 8)


def noms(segments: list[Segment]) -> list[str]:
    return [segment.nom for segment in segments]


# ---------- Construction ----------

def test_branches_placees_a_leur_point_cardinal(rond_point: RondPoint) -> None:
    angles = {branche.nom: branche.angle for branche in rond_point.branches}
    assert angles == pytest.approx({"N": 90.0, "E": 0.0, "S": 270.0, "O": 180.0})


def test_trois_branches_reparties_regulierement() -> None:
    angles = [branche.angle for branche in RondPoint(["A", "B", "C"], 20.0, 8).branches]
    assert angles == pytest.approx([90.0, 330.0, 210.0])


def test_un_segment_par_branche_dans_le_sens_de_circulation(rond_point: RondPoint) -> None:
    assert noms(rond_point.segments) == ["N-O", "E-N", "S-E", "O-S"]


def test_longueur_des_segments(rond_point: RondPoint) -> None:
    for segment in rond_point.segments:
        assert segment.longueur == pytest.approx(2 * math.pi * 20.0 / 4)


def test_capacite_donnee_a_chaque_branche(rond_point: RondPoint) -> None:
    assert {branche.capacite for branche in rond_point.branches} == {8}


def test_construction_depuis_la_configuration() -> None:
    rond_point = RondPoint.depuis_config(Configuration.depuis_fichier(CHEMIN_EXEMPLE))
    assert [branche.nom for branche in rond_point.branches] == ["N", "E", "S", "O"]
    assert rond_point.rayon == pytest.approx(20.0)


def test_branches_modifiees_de_l_exterieur_sans_effet(rond_point: RondPoint) -> None:
    rond_point.branches.clear()
    assert len(rond_point.branches) == 4


@pytest.mark.parametrize(
    ("noms_branches", "rayon", "motif"),
    [
        (["N", "S"], 20.0, "au moins 3"),
        (["N", "E", "N"], 20.0, "même nom"),
        (["N", "E", "S"], 0.0, "rayon"),
    ],
    ids=["trop-peu-de-branches", "noms-en-double", "rayon-nul"],
)
def test_rond_point_incoherent_refuse(noms_branches: list[str], rayon: float, motif: str) -> None:
    with pytest.raises(ValueError, match=motif):
        RondPoint(noms_branches, rayon, 8)


# ---------- Recherche d'une branche ----------

def test_branche_retrouvee_par_son_nom(rond_point: RondPoint) -> None:
    assert rond_point.branche("S").angle == pytest.approx(270.0)


def test_branche_inconnue_refusee(rond_point: RondPoint) -> None:
    with pytest.raises(BrancheInconnueError, match="'X'"):
        rond_point.branche("X")


# ---------- Parcours sur l'anneau ----------

@pytest.mark.parametrize(
    ("entree", "sortie", "attendu"),
    [
        ("N", "O", ["N-O"]),
        ("S", "N", ["S-E", "E-N"]),
        ("N", "E", ["N-O", "O-S", "S-E"]),
        ("N", "N", ["N-O", "O-S", "S-E", "E-N"]),
    ],
    ids=["branche-suivante", "en-face", "trois-quarts", "demi-tour"],
)
def test_segments_entre_deux_branches(rond_point: RondPoint, entree: str, sortie: str, attendu: list[str]) -> None:
    assert noms(rond_point.segments_entre(entree, sortie)) == attendu


def test_segments_entre_branche_inconnue_refuses(rond_point: RondPoint) -> None:
    with pytest.raises(BrancheInconnueError):
        rond_point.segments_entre("N", "X")


# ---------- Points d'une branche ----------

def test_point_sur_l_axe_d_une_branche(rond_point: RondPoint) -> None:
    point = rond_point.branche("E").point(20.0)
    assert (point.x, point.y) == pytest.approx((20.0, 0.0))


def test_point_decale_a_droite_d_un_usager_qui_arrive(rond_point: RondPoint) -> None:
    # En arrivant du nord vers le centre, on roule vers le sud : la droite est à l'ouest.
    point = rond_point.branche("N").point(20.0, decalage=1.0)
    assert (point.x, point.y) == pytest.approx((-1.0, 20.0))


# ---------- Branches et segments isolés ----------

def test_branche_sans_nom_refusee() -> None:
    with pytest.raises(ValueError, match="nom"):
        Branche("", 90.0, 8)


def test_branche_sans_capacite_refusee() -> None:
    with pytest.raises(ValueError, match="capacité"):
        Branche("N", 90.0, 0)


def test_angle_de_branche_ramene_entre_0_et_360() -> None:
    assert Branche("S", -90.0, 8).angle == pytest.approx(270.0)


def test_segment_d_une_branche_vers_elle_meme_refuse() -> None:
    nord = Branche("N", 90.0, 8)
    with pytest.raises(ValueError, match="deux branches différentes"):
        Segment(nord, nord, 10.0)
