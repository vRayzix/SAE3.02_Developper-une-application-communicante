"""Tests du script lancer_supervision.py : options et clé HMAC, avant l'ouverture de la fenêtre."""

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from outils import aide_du_script, charger_script

CHEMIN_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "lancer_supervision.py"


@pytest.fixture
def lancer_supervision(lancement_isole: Callable[[ModuleType], ModuleType]) -> ModuleType:
    """Le script chargé comme un module, sans config.ini, sans terminal ni variable CHERRYPIE_*."""
    return lancement_isole(charger_script(CHEMIN_SCRIPT))


def test_options_reseau_seulement() -> None:
    aide, _ = aide_du_script(CHEMIN_SCRIPT)
    assert all(option in aide for option in ("--config", "--hote", "--port-tcp", "--port-udp", "CHERRYPIE_CLE"))
    # La supervision ne se connecte jamais à la base.
    assert "--bdd" not in aide and "CHERRYPIE_BDD_MDP" not in aide


def test_cle_absente_nommee_avant_la_fenetre(lancer_supervision: ModuleType, capsys: pytest.CaptureFixture) -> None:
    assert lancer_supervision.main(["--hote", "192.0.2.1"]) == 1
    assert "CHERRYPIE_CLE non définie" in capsys.readouterr().err
