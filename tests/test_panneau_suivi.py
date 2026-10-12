"""Tests de la section « Suivi » : clients en route et dernières consignes."""

from collections.abc import Callable

import pytest
from outils import attendre_qt
from PyQt6.QtWidgets import QApplication

from cherrypie.commun.config import Configuration
from cherrypie.ihm.lanceur_clients import LanceurClients
from cherrypie.ihm.panneau_suivi import (
    COLONNE_CONNEXION,
    COLONNE_CONSIGNE,
    COLONNE_TRAJET,
    NOMBRE_MAX_CONSIGNES,
    PanneauSuivi,
)
from cherrypie.serveur.serveur import Serveur


@pytest.fixture
def lanceur(qapp: QApplication, fabrique_config: Callable[..., Configuration]) -> LanceurClients:
    return LanceurClients(fabrique_config())


@pytest.fixture
def suivi(lanceur: LanceurClients) -> PanneauSuivi:
    return PanneauSuivi(lanceur)


# ---------- Clients en route ----------

def test_client_lance_ajoute_une_ligne(lanceur: LanceurClients, suivi: PanneauSuivi) -> None:
    lanceur.client_lance.emit("voiture_1", "Bd des Nations (sud) vers Rue Albert Camus")
    ligne = suivi.liste_clients.topLevelItem(0)
    assert (ligne.text(0), ligne.text(COLONNE_TRAJET)) == ("voiture_1", "Bd des Nations (sud) vers Rue Albert Camus")


def test_connexion_et_consigne_affichees(lanceur: LanceurClients, suivi: PanneauSuivi) -> None:
    lanceur.client_lance.emit("voiture_1", "trajet")
    lanceur.connexion_changee.emit("voiture_1", "connecte", "inscrit")
    lanceur.position_changee.emit("voiture_1", {"consigne": "ATTENDEZ"})
    ligne = suivi.liste_clients.topLevelItem(0)
    assert (ligne.text(COLONNE_CONNEXION), ligne.text(COLONNE_CONSIGNE)) == ("connecté", "ATTENDEZ")


def test_client_termine_retire_de_la_liste(lanceur: LanceurClients, suivi: PanneauSuivi) -> None:
    lanceur.client_lance.emit("voiture_1", "trajet")
    lanceur.connexion_changee.emit("voiture_1", "termine", "trajet terminé")
    assert suivi.liste_clients.topLevelItemCount() == 0


# ---------- Dernières consignes ----------

def test_consigne_ajoutee_en_haut(lanceur: LanceurClients, suivi: PanneauSuivi) -> None:
    lanceur.notification_recue.emit("voiture_1", "ATTENDEZ", "attendez", True)
    lanceur.notification_recue.emit("moto_1", "DEGAGEZ", "dégagez", False)
    assert suivi.consignes.item(0).text().endswith("moto_1 : DEGAGEZ (ignorée)")
    assert suivi.consignes.item(1).toolTip() == "attendez"


def test_consignes_les_plus_anciennes_oubliees(lanceur: LanceurClients, suivi: PanneauSuivi) -> None:
    for numero in range(NOMBRE_MAX_CONSIGNES + 5):
        lanceur.notification_recue.emit(f"voiture_{numero}", "ATTENDEZ", "", True)
    assert suivi.consignes.count() == NOMBRE_MAX_CONSIGNES
    assert f"voiture_{NOMBRE_MAX_CONSIGNES + 4} " in suivi.consignes.item(0).text()


# ---------- Avec de vrais clients ----------

def test_clients_lances_suivis_jusqu_a_la_connexion(qapp: QApplication, lancer_serveur: Callable[..., Serveur]) -> None:
    serveur = lancer_serveur()
    lanceur = LanceurClients(serveur.config)
    suivi = PanneauSuivi(lanceur)
    lanceur.lancer("voiture", "nations_sud", "albert_camus", 2)
    try:
        attendre_qt(lambda: all(
            suivi.liste_clients.topLevelItem(rang).text(COLONNE_CONNEXION) == "connecté" for rang in range(2)
        ))
    finally:
        lanceur.arreter_tous(2.0)
