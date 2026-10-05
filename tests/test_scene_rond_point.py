"""Tests de la scène 2D : dessin du rond-point d'après la configuration."""

import pytest
from PyQt6.QtWidgets import QApplication

from cherrypie.commun.protocole import CodeNotification
from cherrypie.ihm.scene_rond_point import SceneRondPoint
from cherrypie.ihm.style import (
    COULEUR_CONTOUR_USAGER,
    COULEURS_CATEGORIE,
    COULEURS_CONSIGNE,
    COULEURS_DENSITE,
    MARGE_SCENE,
)
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import LONGUEUR_BRANCHE
from cherrypie.modele.usager import KMH, Usager, VehiculePrioritaire, Voiture
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
    assert [texte.toPlainText() for texte in scene.textes_densite.values()] == ["N", "E", "S", "O"]


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


# ---------- Affichage d'un STATE ----------


def decrire(usager: Usager, x: float | None = 10.0, y: float = -30.0, consigne: CodeNotification | None = None) -> dict:
    """Décrit un usager comme le fait le STATE, à une position donnée (x à None : position inconnue)."""
    if x is not None:
        usager.position = Position(x, y)
    if consigne is not None:
        usager.reagir(consigne)
    return usager.vers_dict()


def etat(
    usagers: list[dict] | None = None,
    densite: dict[str, float] | None = None,
    segments_reserves: list[str] | None = None,
    entrees_bloquees: list[str] | None = None,
) -> dict:
    """Données d'un STATE, vides par défaut."""
    return {
        "usagers": usagers or [],
        "densite": densite or {},
        "vp_actif": False,
        "segments_reserves": segments_reserves or [],
        "entrees_bloquees": entrees_bloquees or [],
        "regulation": True,
    }


def test_usager_place_a_sa_position(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Voiture("voiture_1", "S", "N"), 10.0, -30.0)]))
    marqueur = scene.marqueurs["voiture_1"]
    assert (marqueur.pos().x(), marqueur.pos().y()) == pytest.approx((10.0, 30.0))
    assert marqueur.brush().color() == COULEURS_CATEGORIE["voiture"]


def test_usager_suivi_d_un_state_a_l_autre(scene: SceneRondPoint) -> None:
    voiture = Voiture("voiture_1", "S", "N")
    scene.afficher_etat(etat([decrire(voiture, 10.0, -30.0)]))
    premier = scene.marqueurs["voiture_1"]
    scene.afficher_etat(etat([decrire(voiture, 10.0, -25.0)]))
    assert scene.marqueurs["voiture_1"] is premier
    assert premier.pos().y() == pytest.approx(25.0)


def test_usager_sans_position_pas_affiche(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Voiture("voiture_1", "S", "N"), x=None)]))
    assert scene.marqueurs == {}


def test_usager_parti_retire_de_la_scene(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Voiture("voiture_1", "S", "N"))]))
    marqueur = scene.marqueurs["voiture_1"]
    scene.afficher_etat(etat())
    assert scene.marqueurs == {}
    assert marqueur.scene() is None


def test_vp_plus_gros_avec_halo_au_dessus(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Voiture("voiture_1", "S", "N")), decrire(VehiculePrioritaire("vp_1", "S", "N"))]))
    voiture, vp = scene.marqueurs["voiture_1"], scene.marqueurs["vp_1"]
    assert vp.rect().width() > voiture.rect().width()
    assert vp.zValue() > voiture.zValue()
    assert vp.halo is not None and voiture.halo is None


def test_consigne_affichee_par_le_contour(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Voiture("voiture_1", "S", "N"), consigne=CodeNotification.ATTENDEZ)]))
    marqueur = scene.marqueurs["voiture_1"]
    assert marqueur.pen().color() == COULEURS_CONSIGNE["ATTENDEZ"]
    assert "ATTENDEZ" in marqueur.toolTip()


def test_sans_consigne_contour_neutre(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Voiture("voiture_1", "S", "N"))]))
    assert scene.marqueurs["voiture_1"].pen().color() == COULEUR_CONTOUR_USAGER


def test_infobulle_avec_trajet_et_vitesse(scene: SceneRondPoint) -> None:
    voiture = Voiture("voiture_1", "S", "N")
    voiture.vitesse = 18 * KMH
    scene.afficher_etat(etat([decrire(voiture)]))
    infobulle = scene.marqueurs["voiture_1"].toolTip()
    assert "de S vers N" in infobulle and "18 km/h" in infobulle


def test_segments_reserves_surlignes(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat(segments_reserves=["S-E", "E-N"]))
    visibles = {nom for nom, arc in scene.arcs_reserves.items() if arc.isVisible()}
    assert visibles == {"S-E", "E-N"}
    scene.afficher_etat(etat())
    assert not any(arc.isVisible() for arc in scene.arcs_reserves.values())


def test_entrees_bloquees_signalees_par_un_feu(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat(entrees_bloquees=["E"]))
    visibles = {nom for nom, feu in scene.feux_entree.items() if feu.isVisible()}
    assert visibles == {"E"}


def test_densite_forte_coloree_et_ecrite(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat(densite={"N": 0.25, "S": 0.875}))
    assert scene.bandes_densite["S"].pen().color() == COULEURS_DENSITE[NiveauDensite.FORTE]
    assert scene.bandes_densite["N"].pen().color() == COULEURS_DENSITE[NiveauDensite.FAIBLE]
    assert scene.textes_densite["S"].toPlainText() == "S\n88 % forte"


def test_branche_inconnue_ignoree(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat(densite={"X": 0.5}, segments_reserves=["X-N"], entrees_bloquees=["X"]))
    assert all(bande.pen().color() == COULEURS_DENSITE[NiveauDensite.FAIBLE] for bande in scene.bandes_densite.values())
