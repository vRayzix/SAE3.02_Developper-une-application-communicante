"""Tests de la légende : une entrée par élément que la scène peut montrer."""

import math

import pytest
from PyQt6.QtWidgets import QApplication, QGridLayout

from cherrypie.ihm.legende import Legende
from cherrypie.ihm.style import COULEURS_CONSIGNE, NOMS_CATEGORIE
from cherrypie.serveur.densite import NiveauDensite


@pytest.fixture
def legende(qapp: QApplication) -> Legende:
    return Legende(colonnes=4)


def test_legende_toutes_les_categories(legende: Legende) -> None:
    assert set(NOMS_CATEGORIE.values()) <= set(legende.libelles)


def test_legende_toutes_les_consignes(legende: Legende) -> None:
    assert {f"Consigne {code}" for code in COULEURS_CONSIGNE} <= set(legende.libelles)


def test_legende_tous_les_niveaux_de_densite(legende: Legende) -> None:
    assert {f"Densité {niveau.value}" for niveau in NiveauDensite} <= set(legende.libelles)


def test_legende_marques_de_regulation(legende: Legende) -> None:
    assert {"Segment réservé au VP", "Entrée temporisée"} <= set(legende.libelles)


def test_legende_rangee_sur_le_nombre_de_colonnes(legende: Legende) -> None:
    grille = legende.layout()
    assert isinstance(grille, QGridLayout)
    assert grille.columnCount() == 4
    assert grille.rowCount() == math.ceil(len(legende.libelles) / 4)
