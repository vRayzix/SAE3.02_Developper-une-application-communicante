"""Tests du réseau de la supervision : vrai serveur sur 127.0.0.1, travailleur dans un QThread."""

import threading
import time
from collections.abc import Callable, Iterator

import pytest
from outils import DELAI, attendre, attendre_qt
from PyQt6.QtCore import QThread, Qt
from PyQt6.QtWidgets import QApplication

from cherrypie.client.client_usager import EtatConnexion
from cherrypie.commun.config import Configuration
from cherrypie.ihm.thread_reseau import ReseauSupervision
from cherrypie.serveur.serveur import Serveur

DELAI_MS = int(DELAI * 1000)
# Délais courts pour que heartbeat, timeout et reconnexion se jouent en moins d'une seconde.
DELAIS_RAPIDES = {
    "intervalle_ping": "0.1",
    "timeout_client": "0.5",
    "backoff_initial": "0.1",
    "backoff_max": "0.4",
}


class Recepteur:
    """Note ce que le travailleur signale, et dans quel thread chaque signal arrive."""

    def __init__(self, reseau: ReseauSupervision) -> None:
        self.__etats: list[dict] = []
        self.__connexions: list[str] = []
        self.__termine = False
        self.__threads: set[threading.Thread] = set()
        reseau.etat_recu.connect(self.__noter_etat)
        reseau.connexion_changee.connect(self.__noter_connexion)
        reseau.termine.connect(self.__noter_fin)

    @property
    def etats(self) -> list[dict]:
        return list(self.__etats)

    @property
    def connexions(self) -> list[str]:
        return list(self.__connexions)

    @property
    def termine(self) -> bool:
        return self.__termine

    @property
    def threads(self) -> set[threading.Thread]:
        return set(self.__threads)

    def oublier_etats(self) -> None:
        self.__etats.clear()

    def __noter_etat(self, etat: dict) -> None:
        self.__threads.add(threading.current_thread())
        self.__etats.append(etat)

    def __noter_connexion(self, etat: str, detail: str) -> None:
        self.__threads.add(threading.current_thread())
        self.__connexions.append(etat)

    def __noter_fin(self) -> None:
        self.__termine = True


@pytest.fixture
def lancer_reseau(qapp: QApplication) -> Iterator[Callable[[Configuration], tuple[ReseauSupervision, QThread, Recepteur]]]:
    """Lance des travailleurs dans des QThread, puis les arrête à la fin du test."""
    lances: list[tuple[ReseauSupervision, QThread]] = []

    def lancer(config: Configuration) -> tuple[ReseauSupervision, QThread, Recepteur]:
        reseau = ReseauSupervision(config)
        fil = QThread()
        reseau.moveToThread(fil)
        fil.started.connect(reseau.tourner)
        reseau.termine.connect(fil.quit, Qt.ConnectionType.DirectConnection)
        recepteur = Recepteur(reseau)
        fil.start()
        lances.append((reseau, fil))
        return reseau, fil, recepteur

    yield lancer
    for reseau, fil in lances:
        reseau.arreter()
        fil.wait(DELAI_MS)


# ---------- Abonnement et STATE ----------


def test_state_recu_dans_le_thread_de_l_ihm(lancer_serveur: Callable[..., Serveur], lancer_reseau: Callable) -> None:
    serveur = lancer_serveur(**DELAIS_RAPIDES)
    _, _, recepteur = lancer_reseau(serveur.config)
    attendre_qt(lambda: len(recepteur.etats) >= 2)
    assert recepteur.etats[-1]["regulation"] is True
    assert recepteur.threads == {threading.main_thread()}


def test_connexion_signalee(lancer_serveur: Callable[..., Serveur], lancer_reseau: Callable) -> None:
    serveur = lancer_serveur(**DELAIS_RAPIDES)
    reseau, _, recepteur = lancer_reseau(serveur.config)
    attendre_qt(lambda: EtatConnexion.CONNECTE.value in recepteur.connexions)
    assert recepteur.connexions[:2] == [EtatConnexion.CONNEXION.value, EtatConnexion.CONNECTE.value]
    assert reseau.etat is EtatConnexion.CONNECTE
    attendre(lambda: len(serveur.logique.superviseurs()) == 1)


def test_ping_garde_la_supervision_abonnee(lancer_serveur: Callable[..., Serveur], lancer_reseau: Callable) -> None:
    serveur = lancer_serveur(**DELAIS_RAPIDES)
    _, _, recepteur = lancer_reseau(serveur.config)
    attendre(lambda: len(serveur.logique.superviseurs()) == 1)
    (session,) = serveur.logique.superviseurs()
    # Trois fois le timeout du serveur : sans PING, la supervision aurait été retirée.
    duree = 3 * float(DELAIS_RAPIDES["timeout_client"])
    fin = time.monotonic() + duree
    attendre_qt(lambda: time.monotonic() >= fin, delai=duree + DELAI)
    assert serveur.logique.superviseurs() == [session]
    assert EtatConnexion.DECONNECTE.value not in recepteur.connexions


# ---------- Réglage de la régulation ----------


def test_reglage_transmis_au_serveur(lancer_serveur: Callable[..., Serveur], lancer_reseau: Callable) -> None:
    serveur = lancer_serveur(**DELAIS_RAPIDES)
    reseau, _, recepteur = lancer_reseau(serveur.config)
    attendre_qt(lambda: bool(recepteur.etats))
    reseau.demander_reglage(False)
    attendre(lambda: serveur.logique.regulation_active is False)
    attendre_qt(lambda: recepteur.etats[-1]["regulation"] is False)


def test_reglage_demande_hors_connexion_abandonne(
    fabrique_config: Callable[..., Configuration], lancer_serveur: Callable[..., Serveur], lancer_reseau: Callable
) -> None:
    config = fabrique_config(**DELAIS_RAPIDES, intervalle_etat="0.05")
    reseau, _, recepteur = lancer_reseau(config)
    attendre_qt(lambda: EtatConnexion.DECONNECTE.value in recepteur.connexions)
    reseau.demander_reglage(False)
    serveur = lancer_serveur(config)
    attendre_qt(lambda: len(recepteur.etats) >= 3)
    assert serveur.logique.regulation_active is True


# ---------- Coupures et arrêt ----------


def test_reconnexion_apres_redemarrage_du_serveur(
    lancer_serveur: Callable[..., Serveur], lancer_reseau: Callable
) -> None:
    serveur = lancer_serveur(**DELAIS_RAPIDES)
    _, _, recepteur = lancer_reseau(serveur.config)
    attendre_qt(lambda: bool(recepteur.etats))
    serveur.arreter()
    attendre_qt(lambda: EtatConnexion.DECONNECTE.value in recepteur.connexions)
    recepteur.oublier_etats()
    relance = lancer_serveur(serveur.config)
    attendre_qt(lambda: bool(recepteur.etats))
    assert recepteur.connexions.count(EtatConnexion.CONNECTE.value) == 2
    assert len(relance.logique.superviseurs()) == 1


def test_serveur_absent_reessaie_sans_fin(fabrique_config: Callable[..., Configuration], lancer_reseau: Callable) -> None:
    _, _, recepteur = lancer_reseau(fabrique_config(**DELAIS_RAPIDES))
    attendre_qt(lambda: recepteur.connexions.count(EtatConnexion.DECONNECTE.value) >= 3)
    assert EtatConnexion.CONNECTE.value not in recepteur.connexions


def test_arret_termine_le_thread_et_desabonne(lancer_serveur: Callable[..., Serveur], lancer_reseau: Callable) -> None:
    serveur = lancer_serveur(**DELAIS_RAPIDES)
    reseau, fil, recepteur = lancer_reseau(serveur.config)
    attendre(lambda: len(serveur.logique.superviseurs()) == 1)
    reseau.arreter()
    assert fil.wait(DELAI_MS)
    attendre_qt(lambda: recepteur.termine)
    assert recepteur.connexions[-1] == EtatConnexion.TERMINE.value
    attendre(lambda: serveur.logique.superviseurs() == [])
