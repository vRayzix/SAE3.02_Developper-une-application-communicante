"""Tests de fumée sur la structure du paquet cherrypie."""

import importlib

import pytest

SOUS_PAQUETS = ["commun", "modele", "serveur", "client", "ihm", "bdd"]


# ---------- Import ----------

def test_import_paquet_racine_reussit() -> None:
    paquet = importlib.import_module("cherrypie")
    assert paquet.__doc__


@pytest.mark.parametrize("nom", SOUS_PAQUETS)
def test_import_sous_paquet_reussit(nom: str) -> None:
    sous_paquet = importlib.import_module(f"cherrypie.{nom}")
    assert sous_paquet.__doc__
