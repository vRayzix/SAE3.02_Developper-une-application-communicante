"""Tests de la fenêtre de supervision, en plateforme offscreen."""

import threading
from collections.abc import Callable, Iterator

import pytest
from outils import attendre, attendre_qt
from PyQt6.QtWidgets import QApplication

from cherrypie.client.client_usager import EtatConnexion
from cherrypie.commun.config import Configuration
from cherrypie.ihm.fenetre_supervision import NOMBRE_MAX_CONSIGNES, TITRE, FenetreSupervision
from cherrypie.modele.position import Position
from cherrypie.modele.usager import VehiculePrioritaire, Voiture
from cherrypie.serveur.serveur import Serveur


@pytest.fixture
def fabrique_fenetre(qapp: QApplication) -> Iterator[Callable[[Configuration], FenetreSupervision]]:
    """Crée des fenêtres, puis les ferme à la fin du test, ce qui arrête leurs threads."""
    fenetres: list[FenetreSupervision] = []

    def fabriquer(config: Configuration) -> FenetreSupervision:
        fenetre = FenetreSupervision(config)
        fenetres.append(fenetre)
        return fenetre

    yield fabriquer
    for fenetre in fenetres:
        fenetre.close()


@pytest.fixture
def fenetre(fabrique_config: Callable[..., Configuration], fabrique_fenetre: Callable) -> FenetreSupervision:
    """Fenêtre dont le réseau n'est pas démarré : les signaux sont émis à la main."""
    return fabrique_fenetre(fabrique_config())


def etat(regulation: bool = True, vp_actif: bool = False) -> dict:
    """Données d'un STATE avec une voiture en approche sur la branche sud."""
    voiture = Voiture("voiture_1", "S", "N")
    voiture.position = Position(2.0, -40.0)
    return {
        "usagers": [voiture.vers_dict()],
        "densite": {"N": 0.0, "E": 0.25, "S": 0.5, "O": 0.875},
        "vp_actif": vp_actif,
        "segments_reserves": ["S-E"] if vp_actif else [],
        "entrees_bloquees": [],
        "regulation": regulation,
    }


def threads_clients() -> list[threading.Thread]:
    return [fil for fil in threading.enumerate() if fil.name.startswith("client-")]


# ---------- Fumée ----------


def test_fenetre_construite_et_affichee(fenetre: FenetreSupervision) -> None:
    fenetre.show()
    assert fenetre.windowTitle() == TITRE
    assert fenetre.onglets.tabText(0) == "Rond-point"
    assert not fenetre.case_regulation.isEnabled()
    assert fenetre.legende.libelles


def test_vue_montre_tout_le_rond_point(fenetre: FenetreSupervision) -> None:
    fenetre.show()
    attendre_qt(lambda: fenetre.vue.isVisible())
    visible = fenetre.vue.mapToScene(fenetre.vue.viewport().rect()).boundingRect()
    cadre = fenetre.scene.sceneRect()
    assert visible.width() >= cadre.width() - 1 and visible.height() >= cadre.height() - 1


# ---------- STATE reçu ----------


def test_state_dessine_sur_la_scene(fenetre: FenetreSupervision) -> None:
    fenetre.reseau.etat_recu.emit(etat(vp_actif=True))
    assert list(fenetre.scene.marqueurs) == ["voiture_1"]
    assert fenetre.scene.arcs_reserves["S-E"].isVisible()
    assert fenetre.scene.textes_densite["O"].toPlainText() == "O\n88 % forte"


def test_indicateurs_d_apres_le_state(fenetre: FenetreSupervision) -> None:
    fenetre.reseau.etat_recu.emit(etat(regulation=False, vp_actif=True))
    assert fenetre.indicateur_regulation.text() == "inactive"
    assert fenetre.indicateur_vp.text() == "en traversée"


def test_case_alignee_sur_le_premier_state_apres_connexion(fenetre: FenetreSupervision) -> None:
    fenetre.reseau.connexion_changee.emit(EtatConnexion.CONNECTE.value, "abonnée")
    assert fenetre.case_regulation.isEnabled()
    fenetre.reseau.etat_recu.emit(etat(regulation=False))
    assert not fenetre.case_regulation.isChecked()
    # Ensuite seul l'indicateur suit le serveur : la case reste la demande de l'utilisateur.
    fenetre.reseau.etat_recu.emit(etat(regulation=True))
    assert not fenetre.case_regulation.isChecked()
    assert fenetre.indicateur_regulation.text() == "active"


def test_deconnexion_desactive_la_case(fenetre: FenetreSupervision) -> None:
    fenetre.reseau.connexion_changee.emit(EtatConnexion.CONNECTE.value, "abonnée")
    fenetre.reseau.etat_recu.emit(etat())
    fenetre.reseau.connexion_changee.emit(EtatConnexion.DECONNECTE.value, "connexion perdue")
    assert not fenetre.case_regulation.isEnabled()
    assert fenetre.indicateur_regulation.text() == "inconnue"
    assert fenetre.etat_connexion.toolTip() == "connexion perdue"


# ---------- Dernières consignes ----------


def test_consigne_ajoutee_en_haut(fenetre: FenetreSupervision) -> None:
    fenetre.panneau_creation.notification_recue.emit("voiture_1", "ATTENDEZ", "attendez", True)
    fenetre.panneau_creation.notification_recue.emit("moto_1", "DEGAGEZ", "dégagez", False)
    assert fenetre.consignes.item(0).text().endswith("moto_1 : DEGAGEZ (ignorée)")
    assert fenetre.consignes.item(1).toolTip() == "attendez"


def test_consignes_les_plus_anciennes_oubliees(fenetre: FenetreSupervision) -> None:
    for numero in range(NOMBRE_MAX_CONSIGNES + 5):
        fenetre.panneau_creation.notification_recue.emit(f"voiture_{numero}", "ATTENDEZ", "", True)
    assert fenetre.consignes.count() == NOMBRE_MAX_CONSIGNES
    assert f"voiture_{NOMBRE_MAX_CONSIGNES + 4} " in fenetre.consignes.item(0).text()


# ---------- Avec un vrai serveur ----------


def test_interrupteur_coupe_la_regulation(lancer_serveur: Callable[..., Serveur], fabrique_fenetre: Callable) -> None:
    serveur = lancer_serveur()
    fenetre = fabrique_fenetre(serveur.config)
    fenetre.show()
    fenetre.demarrer()
    attendre_qt(lambda: fenetre.case_regulation.isEnabled() and fenetre.indicateur_regulation.text() == "active")
    # click() émet les mêmes signaux qu'un clic de l'utilisateur sur la case.
    fenetre.case_regulation.click()
    attendre(lambda: serveur.logique.regulation_active is False)
    attendre_qt(lambda: fenetre.indicateur_regulation.text() == "inactive")


def test_fermeture_arrete_tous_les_threads(lancer_serveur: Callable[..., Serveur], fabrique_fenetre: Callable) -> None:
    serveur = lancer_serveur()
    fenetre = fabrique_fenetre(serveur.config)
    fenetre.show()
    fenetre.demarrer()
    panneau = fenetre.panneau_creation
    panneau.choix_nombre.setValue(3)
    panneau.lancer()
    panneau.choix_categorie.setCurrentIndex(panneau.choix_categorie.findData(VehiculePrioritaire.CATEGORIE))
    panneau.choix_nombre.setValue(1)
    panneau.lancer()
    attendre_qt(lambda: bool(fenetre.scene.marqueurs))
    fenetre.close()
    assert fenetre.fil.isFinished()
    assert threads_clients() == []
    attendre(lambda: serveur.logique.registre.usagers == [] and serveur.logique.superviseurs() == [])
