"""Tests du panneau de création : choix de l'usager, lancement de clients locaux et arrêt propre."""

import threading
from collections.abc import Callable, Iterator

import pytest
from outils import DELAI, attendre, attendre_qt
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from cherrypie.client.client_usager import EtatConnexion
from cherrypie.commun.config import Configuration
from cherrypie.ihm.panneau_creation import COLONNE_CONNEXION, COLONNE_CONSIGNE, COLONNE_TRAJET, PanneauCreation
from cherrypie.ihm.style import LIBELLES_CONNEXION
from cherrypie.modele.usager import Pieton, VehiculePrioritaire
from cherrypie.serveur.serveur import Serveur


@pytest.fixture
def fabrique_panneau(qapp: QApplication) -> Iterator[Callable[[Configuration], PanneauCreation]]:
    """Crée des panneaux, puis arrête leurs clients à la fin du test."""
    panneaux: list[PanneauCreation] = []

    def fabriquer(config: Configuration) -> PanneauCreation:
        panneau = PanneauCreation(config)
        panneaux.append(panneau)
        return panneau

    yield fabriquer
    for panneau in panneaux:
        panneau.arreter_clients(DELAI)


def choisir(panneau: PanneauCreation, categorie: str, entree: str, sortie: str | None = None) -> None:
    panneau.choix_categorie.setCurrentIndex(panneau.choix_categorie.findData(categorie))
    panneau.choix_entree.setCurrentIndex(panneau.choix_entree.findData(entree))
    if sortie is not None:
        panneau.choix_sortie.setCurrentIndex(panneau.choix_sortie.findData(sortie))


def threads_clients() -> list[threading.Thread]:
    return [fil for fil in threading.enumerate() if fil.name.startswith("client-")]


# ---------- Choix ----------


def test_choix_d_apres_la_configuration(
    fabrique_config: Callable[..., Configuration], fabrique_panneau: Callable
) -> None:
    panneau = fabrique_panneau(fabrique_config(branches=["a", "b", "c"]))
    rangs = range(panneau.choix_entree.count())
    assert [panneau.choix_entree.itemText(rang) for rang in rangs] == ["Rue a", "Rue b", "Rue c"]
    assert [panneau.choix_entree.itemData(rang) for rang in rangs] == ["a", "b", "c"]
    assert panneau.choix_categorie.count() == 5


def test_pieton_sortie_egale_a_l_entree(
    fabrique_config: Callable[..., Configuration], fabrique_panneau: Callable
) -> None:
    panneau = fabrique_panneau(fabrique_config())
    choisir(panneau, Pieton.CATEGORIE, "jean_de_la_bruyere")
    assert panneau.choix_sortie.currentData() == "jean_de_la_bruyere"
    assert not panneau.choix_sortie.isEnabled()
    panneau.choix_entree.setCurrentIndex(panneau.choix_entree.findData("albert_camus"))
    assert panneau.choix_sortie.currentData() == "albert_camus"


def test_vehicule_sortie_libre(fabrique_config: Callable[..., Configuration], fabrique_panneau: Callable) -> None:
    panneau = fabrique_panneau(fabrique_config())
    choisir(panneau, Pieton.CATEGORIE, "jean_de_la_bruyere")
    choisir(panneau, VehiculePrioritaire.CATEGORIE, "nations_sud", "nations_nord")
    assert panneau.choix_sortie.isEnabled()
    assert panneau.choix_sortie.currentData() == "nations_nord"


# ---------- Lancement ----------


def test_clic_lance_un_client_inscrit_au_serveur(
    lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable
) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    choisir(panneau, VehiculePrioritaire.CATEGORIE, "nations_sud", "nations_nord")
    QTest.mouseClick(panneau.bouton_lancer, Qt.MouseButton.LeftButton)
    (client,) = panneau.clients
    usager = client.usager
    assert (usager.identifiant, usager.branche_entree, usager.branche_sortie) == ("vp_1", "nations_sud", "nations_nord")
    attendre(lambda: serveur.logique.registre.contient("vp_1"))
    ligne = panneau.liste_clients.topLevelItem(0)
    attendre_qt(lambda: ligne.text(COLONNE_CONNEXION) == LIBELLES_CONNEXION[EtatConnexion.CONNECTE])


def test_trajet_affiche_avec_les_noms_de_rues(
    lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable
) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    choisir(panneau, "voiture", "nations_sud", "albert_camus")
    panneau.lancer()
    choisir(panneau, Pieton.CATEGORIE, "nations_nord")
    panneau.lancer()
    trajets = [panneau.liste_clients.topLevelItem(rang).text(COLONNE_TRAJET) for rang in range(2)]
    assert trajets == ["Bd des Nations (sud) vers Rue Albert Camus", "traverse Bd des Nations (nord)"]


def test_identifiants_uniques_par_categorie(lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    panneau.choix_nombre.setValue(3)
    panneau.lancer()
    panneau.lancer()
    identifiants = [client.usager.identifiant for client in panneau.clients]
    assert identifiants == [f"voiture_{numero}" for numero in range(1, 7)]
    attendre(lambda: len(serveur.logique.registre.usagers) == 6)


def test_pieton_lance(lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    choisir(panneau, Pieton.CATEGORIE, "nations_nord")
    (client,) = panneau.lancer()
    assert isinstance(client.usager, Pieton)
    attendre(lambda: serveur.logique.registre.contient("pieton_1"))


def test_consigne_affichee_et_relayee(lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    consignes: list[tuple] = []
    panneau.notification_recue.connect(lambda *recue: consignes.append(recue))
    choisir(panneau, "voiture", "jean_de_la_bruyere", "albert_camus")
    panneau.lancer()
    # Un VP qui va de S à N passe devant l'entrée E : la voiture doit attendre.
    choisir(panneau, VehiculePrioritaire.CATEGORIE, "nations_sud", "nations_nord")
    panneau.lancer()
    attendre_qt(lambda: ("voiture_1", "ATTENDEZ") in [recue[:2] for recue in consignes])
    ligne = panneau.liste_clients.topLevelItem(0)
    attendre_qt(lambda: ligne.text(COLONNE_CONSIGNE) == "ATTENDEZ")


def test_client_termine_retire_de_la_liste(
    lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable
) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    (client,) = panneau.lancer()
    client.arreter()
    attendre_qt(lambda: panneau.liste_clients.topLevelItemCount() == 0)


# ---------- Arrêt ----------


def test_arret_ne_laisse_aucun_thread_client(
    lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable
) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    panneau.choix_nombre.setValue(4)
    panneau.lancer()
    attendre(lambda: len(serveur.logique.registre.usagers) == 4)
    panneau.arreter_clients(DELAI)
    assert threads_clients() == []
    attendre(lambda: serveur.logique.registre.usagers == [])
