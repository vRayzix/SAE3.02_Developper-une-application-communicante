"""Tests du script lancer_supervision.py : options et clé HMAC, avant l'ouverture de la fenêtre."""

import signal
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from outils import aide_du_script, charger_script

CHEMIN_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "lancer_supervision.py"


@pytest.fixture
def lancer_supervision(lancement_isole: Callable[[ModuleType], ModuleType]) -> ModuleType:
    """Le script chargé comme un module, sans config.ini, sans terminal ni variable CHERRYPIE_*."""
    return lancement_isole(charger_script(CHEMIN_SCRIPT))


def test_options_reseau_seulement() -> None:
    aide, _ = aide_du_script(CHEMIN_SCRIPT)
    options = ("--config", "--hote", "--port-tcp", "--port-udp", "--fenetre-anti-rejeu", "CHERRYPIE_CLE")
    assert all(option in aide for option in options)
    # La supervision ne se connecte jamais à la base.
    assert "--bdd" not in aide and "CHERRYPIE_BDD_MDP" not in aide


def test_cle_absente_nommee_avant_la_fenetre(lancer_supervision: ModuleType, capsys: pytest.CaptureFixture) -> None:
    assert lancer_supervision.main(["--hote", "serveur.exemple"]) == 1
    assert "CHERRYPIE_CLE non définie" in capsys.readouterr().err


def test_fenetre_anti_rejeu_transmise_a_la_fenetre(
    lancer_supervision: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Les clients lancés depuis la fenêtre reçoivent cette même configuration.
    configs = []
    fausse_fenetre = SimpleNamespace(showMaximized=lambda: None, demarrer=lambda: None, close=lambda: None)
    monkeypatch.setattr(lancer_supervision, "FenetreSupervision", lambda config: configs.append(config) or fausse_fenetre)
    monkeypatch.setattr(lancer_supervision, "QApplication", lambda _: SimpleNamespace(exec=lambda: 0))
    monkeypatch.setattr(signal, "signal", lambda *_: None)
    monkeypatch.setenv("CHERRYPIE_CLE", "cle_de_test")
    monkeypatch.setenv("CHERRYPIE_FENETRE_ANTI_REJEU", "30")
    assert lancer_supervision.main(["--hote", "serveur.exemple"]) == 0
    assert configs[0].fenetre_anti_rejeu == pytest.approx(30.0)
