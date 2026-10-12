"""Tests du scénario de démonstration : lignes, instants de départ et enregistrement JSON."""

import json

import pytest

from cherrypie.commun.erreurs import ScenarioInvalideError
from cherrypie.ihm.scenario import LigneScenario, Scenario

BRANCHES = {"nations_nord", "jean_de_la_bruyere", "nations_sud", "albert_camus"}


@pytest.fixture
def scenario() -> Scenario:
    return Scenario([
        LigneScenario("voiture", "nations_sud", "albert_camus", 3, 0.0),
        LigneScenario("pieton", "nations_nord", "nations_nord", 2, 1.5),
        LigneScenario("vp", "nations_sud", "nations_nord", 1, 4.0),
    ])


# ---------- Lignes ----------

@pytest.mark.parametrize(
    ("ligne", "motif"),
    [
        (("tank", "nations_sud", "nations_nord", 1, 0.0), "catégorie"),
        (("voiture", "nations_sud", "nations_nord", 0, 0.0), "nombre"),
        (("voiture", "nations_sud", "nations_nord", True, 0.0), "nombre"),
        (("voiture", "nations_sud", "nations_nord", 1, -1.0), "négatif"),
        (("voiture", "nations_sud", "nations_nord", 1, float("nan")), "délai"),
        (("pieton", "nations_sud", "nations_nord", 1, 0.0), "piéton"),
    ],
    ids=["categorie-inconnue", "nombre-nul", "nombre-booleen", "delai-negatif", "delai-nan", "pieton-deux-branches"],
)
def test_ligne_incoherente_refusee(ligne: tuple, motif: str) -> None:
    with pytest.raises(ScenarioInvalideError, match=motif):
        LigneScenario(*ligne)


def test_aller_retour_d_une_ligne() -> None:
    ligne = LigneScenario("moto", "albert_camus", "jean_de_la_bruyere", 2, 3.0)
    assert LigneScenario.depuis_dict(ligne.vers_dict()) == ligne


def test_ligne_incomplete_refusee() -> None:
    with pytest.raises(ScenarioInvalideError, match="il manque : delai"):
        LigneScenario.depuis_dict({"categorie": "moto", "entree": "albert_camus", "sortie": "nations_sud", "nombre": 1})


# ---------- Scénario ----------

def test_instants_de_depart_cumules(scenario: Scenario) -> None:
    assert scenario.instants_de_depart() == pytest.approx([0.0, 1.5, 5.5])


def test_nombre_d_usagers(scenario: Scenario) -> None:
    assert scenario.nombre_d_usagers == 6


def test_scenario_vide() -> None:
    assert (Scenario([]).instants_de_depart(), Scenario([]).nombre_d_usagers) == ([], 0)


def test_lignes_modifiees_de_l_exterieur_sans_effet(scenario: Scenario) -> None:
    scenario.lignes.clear()
    assert len(scenario.lignes) == 3


# ---------- JSON ----------

def test_aller_retour_json(scenario: Scenario) -> None:
    assert Scenario.depuis_json(scenario.vers_json(), BRANCHES).lignes == scenario.lignes


def test_json_versionne(scenario: Scenario) -> None:
    assert json.loads(scenario.vers_json())["version"] == 1


@pytest.mark.parametrize(
    ("texte", "motif"),
    [
        ("pas du json", "JSON valide"),
        ('{"version": 2, "lignes": []}', "format"),
        ('{"version": 1, "lignes": {}}', "liste"),
        ('{"version": 1, "lignes": [3]}', "objet"),
    ],
    ids=["texte", "version", "lignes-pas-en-liste", "ligne-pas-en-objet"],
)
def test_json_invalide_refuse(texte: str, motif: str) -> None:
    with pytest.raises(ScenarioInvalideError, match=motif):
        Scenario.depuis_json(texte, BRANCHES)


def test_branche_d_un_autre_rond_point_refusee(scenario: Scenario) -> None:
    with pytest.raises(ScenarioInvalideError, match="albert_camus"):
        Scenario.depuis_json(scenario.vers_json(), BRANCHES - {"albert_camus"})
