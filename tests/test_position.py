"""Tests de la position d'un point."""

import dataclasses

import pytest

from cherrypie.modele.position import Position


# ---------- Distance ----------

def test_distance_entre_deux_points() -> None:
    assert Position(0.0, 0.0).distance(Position(3.0, 4.0)) == pytest.approx(5.0)


def test_distance_symetrique() -> None:
    depart, arrivee = Position(-2.0, 7.5), Position(10.0, -1.0)
    assert depart.distance(arrivee) == pytest.approx(arrivee.distance(depart))


def test_distance_a_soi_meme_nulle() -> None:
    assert Position(12.5, -3.0).distance(Position(12.5, -3.0)) == pytest.approx(0.0)


# ---------- Valeurs refusées ----------

@pytest.mark.parametrize("x", [float("nan"), float("inf")], ids=["nan", "infini"])
def test_coordonnee_non_finie_refusee(x: float) -> None:
    with pytest.raises(ValueError, match="fini"):
        Position(x, 0.0)


@pytest.mark.parametrize("y", ["3.5", None, True], ids=["texte", "none", "booleen"])
def test_coordonnee_non_numerique_refusee(y: object) -> None:
    with pytest.raises(TypeError, match="nombre"):
        Position(0.0, y)


def test_position_non_modifiable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        Position(1.0, 2.0).x = 5.0
