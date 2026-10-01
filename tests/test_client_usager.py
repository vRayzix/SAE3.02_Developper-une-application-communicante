"""Tests du client usager face à un vrai serveur, sur 127.0.0.1."""

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from outils import DELAI, attendre

from cherrypie.client.client_usager import ClientUsager, EtatConnexion
from cherrypie.commun.config import Configuration
from cherrypie.modele.usager import Usager, Voiture
from cherrypie.serveur.serveur import Serveur

# Délais courts, pour que les tests de heartbeat et de reconnexion restent rapides.
DELAIS_RAPIDES = {
    "intervalle_position": "0.05",
    "intervalle_ping": "0.1",
    "timeout_client": "0.5",
    "backoff_initial": "0.1",
    "backoff_max": "0.4",
}


@pytest.fixture
def preparer_client() -> Iterator[Callable[..., ClientUsager]]:
    """Prépare des clients, à démarrer avec start(), puis les arrête à la fin du test."""
    prepares: list[ClientUsager] = []

    def preparer(config: Configuration, usager: Usager | None = None, **rappels: Callable) -> ClientUsager:
        client = ClientUsager(config, usager or Voiture("voiture_12", "S", "N"), **rappels)
        prepares.append(client)
        return client

    yield preparer
    for client in prepares:
        client.arreter()
        if client.is_alive():
            client.join(timeout=DELAI)


@pytest.fixture
def serveur(lancer_serveur: Callable[..., Serveur]) -> Serveur:
    return lancer_serveur(**DELAIS_RAPIDES)


# ---------- Connexion et heartbeat ----------

def test_client_inscrit_aupres_du_serveur(serveur: Serveur, preparer_client: Callable[..., ClientUsager]) -> None:
    etats: list[EtatConnexion] = []
    client = preparer_client(serveur.config, sur_connexion=lambda etat, detail: etats.append(etat))
    client.start()
    attendre(lambda: serveur.logique.registre.contient("voiture_12"))
    attendre(lambda: client.etat is EtatConnexion.CONNECTE)
    assert etats[:2] == [EtatConnexion.CONNEXION, EtatConnexion.CONNECTE]


def test_ping_garde_le_client_inscrit_au_dela_du_timeout(
    serveur: Serveur, preparer_client: Callable[..., ClientUsager]
) -> None:
    client = preparer_client(serveur.config)
    client.start()
    attendre(lambda: client.etat is EtatConnexion.CONNECTE)
    time.sleep(3 * serveur.config.timeout_client)
    assert serveur.logique.registre.contient("voiture_12")
    assert client.etat is EtatConnexion.CONNECTE


def test_client_ne_depend_pas_de_qt() -> None:
    racine = Path(__file__).resolve().parent.parent
    environnement = {**os.environ, "PYTHONPATH": str(racine / "src")}
    resultat = subprocess.run(
        [sys.executable, "-c", "import sys, cherrypie.client.client_usager; print('PyQt6' in sys.modules)"],
        capture_output=True, text=True, env=environnement, check=True,
    )
    assert resultat.stdout.strip() == "False"


# ---------- Arrêt ----------

def test_arret_propre_avec_au_revoir(serveur: Serveur, preparer_client: Callable[..., ClientUsager]) -> None:
    client = preparer_client(serveur.config)
    client.start()
    attendre(lambda: serveur.logique.registre.contient("voiture_12"))
    debut = time.monotonic()
    client.arreter()
    client.join(timeout=DELAI)
    assert not client.is_alive()
    assert client.etat is EtatConnexion.TERMINE
    attendre(lambda: not serveur.logique.registre.contient("voiture_12"))
    # Le BYE fait retirer l'usager tout de suite, sans attendre le timeout du serveur.
    assert time.monotonic() - debut < serveur.config.timeout_client


def test_arret_pendant_l_attente_entre_deux_essais(
    fabrique_config: Callable[..., Configuration], preparer_client: Callable[..., ClientUsager]
) -> None:
    config = fabrique_config(**{**DELAIS_RAPIDES, "backoff_initial": "5", "backoff_max": "10"})
    client = preparer_client(config)
    client.start()
    attendre(lambda: client.etat is EtatConnexion.DECONNECTE)
    debut = time.monotonic()
    client.arreter()
    client.join(timeout=DELAI)
    assert not client.is_alive()
    assert time.monotonic() - debut < 1.0


# ---------- Reconnexion ----------

def test_reconnexion_apres_coupure_du_serveur(
    lancer_serveur: Callable[..., Serveur], preparer_client: Callable[..., ClientUsager]
) -> None:
    premier = lancer_serveur(**DELAIS_RAPIDES)
    etats: list[EtatConnexion] = []
    client = preparer_client(premier.config, sur_connexion=lambda etat, detail: etats.append(etat))
    client.start()
    attendre(lambda: premier.logique.registre.contient("voiture_12"))
    premier.arreter()
    attendre(lambda: EtatConnexion.DECONNECTE in etats)
    attendre(lambda: premier.ecoute_tcp.fileno() == -1 and premier.socket_udp.fileno() == -1)
    second = lancer_serveur(premier.config)
    attendre(lambda: second.logique.registre.contient("voiture_12"))
    assert etats.count(EtatConnexion.CONNECTE) == 2


def test_essais_espaces_par_un_delai_qui_double(
    fabrique_config: Callable[..., Configuration], preparer_client: Callable[..., ClientUsager]
) -> None:
    instants: list[float] = []

    def noter_les_essais(etat: EtatConnexion, detail: str) -> None:
        if etat is EtatConnexion.CONNEXION:
            instants.append(time.monotonic())

    client = preparer_client(fabrique_config(**DELAIS_RAPIDES), sur_connexion=noter_les_essais)
    client.start()
    attendre(lambda: len(instants) >= 5)
    ecarts = [suivant - precedent for precedent, suivant in zip(instants, instants[1:])]
    assert ecarts[:4] == pytest.approx([0.1, 0.2, 0.4, 0.4], abs=0.08)


def test_identifiant_deja_connecte_refuse_puis_inscrit(
    serveur: Serveur, preparer_client: Callable[..., ClientUsager]
) -> None:
    premier = preparer_client(serveur.config)
    premier.start()
    attendre(lambda: premier.etat is EtatConnexion.CONNECTE)
    details: list[str] = []
    second = preparer_client(serveur.config, sur_connexion=lambda etat, detail: details.append(detail))
    second.start()
    attendre(lambda: any("déjà connecté" in detail for detail in details))
    premier.arreter()
    premier.join(timeout=DELAI)
    attendre(lambda: second.etat is EtatConnexion.CONNECTE)


def test_refus_definitif_arrete_le_client(
    lancer_serveur: Callable[..., Serveur],
    fabrique_config: Callable[..., Configuration],
    preparer_client: Callable[..., ClientUsager],
) -> None:
    serveur = lancer_serveur(**DELAIS_RAPIDES, branches="A, B, C")
    # Le client croit à un rond-point N, E, S, O : le serveur ne connaît pas ses branches.
    ports = {"port_tcp": str(serveur.config.port_tcp), "port_udp": str(serveur.config.port_udp)}
    details: list[str] = []
    client = preparer_client(
        fabrique_config(**DELAIS_RAPIDES, **ports), sur_connexion=lambda etat, detail: details.append(detail)
    )
    client.start()
    client.join(timeout=DELAI)
    assert not client.is_alive()
    assert client.etat is EtatConnexion.TERMINE
    assert "branche inconnue" in details[-1]
