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
from cherrypie.ihm.panneau_creation import COLONNE_CONNEXION, COLONNE_CONSIGNE, PanneauCreation
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
    panneau.choix_entree.setCurrentText(entree)
    if sortie is not None:
        panneau.choix_sortie.setCurrentText(sortie)


def threads_clients() -> list[threading.Thread]:
    return [fil for fil in threading.enumerate() if fil.name.startswith("client-")]


# ---------- Choix ----------


def test_choix_d_apres_la_configuration(fabrique_config: Callable[..., Configuration], fabrique_panneau: Callable) -> None:
    panneau = fabrique_panneau(fabrique_config(branches="A, B, C"))
    entrees = [panneau.choix_entree.itemText(rang) for rang in range(panneau.choix_entree.count())]
    assert entrees == ["A", "B", "C"]
    assert panneau.choix_categorie.count() == 5


def test_pieton_sortie_egale_a_l_entree(fabrique_config: Callable[..., Configuration], fabrique_panneau: Callable) -> None:
    panneau = fabrique_panneau(fabrique_config())
    choisir(panneau, Pieton.CATEGORIE, "E")
    assert panneau.choix_sortie.currentText() == "E"
    assert not panneau.choix_sortie.isEnabled()
    panneau.choix_entree.setCurrentText("O")
    assert panneau.choix_sortie.currentText() == "O"


def test_vehicule_sortie_libre(fabrique_config: Callable[..., Configuration], fabrique_panneau: Callable) -> None:
    panneau = fabrique_panneau(fabrique_config())
    choisir(panneau, Pieton.CATEGORIE, "E")
    choisir(panneau, VehiculePrioritaire.CATEGORIE, "S", "N")
    assert panneau.choix_sortie.isEnabled()
    assert panneau.choix_sortie.currentText() == "N"


# ---------- Lancement ----------


def test_clic_lance_un_client_inscrit_au_serveur(lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    choisir(panneau, VehiculePrioritaire.CATEGORIE, "S", "N")
    QTest.mouseClick(panneau.bouton_lancer, Qt.MouseButton.LeftButton)
    (client,) = panneau.clients
    assert (client.usager.identifiant, client.usager.branche_entree, client.usager.branche_sortie) == ("vp_1", "S", "N")
    attendre(lambda: serveur.logique.registre.contient("vp_1"))
    ligne = panneau.liste_clients.topLevelItem(0)
    attendre_qt(lambda: ligne.text(COLONNE_CONNEXION) == LIBELLES_CONNEXION[EtatConnexion.CONNECTE])


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
    choisir(panneau, Pieton.CATEGORIE, "N")
    (client,) = panneau.lancer()
    assert isinstance(client.usager, Pieton)
    attendre(lambda: serveur.logique.registre.contient("pieton_1"))


def test_consigne_affichee_et_relayee(lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    consignes: list[tuple] = []
    panneau.notification_recue.connect(lambda *recue: consignes.append(recue))
    choisir(panneau, "voiture", "E", "O")
    panneau.lancer()
    # Un VP qui va de S à N passe devant l'entrée E : la voiture doit attendre.
    choisir(panneau, VehiculePrioritaire.CATEGORIE, "S", "N")
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


def test_arret_ne_laisse_aucun_thread_client(lancer_serveur: Callable[..., Serveur], fabrique_panneau: Callable) -> None:
    serveur = lancer_serveur()
    panneau = fabrique_panneau(serveur.config)
    panneau.choix_nombre.setValue(4)
    panneau.lancer()
    attendre(lambda: len(serveur.logique.registre.usagers) == 4)
    panneau.arreter_clients(DELAI)
    assert threads_clients() == []
    attendre(lambda: serveur.logique.registre.usagers == [])
