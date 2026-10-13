"""Tests de la fenêtre de supervision, en plateforme offscreen."""

import threading
from collections.abc import Callable, Iterator

import pytest
from outils import attendre, attendre_qt
from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtWidgets import QApplication, QWidget

from cherrypie.client.client_usager import EtatConnexion
from cherrypie.commun.config import Configuration
from cherrypie.ihm.fenetre_supervision import HAUTEUR_MINIMALE, LARGEUR_MINIMALE, TITRE, FenetreSupervision
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
    voiture = Voiture("voiture_1", "nations_sud", "nations_nord")
    voiture.position = Position(2.0, -40.0)
    return {
        "usagers": [voiture.vers_dict()],
        "densite": {"nations_nord": 0.0, "jean_de_la_bruyere": 0.25, "nations_sud": 0.5, "albert_camus": 0.875},
        "vp_actif": vp_actif,
        "vps": [{"id": "vp_1", "entree": "nations_sud", "sortie": "nations_nord", "eta": 4.0}] if vp_actif else [],
        "segments_reserves": ["nations_sud-jean_de_la_bruyere"] if vp_actif else [],
        "entrees_bloquees": [],
        "passages_fermes": [],
        "regulation": regulation,
    }


def visible_sans_defiler(fenetre: FenetreSupervision, element: QWidget) -> bool:
    """Indique si un élément du panneau latéral se voit en entier, sans faire défiler le panneau."""
    zone = fenetre.panneau_lateral.viewport()
    return zone.rect().contains(QRect(element.mapTo(zone, QPoint(0, 0)), element.size()))


def montre_toute_la_scene(fenetre: FenetreSupervision) -> bool:
    visible = fenetre.vue.mapToScene(fenetre.vue.viewport().rect()).boundingRect()
    cadre = fenetre.scene.sceneRect()
    return visible.width() >= cadre.width() - 1 and visible.height() >= cadre.height() - 1


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
    assert montre_toute_la_scene(fenetre)


# ---------- Tailles d'écran ----------


def test_taille_minimale_sans_taille_fixe(fenetre: FenetreSupervision) -> None:
    assert (fenetre.minimumWidth(), fenetre.minimumHeight()) == (LARGEUR_MINIMALE, HAUTEUR_MINIMALE)
    assert fenetre.maximumWidth() > LARGEUR_MINIMALE and fenetre.maximumHeight() > HAUTEUR_MINIMALE


@pytest.mark.parametrize(("largeur", "hauteur"), [(1024, 640), (1280, 720), (1440, 800)])
def test_tout_visible_sur_un_ecran_de_portable(fenetre: FenetreSupervision, largeur: int, hauteur: int) -> None:
    fenetre.resize(largeur, hauteur)
    fenetre.show()
    attendre_qt(lambda: fenetre.vue.isVisible())
    assert fenetre.size().width() == largeur and fenetre.size().height() == hauteur
    boutons = fenetre.panneau_scenario.boutons
    elements = [boutons["ajouter"], boutons["lancer"], boutons["arreter"], fenetre.case_regulation]
    # Les dispositions se recalculent dans la boucle Qt : on la laisse tourner jusqu'à ce qu'elles soient posées.
    attendre_qt(lambda: all(visible_sans_defiler(fenetre, element) for element in elements))
    assert montre_toute_la_scene(fenetre)


def test_scene_et_panneau_grandissent_ensemble(fenetre: FenetreSupervision) -> None:
    fenetre.resize(LARGEUR_MINIMALE, HAUTEUR_MINIMALE)
    fenetre.show()
    attendre_qt(lambda: fenetre.vue.isVisible())
    scene_avant, panneau_avant = fenetre.separateur.sizes()
    fenetre.resize(2 * LARGEUR_MINIMALE, HAUTEUR_MINIMALE)
    attendre_qt(lambda: fenetre.separateur.sizes()[0] > scene_avant)
    assert fenetre.separateur.sizes()[1] > panneau_avant


# ---------- STATE reçu ----------


def test_state_dessine_sur_la_scene(fenetre: FenetreSupervision) -> None:
    fenetre.reseau.etat_recu.emit(etat(vp_actif=True))
    assert list(fenetre.scene.marqueurs) == ["voiture_1"]
    assert fenetre.scene.arcs_reserves["nations_sud-jean_de_la_bruyere"].isVisible()
    assert fenetre.scene.textes_densite["albert_camus"].toPlainText() == "Rue Albert Camus\n88 % (forte)"


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


# ---------- Sections ----------


def test_sections_scenario_et_suivi(fenetre: FenetreSupervision) -> None:
    assert [fenetre.sections.tabText(rang) for rang in range(fenetre.sections.count())] == ["Scénario", "Suivi"]
    assert fenetre.sections.widget(0) is fenetre.panneau_scenario
    assert fenetre.sections.widget(1) is fenetre.panneau_suivi


def test_consigne_du_lanceur_affichee_dans_le_suivi(fenetre: FenetreSupervision) -> None:
    fenetre.lanceur.notification_recue.emit("voiture_1", "ATTENDEZ", "attendez", True)
    assert fenetre.panneau_suivi.messages.item(0).text().endswith("voiture_1 ← ATTENDEZ : attendez")


def test_evenement_du_state_affiche_dans_le_suivi(fenetre: FenetreSupervision) -> None:
    fenetre.reseau.etat_recu.emit(etat())
    fenetre.reseau.etat_recu.emit(etat(vp_actif=True))
    assert "VP annoncé : vp_1, Bd des Nations (sud) vers Bd des Nations (nord)" in fenetre.panneau_suivi.messages.item(0).text()


def test_deconnexion_n_invente_pas_d_evenement(fenetre: FenetreSupervision) -> None:
    fenetre.reseau.etat_recu.emit(etat())
    fenetre.reseau.connexion_changee.emit(EtatConnexion.DECONNECTE.value, "connexion perdue")
    fenetre.reseau.etat_recu.emit(etat(regulation=False))
    assert fenetre.panneau_suivi.messages.count() == 0


# ---------- Statistiques ----------


def test_onglet_statistiques_a_cote_du_rond_point(fenetre: FenetreSupervision) -> None:
    assert [fenetre.onglets.tabText(rang) for rang in range(fenetre.onglets.count())] == ["Rond-point", "Statistiques"]
    assert fenetre.onglets.widget(1) is fenetre.panneau_stats


def test_reponse_du_serveur_affichee_dans_l_onglet(fenetre: FenetreSupervision) -> None:
    fenetre.reseau.statistiques_recues.emit({"disponible": False, "raison": "base injoignable"})
    assert fenetre.panneau_stats.etat.text().endswith("base injoignable")


def test_ouvrir_l_onglet_demande_les_statistiques(
    lancer_serveur: Callable[..., Serveur], fabrique_fenetre: Callable
) -> None:
    serveur = lancer_serveur()
    fenetre = fabrique_fenetre(serveur.config)
    fenetre.demarrer()
    attendre_qt(lambda: fenetre.case_regulation.isEnabled())
    fenetre.onglets.setCurrentWidget(fenetre.panneau_stats)
    attendre_qt(lambda: "traversée(s) de VP" in fenetre.panneau_stats.etat.text())


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
    panneau = fenetre.panneau_scenario
    panneau.choix_nombre.setValue(3)
    panneau.ajouter()
    panneau.choix_categorie.setCurrentIndex(panneau.choix_categorie.findData(VehiculePrioritaire.CATEGORIE))
    panneau.choix_nombre.setValue(1)
    panneau.ajouter()
    # Une ligne lancée bien plus tard : la fermeture doit aussi l'annuler.
    panneau.choix_delai.setValue(60.0)
    panneau.ajouter()
    panneau.lancer()
    attendre_qt(lambda: bool(fenetre.scene.marqueurs))
    fenetre.close()
    assert fenetre.fil.isFinished()
    assert not panneau.en_cours
    assert threads_clients() == []
    attendre(lambda: serveur.logique.registre.usagers == [] and serveur.logique.superviseurs() == [])
