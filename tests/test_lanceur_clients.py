"""Tests du lanceur de clients locaux : identifiants, trajets, signaux et arrêt."""

import threading
from collections.abc import Callable, Iterator

import pytest
from outils import DELAI, attendre, attendre_qt
from PyQt6.QtWidgets import QApplication

from cherrypie.commun.config import Configuration
from cherrypie.ihm.lanceur_clients import LanceurClients
from cherrypie.modele.usager import Pieton
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


def test_plusieurs_pietons_lances_ensemble_ne_se_superposent_pas(
    lancer_serveur: Callable[..., Serveur], fabrique_lanceur: Callable
) -> None:
    serveur = lancer_serveur(intervalle_position="0.05")
    lanceur = fabrique_lanceur(serveur.config)
    lanceur.lancer(Pieton.CATEGORIE, "nations_nord", "nations_nord", 3)
    registre = serveur.logique.registre

    def espaces() -> bool:
        positions = [usager.position for usager in registre.usagers if usager.position is not None]
        return len(positions) == 3 and min(
            a.distance(b) for rang, a in enumerate(positions) for b in positions[rang + 1:]
        ) >= Pieton.DISTANCE_SECURITE / 2

    attendre(espaces, delai=3 * DELAI)


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


def test_consigne_du_serveur_relayee(lancer_serveur: Callable[..., Serveur], fabrique_lanceur: Callable) -> None:
    serveur = lancer_serveur()
    lanceur = fabrique_lanceur(serveur.config)
    consignes: list[tuple] = []
    lanceur.notification_recue.connect(lambda *recue: consignes.append(recue))
    lanceur.lancer("voiture", "jean_de_la_bruyere", "albert_camus", 1)
    # Le VP du sud vers le nord passe devant l'entrée de la rue Jean de la Bruyère : la voiture doit attendre.
    lanceur.lancer("vp", "nations_sud", "nations_nord", 1)
    attendre_qt(lambda: ("voiture_1", "ATTENDEZ") in [recue[:2] for recue in consignes])


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
