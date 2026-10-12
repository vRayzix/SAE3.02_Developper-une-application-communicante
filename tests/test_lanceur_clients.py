"""Tests du lanceur de clients locaux : identifiants, trajets, signaux et arrêt."""

import threading
from collections.abc import Callable, Iterator

import pytest
from outils import DELAI, attendre, attendre_qt
from PyQt6.QtWidgets import QApplication

from cherrypie.commun.config import Configuration
from cherrypie.ihm.lanceur_clients import LanceurClients
from cherrypie.serveur.serveur import Serveur


@pytest.fixture
def fabrique_lanceur(qapp: QApplication) -> Iterator[Callable[[Configuration], LanceurClients]]:
    """Crée des lanceurs, puis arrête leurs clients à la fin du test."""
    lanceurs: list[LanceurClients] = []

    def fabriquer(config: Configuration) -> LanceurClients:
        lanceur = LanceurClients(config)
        lanceurs.append(lanceur)
        return lanceur

    yield fabriquer
    for lanceur in lanceurs:
        lanceur.arreter_tous(DELAI)


def threads_clients() -> list[threading.Thread]:
    return [fil for fil in threading.enumerate() if fil.name.startswith("client-")]


# ---------- Lancement ----------

def test_clients_lances_et_inscrits(lancer_serveur: Callable[..., Serveur], fabrique_lanceur: Callable) -> None:
    serveur = lancer_serveur()
    lanceur = fabrique_lanceur(serveur.config)
    clients = lanceur.lancer("voiture", "nations_sud", "albert_camus", 3)
    assert [client.usager.identifiant for client in clients] == ["voiture_1", "voiture_2", "voiture_3"]
    attendre(lambda: len(serveur.logique.registre.usagers) == 3)


def test_identifiants_jamais_resservis(lancer_serveur: Callable[..., Serveur], fabrique_lanceur: Callable) -> None:
    serveur = lancer_serveur()
    lanceur = fabrique_lanceur(serveur.config)
    lanceur.lancer("moto", "nations_sud", "albert_camus", 1)
    (seconde,) = lanceur.lancer("moto", "nations_nord", "nations_sud", 1)
    assert seconde.usager.identifiant == "moto_2"


@pytest.mark.parametrize(
    ("categorie", "entree", "sortie", "trajet"),
    [
        ("voiture", "nations_sud", "albert_camus", "Bd des Nations (sud) vers Rue Albert Camus"),
        ("pieton", "nations_nord", "nations_nord", "traverse Bd des Nations (nord)"),
    ],
    ids=["vehicule", "pieton"],
)
def test_trajet_avec_les_noms_de_rues(
    fabrique_config: Callable[..., Configuration], fabrique_lanceur: Callable, categorie: str, entree: str,
    sortie: str, trajet: str,
) -> None:
    assert fabrique_lanceur(fabrique_config()).trajet(categorie, entree, sortie) == trajet


# ---------- Signaux ----------

def test_lancement_et_connexion_signales(lancer_serveur: Callable[..., Serveur], fabrique_lanceur: Callable) -> None:
    serveur = lancer_serveur()
    lanceur = fabrique_lanceur(serveur.config)
    lances: list[tuple] = []
    connexions: list[tuple] = []
    lanceur.client_lance.connect(lambda *recu: lances.append(recu))
    lanceur.connexion_changee.connect(lambda *recu: connexions.append(recu))
    lanceur.lancer("voiture", "nations_sud", "albert_camus", 1)
    assert lances == [("voiture_1", "Bd des Nations (sud) vers Rue Albert Camus")]
    attendre_qt(lambda: ("voiture_1", "connecte", "inscrit auprès du serveur") in connexions)


# ---------- Arrêt ----------

def test_arret_ne_laisse_aucun_thread_client(
    lancer_serveur: Callable[..., Serveur], fabrique_lanceur: Callable
) -> None:
    serveur = lancer_serveur()
    lanceur = fabrique_lanceur(serveur.config)
    lanceur.lancer("voiture", "nations_sud", "albert_camus", 4)
    attendre(lambda: len(serveur.logique.registre.usagers) == 4)
    lanceur.arreter_tous(DELAI)
    assert threads_clients() == []
    attendre(lambda: serveur.logique.registre.usagers == [])
