"""Tests de la section « Scénario » : composition, ordre, lancement minuté, arrêt et JSON."""

import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from outils import DELAI, attendre, attendre_qt
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from cherrypie.commun.config import Configuration
from cherrypie.commun.erreurs import ScenarioInvalideError
from cherrypie.commun.protocole import CodeNotification
from cherrypie.ihm.lanceur_clients import LanceurClients
from cherrypie.ihm.panneau_scenario import PanneauScenario
from cherrypie.ihm.scenario import LigneScenario
from cherrypie.modele.trajectoire import Etape
from cherrypie.modele.usager import Pieton, VehiculePrioritaire
from cherrypie.serveur.serveur import Serveur


@pytest.fixture
def fabrique_panneau(qapp: QApplication) -> Iterator[Callable[[Configuration], PanneauScenario]]:
    """Crée des sections, puis arrête tout ce qu'elles ont lancé à la fin du test."""
    panneaux: list[PanneauScenario] = []

    def fabriquer(config: Configuration) -> PanneauScenario:
        panneau = PanneauScenario(LanceurClients(config))
        panneaux.append(panneau)
        return panneau

    yield fabriquer
    for panneau in panneaux:
        panneau.arreter_tout()


@pytest.fixture
def panneau(fabrique_config: Callable[..., Configuration], fabrique_panneau: Callable) -> PanneauScenario:
    return fabrique_panneau(fabrique_config())


def composer(
    panneau: PanneauScenario, categorie: str, entree: str, sortie: str, nombre: int = 1, delai: float = 0.0
) -> None:
    """Remplit le formulaire puis ajoute la ligne, comme le ferait l'utilisateur."""
    panneau.choix_categorie.setCurrentIndex(panneau.choix_categorie.findData(categorie))
    panneau.choix_entree.setCurrentIndex(panneau.choix_entree.findData(entree))
    panneau.choix_sortie.setCurrentIndex(panneau.choix_sortie.findData(sortie))
    panneau.choix_nombre.setValue(nombre)
    panneau.choix_delai.setValue(delai)
    panneau.boutons["ajouter"].click()


def categories(panneau: PanneauScenario) -> list[str]:
    return [ligne.categorie for ligne in panneau.scenario.lignes]


def threads_clients() -> list[threading.Thread]:
    return [fil for fil in threading.enumerate() if fil.name.startswith("client-")]


def patienter(duree: float) -> None:
    fin = time.monotonic() + duree
    attendre_qt(lambda: time.monotonic() >= fin, delai=duree + DELAI)


# ---------- Composition ----------

def test_choix_d_apres_la_configuration(
    fabrique_config: Callable[..., Configuration], fabrique_panneau: Callable
) -> None:
    panneau = fabrique_panneau(fabrique_config(branches=["a", "b", "c"]))
    rangs = range(panneau.choix_entree.count())
    assert [panneau.choix_entree.itemText(rang) for rang in rangs] == ["Rue a", "Rue b", "Rue c"]
    assert [panneau.choix_entree.itemData(rang) for rang in rangs] == ["a", "b", "c"]
    assert panneau.choix_categorie.count() == 5


def test_ligne_ajoutee_d_apres_le_formulaire(panneau: PanneauScenario) -> None:
    composer(panneau, "voiture", "nations_sud", "albert_camus", nombre=3, delai=2.5)
    assert panneau.scenario.lignes == [LigneScenario("voiture", "nations_sud", "albert_camus", 3, 2.5)]
    assert "3 × Voiture" in panneau.liste.item(0).text()


def test_pieton_sortie_egale_a_l_entree(panneau: PanneauScenario) -> None:
    panneau.choix_categorie.setCurrentIndex(panneau.choix_categorie.findData(Pieton.CATEGORIE))
    panneau.choix_entree.setCurrentIndex(panneau.choix_entree.findData("albert_camus"))
    assert panneau.choix_sortie.currentData() == "albert_camus"
    assert not panneau.choix_sortie.isEnabled()


def test_monter_descendre_supprimer_vider(panneau: PanneauScenario) -> None:
    composer(panneau, "voiture", "nations_sud", "albert_camus")
    composer(panneau, "moto", "nations_nord", "nations_sud")
    composer(panneau, VehiculePrioritaire.CATEGORIE, "nations_sud", "nations_nord")
    panneau.liste.setCurrentRow(2)
    panneau.boutons["monter"].click()
    assert categories(panneau) == ["voiture", "vp", "moto"]
    panneau.liste.setCurrentRow(0)
    panneau.boutons["descendre"].click()
    assert categories(panneau) == ["vp", "voiture", "moto"]
    panneau.liste.setCurrentRow(2)
    panneau.boutons["supprimer"].click()
    assert categories(panneau) == ["vp", "voiture"]
    panneau.boutons["vider"].click()
    assert categories(panneau) == []


def test_premiere_ligne_ne_monte_pas_plus_haut(panneau: PanneauScenario) -> None:
    composer(panneau, "voiture", "nations_sud", "albert_camus")
    composer(panneau, "moto", "nations_nord", "nations_sud")
    panneau.liste.setCurrentRow(0)
    panneau.boutons["monter"].click()
    assert categories(panneau) == ["voiture", "moto"]


def test_ordre_affiche_fait_foi_apres_un_glisser_deposer(panneau: PanneauScenario) -> None:
    composer(panneau, "voiture", "nations_sud", "albert_camus")
    composer(panneau, "moto", "nations_nord", "nations_sud")
    # Un glisser-déposer interne déplace l'élément dans la liste, comme ici.
    panneau.liste.insertItem(0, panneau.liste.takeItem(1))
    assert categories(panneau) == ["moto", "voiture"]


# ---------- Lancement ----------

def test_lignes_lancees_dans_l_ordre_avec_leurs_delais(
    lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable
) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    composer(panneau, "voiture", "nations_sud", "albert_camus", nombre=2)
    composer(panneau, Pieton.CATEGORIE, "nations_nord", "nations_nord", nombre=3, delai=0.5)
    panneau.boutons["lancer"].click()
    QCoreApplication.processEvents()
    attendre(lambda: len(serveur.logique.registre.usagers) == 2)
    assert panneau.en_cours
    attendre_qt(lambda: len(serveur.logique.registre.usagers) == 5)
    assert not panneau.en_cours


def test_arreter_tout_annule_les_lignes_a_venir(
    lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable
) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    composer(panneau, "voiture", "nations_sud", "albert_camus")
    composer(panneau, "moto", "nations_nord", "nations_sud", delai=0.5)
    panneau.boutons["lancer"].click()
    QCoreApplication.processEvents()
    panneau.boutons["arreter"].click()
    patienter(1.0)
    assert threads_clients() == []
    assert not panneau.en_cours
    attendre(lambda: serveur.logique.registre.usagers == [])


# ---------- VP et civils de la même branche ----------

# Délai entre les voitures et le VP dans le scénario, en secondes, et durée maximale de la traversée.
DELAI_AVANT_LE_VP = 1.0
DUREE_MAX_TRAVERSEE = 30.0


@pytest.mark.lent
@pytest.mark.parametrize("sortie_du_vp", ["nations_nord", "nations_sud"], ids=["trajet-normal", "demi-tour"])
def test_vp_lance_juste_apres_des_civils_de_sa_branche(
    lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable, sortie_du_vp: str
) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    composer(panneau, "voiture", "nations_sud", "albert_camus", nombre=3)
    composer(panneau, VehiculePrioritaire.CATEGORIE, "nations_sud", sortie_du_vp, delai=DELAI_AVANT_LE_VP)
    panneau.boutons["lancer"].click()
    arretees: set[str] = set()

    def vp_sorti() -> bool:
        if serveur.logique.passages:
            return True
        for usager in serveur.logique.registre.usagers:
            if usager.CATEGORIE != "voiture":
                continue
            assert usager.etape is Etape.APPROCHE, f"{usager.identifiant} entre avant la sortie du VP"
            if usager.consigne is CodeNotification.CHANGEZ_VOIE and usager.vitesse == 0.0:
                arretees.add(usager.identifiant)
        return False

    attendre_qt(vp_sorti, delai=DUREE_MAX_TRAVERSEE)
    assert arretees == {"voiture_1", "voiture_2", "voiture_3"}


# ---------- Enregistrement ----------

def test_enregistrer_puis_charger(panneau: PanneauScenario, tmp_path: Path) -> None:
    composer(panneau, "voiture", "nations_sud", "albert_camus", nombre=2, delai=1.0)
    composer(panneau, Pieton.CATEGORIE, "nations_nord", "nations_nord")
    lignes = panneau.scenario.lignes
    chemin = tmp_path / "demo.json"
    panneau.enregistrer(chemin)
    panneau.boutons["vider"].click()
    panneau.charger(chemin)
    assert panneau.scenario.lignes == lignes
    assert panneau.liste.count() == 2


def test_fichier_invalide_laisse_la_liste_intacte(panneau: PanneauScenario, tmp_path: Path) -> None:
    composer(panneau, "voiture", "nations_sud", "albert_camus")
    chemin = tmp_path / "abime.json"
    chemin.write_text("{", encoding="utf-8")
    with pytest.raises(ScenarioInvalideError):
        panneau.charger(chemin)
    assert panneau.liste.count() == 1
