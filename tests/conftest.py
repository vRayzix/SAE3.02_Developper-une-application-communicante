"""Fixtures partagées par les tests : configurations sur des ports libres, serveurs et clients lancés."""

import configparser
import socket
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from outils import DELAI

from cherrypie.client.client_usager import ClientUsager
from cherrypie.commun.config import Configuration
from cherrypie.modele.usager import Usager, Voiture
from cherrypie.serveur.serveur import Serveur

CHEMIN_EXEMPLE = Path(__file__).resolve().parent.parent / "config.exemple.ini"


def port_libre(type_socket: socket.SocketKind) -> int:
    """Demande au système un port libre sur 127.0.0.1."""
    with socket.socket(socket.AF_INET, type_socket) as prise:
        prise.bind(("127.0.0.1", 0))
        return prise.getsockname()[1]


@pytest.fixture
def fabrique_config() -> Callable[..., Configuration]:
    """Fabrique des configurations tirées du fichier d'exemple, sur 127.0.0.1 et des ports libres.

    Les arguments nommés remplacent des valeurs de l'exemple, quelle que soit leur
    section : fabrique_config(timeout_client="0.3").
    """

    def fabriquer(**valeurs: str) -> Configuration:
        parseur = configparser.ConfigParser(interpolation=None)
        parseur.read(CHEMIN_EXEMPLE, encoding="utf-8")
        parseur["reseau"]["hote"] = "127.0.0.1"
        parseur["reseau"]["port_tcp"] = str(port_libre(socket.SOCK_STREAM))
        parseur["reseau"]["port_udp"] = str(port_libre(socket.SOCK_DGRAM))
        for cle, valeur in valeurs.items():
            (section,) = [nom for nom in parseur.sections() if cle in parseur[nom]]
            parseur[section][cle] = valeur
        return Configuration(parseur)

    return fabriquer


@pytest.fixture
def lancer_serveur(fabrique_config: Callable[..., Configuration]) -> Iterator[Callable[..., Serveur]]:
    """Démarre des serveurs dans des threads, puis les arrête proprement à la fin du test.

    lancer_serveur(timeout_client="0.3") fabrique une configuration sur des ports libres ;
    lancer_serveur(config) réutilise une configuration, par exemple pour relancer un
    serveur sur les mêmes ports.
    """
    lances: list[tuple[Serveur, threading.Thread]] = []

    def lancer(config: Configuration | None = None, **valeurs: str) -> Serveur:
        if config is None:
            config = fabrique_config(**{"intervalle_etat": "0.05", **valeurs})
        serveur = Serveur(config)
        serveur.demarrer()
        fil = threading.Thread(target=serveur.servir, daemon=True)
        fil.start()
        lances.append((serveur, fil))
        return serveur

    yield lancer
    for serveur, fil in lances:
        serveur.arreter()
        fil.join(timeout=DELAI)


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
