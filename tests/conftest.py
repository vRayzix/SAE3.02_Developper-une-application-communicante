"""Outils partagés par les tests : configurations sur des ports libres."""

import configparser
import socket
from collections.abc import Callable
from pathlib import Path

import pytest

from cherrypie.commun.config import Configuration

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
