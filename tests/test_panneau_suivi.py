"""Tests de la section « Suivi » : clients en route, consignes et événements du serveur."""

import re
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
    DESTINATAIRES_AFFICHES,
    NOMBRE_MAX_MESSAGES,
    PanneauSuivi,
)
from cherrypie.ihm.style import COULEUR_EVENEMENT, COULEURS_MESSAGE
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


# ---------- Consignes ----------

def test_consigne_affichee_en_haut_avec_son_texte(lanceur: LanceurClients, suivi: PanneauSuivi) -> None:
    lanceur.notification_recue.emit("voiture_1", "ATTENDEZ", "Attendez avant d'entrer.", True)
    lanceur.notification_recue.emit("moto_1", "DEGAGEZ", "Dégagez la voie.", False)
    attendu = r"\d\d:\d\d:\d\d  moto_1 ← DEGAGEZ : Dégagez la voie\. \(ignorée\)"
    assert re.fullmatch(attendu, suivi.messages.item(0).text())
    assert suivi.messages.item(1).text().endswith("voiture_1 ← ATTENDEZ : Attendez avant d'entrer.")


@pytest.mark.parametrize("code", list(COULEURS_MESSAGE))
def test_ligne_coloree_selon_le_code(lanceur: LanceurClients, suivi: PanneauSuivi, code: str) -> None:
    lanceur.notification_recue.emit("voiture_1", code, "texte", True)
    fond = suivi.messages.item(0).background().color()
    assert fond.rgb() == COULEURS_MESSAGE[code].rgb()


def test_consignes_identiques_regroupees(lanceur: LanceurClients, suivi: PanneauSuivi) -> None:
    for numero in range(DESTINATAIRES_AFFICHES + 2):
        lanceur.notification_recue.emit(f"voiture_{numero}", "ATTENDEZ", "attendez", True)
    lanceur.notification_recue.emit("voiture_0", "ATTENDEZ", "attendez", True)
    assert suivi.messages.count() == 1
    ligne = suivi.messages.item(0)
    assert "voiture_0 (×2), voiture_1, voiture_2 et 2 autres ← ATTENDEZ" in ligne.text()
    assert ligne.toolTip() == "voiture_0, voiture_1, voiture_2, voiture_3, voiture_4"


def test_un_seul_destinataire_de_plus_au_singulier(lanceur: LanceurClients, suivi: PanneauSuivi) -> None:
    for numero in range(DESTINATAIRES_AFFICHES + 1):
        lanceur.notification_recue.emit(f"voiture_{numero}", "ATTENDEZ", "attendez", True)
    assert " et 1 autre ← ATTENDEZ" in suivi.messages.item(0).text()


def test_consigne_differente_ouvre_une_ligne(lanceur: LanceurClients, suivi: PanneauSuivi) -> None:
    lanceur.notification_recue.emit("voiture_1", "ATTENDEZ", "attendez", True)
    lanceur.notification_recue.emit("voiture_1", "OK_PASSER", "passez", True)
    lanceur.notification_recue.emit("voiture_2", "ATTENDEZ", "attendez", True)
    assert suivi.messages.count() == 3


def test_messages_les_plus_anciens_oublies(lanceur: LanceurClients, suivi: PanneauSuivi) -> None:
    for numero in range(NOMBRE_MAX_MESSAGES + 5):
        code = "ATTENDEZ" if numero % 2 else "OK_PASSER"
        lanceur.notification_recue.emit(f"voiture_{numero}", code, "", True)
    assert suivi.messages.count() == NOMBRE_MAX_MESSAGES
    assert f"voiture_{NOMBRE_MAX_MESSAGES + 4} " in suivi.messages.item(0).text()


# ---------- Événements du serveur ----------

def etat(**changements: object) -> dict:
    return {"regulation": True, "vps": [], "entrees_bloquees": [], "passages_fermes": []} | changements


def test_evenement_du_serveur_dans_la_meme_liste(lanceur: LanceurClients, suivi: PanneauSuivi) -> None:
    suivi.noter_etat(etat())
    lanceur.notification_recue.emit("voiture_1", "ATTENDEZ", "attendez", True)
    suivi.noter_etat(etat(entrees_bloquees=["nations_sud"]))
    assert suivi.messages.item(0).text().endswith("Serveur : Entrée temporisée : Bd des Nations (sud)")
    assert suivi.messages.item(0).background().color().rgb() == COULEUR_EVENEMENT.rgb()
    assert suivi.messages.count() == 2


def test_evenements_de_meme_nature_regroupes(suivi: PanneauSuivi) -> None:
    suivi.noter_etat(etat())
    suivi.noter_etat(etat(entrees_bloquees=["nations_sud", "albert_camus"]))
    suivi.noter_etat(etat())
    assert suivi.messages.count() == 2
    assert suivi.messages.item(0).text().endswith("Serveur : Entrée libérée : Rue Albert Camus, Bd des Nations (sud)")


def test_apres_oubli_pas_d_evenement_invente(suivi: PanneauSuivi) -> None:
    suivi.noter_etat(etat())
    for _ in range(3):
        suivi.noter_etat(etat(regulation=False))
        suivi.noter_etat(etat())
    assert suivi.messages.count() == 6
    suivi.oublier_etat()
    suivi.noter_etat(etat(regulation=False))
    assert suivi.messages.count() == 6


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
