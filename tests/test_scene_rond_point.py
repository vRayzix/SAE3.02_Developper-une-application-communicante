"""Tests de la scène 2D : dessin du rond-point d'après la configuration."""

import pytest
from PyQt6.QtWidgets import QApplication

from cherrypie.ihm.scene_rond_point import SceneRondPoint
from cherrypie.ihm.style import COULEURS_DENSITE, MARGE_SCENE
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import LONGUEUR_BRANCHE
from cherrypie.serveur.densite import NiveauDensite

RAYON = 20.0


@pytest.fixture
def scene(qapp: QApplication) -> SceneRondPoint:
    return SceneRondPoint(RondPoint(["N", "E", "S", "O"], RAYON, 8))


# ---------- Repère ----------


def test_vers_scene_inverse_les_ordonnees() -> None:
    point = SceneRondPoint.vers_scene(Position(3.0, 4.0))
    assert (point.x(), point.y()) == pytest.approx((3.0, -4.0))


def test_scene_englobe_les_branches_et_la_marge(scene: SceneRondPoint) -> None:
    demi_cote = RAYON + LONGUEUR_BRANCHE + MARGE_SCENE
    cadre = scene.sceneRect()
    assert (cadre.left(), cadre.top(), cadre.width()) == pytest.approx((-demi_cote, -demi_cote, 2 * demi_cote))


# ---------- Branches ----------


def test_scene_une_bande_et_un_texte_par_branche(scene: SceneRondPoint) -> None:
    assert list(scene.bandes_densite) == ["N", "E", "S", "O"]
    assert [texte.text() for texte in scene.textes_densite.values()] == ["N", "E", "S", "O"]


def test_scene_bandes_de_densite_faible_au_depart(scene: SceneRondPoint) -> None:
    couleurs = {bande.pen().color().name() for bande in scene.bandes_densite.values()}
    assert couleurs == {COULEURS_DENSITE[NiveauDensite.FAIBLE].name()}


def test_scene_nord_en_haut(scene: SceneRondPoint) -> None:
    textes = scene.textes_densite
    assert textes["N"].pos().y() < 0 < textes["S"].pos().y()
    assert textes["O"].pos().x() < 0 < textes["E"].pos().x()


def test_scene_suit_le_nombre_de_branches(qapp: QApplication) -> None:
    scene = SceneRondPoint(RondPoint(["A", "B", "C"], RAYON, 8))
    assert len(scene.bandes_densite) == 3
