"""Tests de la scène 2D : dessin du rond-point d'après la configuration, puis affichage d'un STATE."""

import pytest
from geometrie import rond_point_a_trois_branches, rond_point_bel_air
from PyQt6.QtWidgets import QApplication

from cherrypie.commun.protocole import CodeNotification
from cherrypie.ihm.scene_rond_point import SceneRondPoint
from cherrypie.ihm.style import (
    COULEUR_CONTOUR_USAGER,
    COULEURS_CATEGORIE,
    COULEURS_CONSIGNE,
    COULEURS_DENSITE,
    GABARITS_CATEGORIE,
    MARGE_SCENE,
)
from cherrypie.modele.position import Position
from cherrypie.modele.usager import KMH, Pieton, Usager, VehiculePrioritaire, Voiture
from cherrypie.serveur.densite import NiveauDensite

LIBELLES = ["Bd des Nations (nord)", "Rue Jean de la Bruyère", "Bd des Nations (sud)", "Rue Albert Camus"]


@pytest.fixture
def scene(qapp: QApplication) -> SceneRondPoint:
    return SceneRondPoint(rond_point_bel_air())


# ---------- Repère ----------


def test_vers_scene_inverse_les_ordonnees() -> None:
    point = SceneRondPoint.vers_scene(Position(3.0, 4.0))
    assert (point.x(), point.y()) == pytest.approx((3.0, -4.0))


def test_scene_englobe_le_bout_de_chaque_chaussee_et_la_marge(scene: SceneRondPoint) -> None:
    rond_point = scene.rond_point
    cadre = scene.sceneRect().adjusted(MARGE_SCENE, MARGE_SCENE, -MARGE_SCENE, -MARGE_SCENE)
    extremite = rond_point.rayon_bord + rond_point.longueur_branche
    for branche in rond_point.branches:
        for cote in (1, -1):
            coin = SceneRondPoint.vers_scene(branche.point(extremite, cote * branche.demi_largeur))
            assert cadre.adjusted(-1e-6, -1e-6, 1e-6, 1e-6).contains(coin)


def test_scene_ajustee_au_dessin(scene: SceneRondPoint) -> None:
    # Le cadre suit les branches réelles : il n'est plus le carré qui engloberait des branches à 90°.
    cadre = scene.sceneRect()
    assert cadre.width() != pytest.approx(cadre.height())


# ---------- Branches ----------


def test_scene_une_bande_et_un_texte_par_branche(scene: SceneRondPoint) -> None:
    assert list(scene.bandes_densite) == ["nations_nord", "jean_de_la_bruyere", "nations_sud", "albert_camus"]
    textes = [texte.toPlainText() for texte in scene.textes_densite.values()]
    assert textes == LIBELLES


def test_scene_bandes_de_densite_faible_au_depart(scene: SceneRondPoint) -> None:
    couleurs = {bande.pen().color().name() for bande in scene.bandes_densite.values()}
    assert couleurs == {COULEURS_DENSITE[NiveauDensite.FAIBLE].name()}


def test_scene_nord_en_haut(scene: SceneRondPoint) -> None:
    textes = scene.textes_densite
    assert textes["nations_nord"].pos().y() < 0 < textes["nations_sud"].pos().y()
    assert textes["albert_camus"].pos().x() < 0 < textes["jean_de_la_bruyere"].pos().x()


def test_scene_suit_le_nombre_de_branches(qapp: QApplication) -> None:
    scene = SceneRondPoint(rond_point_a_trois_branches())
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
    passages_fermes: list[dict] | None = None,
) -> dict:
    """Données d'un STATE, vides par défaut."""
    return {
        "usagers": usagers or [],
        "densite": densite or {},
        "vp_actif": False,
        "segments_reserves": segments_reserves or [],
        "entrees_bloquees": entrees_bloquees or [],
        "passages_fermes": passages_fermes or [],
        "regulation": True,
    }


def test_usager_place_a_sa_position(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Voiture("voiture_1", "nations_sud", "nations_nord"), 10.0, -30.0)]))
    marqueur = scene.marqueurs["voiture_1"]
    assert (marqueur.pos().x(), marqueur.pos().y()) == pytest.approx((10.0, 30.0))
    assert marqueur.brush().color() == COULEURS_CATEGORIE["voiture"]


@pytest.mark.parametrize(("cap", "rotation"), [(90.0, 0.0), (0.0, -90.0), (230.0, 140.0)], ids=["est", "nord", "camus"])
def test_silhouette_tournee_dans_le_sens_de_marche(scene: SceneRondPoint, cap: float, rotation: float) -> None:
    voiture = Voiture("voiture_1", "nations_sud", "nations_nord")
    voiture.cap = cap
    scene.afficher_etat(etat([decrire(voiture)]))
    assert scene.marqueurs["voiture_1"].rotation() == pytest.approx(rotation)


def test_avant_du_vehicule_sur_sa_position(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Voiture("voiture_1", "nations_sud", "nations_nord"))]))
    carrosserie = scene.marqueurs["voiture_1"].path().boundingRect()
    longueur, largeur = GABARITS_CATEGORIE["voiture"]
    assert (carrosserie.left(), carrosserie.right()) == pytest.approx((-longueur, 0.0))
    assert carrosserie.height() == pytest.approx(largeur)


def test_pieton_centre_sur_sa_position(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Pieton("pieton_1", "nations_nord", "nations_nord"))]))
    silhouette = scene.marqueurs["pieton_1"].path().boundingRect()
    assert (silhouette.center().x(), silhouette.center().y()) == pytest.approx((0.0, 0.0))


def test_usager_suivi_d_un_state_a_l_autre(scene: SceneRondPoint) -> None:
    voiture = Voiture("voiture_1", "nations_sud", "nations_nord")
    scene.afficher_etat(etat([decrire(voiture, 10.0, -30.0)]))
    premier = scene.marqueurs["voiture_1"]
    scene.afficher_etat(etat([decrire(voiture, 10.0, -25.0)]))
    assert scene.marqueurs["voiture_1"] is premier
    assert premier.pos().y() == pytest.approx(25.0)


def test_usager_sans_position_pas_affiche(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Voiture("voiture_1", "nations_sud", "nations_nord"), x=None)]))
    assert scene.marqueurs == {}


def test_usager_parti_retire_de_la_scene(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Voiture("voiture_1", "nations_sud", "nations_nord"))]))
    marqueur = scene.marqueurs["voiture_1"]
    scene.afficher_etat(etat())
    assert scene.marqueurs == {}
    assert marqueur.scene() is None


def test_vp_plus_gros_avec_halo_au_dessus(scene: SceneRondPoint) -> None:
    voiture = decrire(Voiture("voiture_1", "nations_sud", "nations_nord"))
    scene.afficher_etat(etat([voiture, decrire(VehiculePrioritaire("vp_1", "nations_sud", "nations_nord"))]))
    voiture, vp = scene.marqueurs["voiture_1"], scene.marqueurs["vp_1"]
    assert vp.path().boundingRect().width() > voiture.path().boundingRect().width()
    assert vp.zValue() > voiture.zValue()
    assert vp.halo is not None and voiture.halo is None


def test_consigne_affichee_par_le_contour(scene: SceneRondPoint) -> None:
    voiture = Voiture("voiture_1", "nations_sud", "nations_nord")
    scene.afficher_etat(etat([decrire(voiture, consigne=CodeNotification.ATTENDEZ)]))
    marqueur = scene.marqueurs["voiture_1"]
    assert marqueur.pen().color() == COULEURS_CONSIGNE["ATTENDEZ"]
    assert "ATTENDEZ" in marqueur.toolTip()


def test_sans_consigne_contour_neutre(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat([decrire(Voiture("voiture_1", "nations_sud", "nations_nord"))]))
    assert scene.marqueurs["voiture_1"].pen().color() == COULEUR_CONTOUR_USAGER


def test_infobulle_avec_trajet_et_vitesse(scene: SceneRondPoint) -> None:
    voiture = Voiture("voiture_1", "nations_sud", "nations_nord")
    voiture.vitesse = 18 * KMH
    scene.afficher_etat(etat([decrire(voiture)]))
    infobulle = scene.marqueurs["voiture_1"].toolTip()
    assert "de Bd des Nations (sud) vers Bd des Nations (nord)" in infobulle and "18 km/h" in infobulle


def test_segments_reserves_surlignes(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat(segments_reserves=["nations_sud-jean_de_la_bruyere", "jean_de_la_bruyere-nations_nord"]))
    visibles = {nom for nom, arc in scene.arcs_reserves.items() if arc.isVisible()}
    assert visibles == {"nations_sud-jean_de_la_bruyere", "jean_de_la_bruyere-nations_nord"}
    scene.afficher_etat(etat())
    assert not any(arc.isVisible() for arc in scene.arcs_reserves.values())


def test_entrees_bloquees_signalees_par_une_barre_et_un_feu(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat(entrees_bloquees=["jean_de_la_bruyere"]))
    visibles = {nom for nom, marque in scene.entrees_temporisees.items() if marque.isVisible()}
    assert visibles == {"jean_de_la_bruyere"}
    assert len(scene.entrees_temporisees["jean_de_la_bruyere"].childItems()) == 2


def test_passage_ferme_par_une_barriere_sur_sa_seule_chaussee(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat(passages_fermes=[{"branche": "nations_nord", "chaussee": "sortie"}]))
    visibles = {cle for cle, barriere in scene.passages_fermes.items() if barriere.isVisible()}
    assert visibles == {("nations_nord", "sortie")}
    scene.afficher_etat(etat())
    assert not any(barriere.isVisible() for barriere in scene.passages_fermes.values())


def test_densite_forte_coloree_et_ecrite(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat(densite={"nations_nord": 0.25, "nations_sud": 0.875}))
    assert scene.bandes_densite["nations_sud"].pen().color() == COULEURS_DENSITE[NiveauDensite.FORTE]
    assert scene.bandes_densite["nations_nord"].pen().color() == COULEURS_DENSITE[NiveauDensite.FAIBLE]
    assert scene.textes_densite["nations_sud"].toPlainText() == "Bd des Nations (sud)\n88 % (forte)"


def test_branche_inconnue_ignoree(scene: SceneRondPoint) -> None:
    scene.afficher_etat(etat(densite={"X": 0.5}, segments_reserves=["X-N"], entrees_bloquees=["X"]))
    assert all(bande.pen().color() == COULEURS_DENSITE[NiveauDensite.FAIBLE] for bande in scene.bandes_densite.values())
