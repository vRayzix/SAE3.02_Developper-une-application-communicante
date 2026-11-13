"""Outils partagés par les tests qui font tourner des threads ou des scripts."""

import importlib.util
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

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


def charger_script(chemin: Path) -> ModuleType:
    """Charge un script de scripts/ comme un module, sans exécuter son main()."""
    specification = importlib.util.spec_from_file_location(chemin.stem, chemin)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def aide_du_script(chemin: Path) -> tuple[str, bool]:
    """Lance « script --help » dans un nouvel interpréteur.

    Returns:
        tuple[str, bool]: texte de l'aide, et True si le script a chargé PyQt6.
    """
    code = f"""
import runpy, sys
sys.argv = [{str(chemin)!r}, "--help"]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit:
    pass
print("PyQt6" in sys.modules)
"""
    sortie = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, encoding="utf-8", check=True, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    ).stdout.strip()
    aide, _, qt_charge = sortie.rpartition("\n")
    return aide, qt_charge == "True"
