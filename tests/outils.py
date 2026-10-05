"""Outils partagés par les tests qui font tourner des threads."""

import time
from collections.abc import Callable

from PyQt6.QtCore import QCoreApplication

# Délai maximal accordé à une action réseau ou à un thread dans les tests, en secondes.
DELAI = 2.0


def attendre(condition: Callable[[], bool], delai: float = DELAI) -> None:
    """Attend qu'une condition devienne vraie, au plus `delai` secondes."""
    limite = time.monotonic() + delai
    while not condition():
        assert time.monotonic() < limite, "la condition n'est jamais devenue vraie"
        time.sleep(0.01)


def attendre_qt(condition: Callable[[], bool], delai: float = DELAI) -> None:
    """Fait tourner la boucle d'événements Qt jusqu'à ce qu'une condition devienne vraie.

    Les signaux émis depuis un autre thread n'arrivent dans le thread principal que
    pendant ce traitement des événements.
    """
    limite = time.monotonic() + delai
    while not condition():
        assert time.monotonic() < limite, "la condition n'est jamais devenue vraie"
        QCoreApplication.processEvents()
        time.sleep(0.01)
