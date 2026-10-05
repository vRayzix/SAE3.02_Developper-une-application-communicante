"""Outils partagés par les tests qui font tourner des threads."""

import time
from collections.abc import Callable

# Délai maximal accordé à une action réseau ou à un thread dans les tests, en secondes.
DELAI = 2.0


def attendre(condition: Callable[[], bool], delai: float = DELAI) -> None:
    """Attend qu'une condition devienne vraie, au plus `delai` secondes."""
    limite = time.monotonic() + delai
    while not condition():
        assert time.monotonic() < limite, "la condition n'est jamais devenue vraie"
        time.sleep(0.01)
