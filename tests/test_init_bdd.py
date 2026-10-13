"""Tests du script init_bdd.py : création des tables et messages d'erreur clairs, sans MariaDB."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import mysql.connector
import pytest
from doublure_bdd import FausseConnexion
from mysql.connector import errorcode

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_SCRIPT = RACINE / "scripts" / "init_bdd.py"
CHEMIN_EXEMPLE = RACINE / "config.exemple.ini"


@pytest.fixture
def init_bdd() -> ModuleType:
    """Charge le script comme un module, sans l'exécuter."""
    specification = importlib.util.spec_from_file_location("init_bdd", CHEMIN_SCRIPT)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def lancer(init_bdd: ModuleType, monkeypatch: pytest.MonkeyPatch, chemin: Path = CHEMIN_EXEMPLE) -> int:
    monkeypatch.setattr(sys, "argv", ["init_bdd.py", str(chemin)])
    return init_bdd.main()


# ---------- Réussite ----------

def test_tables_creees(init_bdd: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    connexions: list[FausseConnexion] = []

    def connecter(**parametres: object) -> FausseConnexion:
        connexions.append(FausseConnexion(**parametres))
        return connexions[-1]

    monkeypatch.setattr(mysql.connector, "connect", connecter)
    assert lancer(init_bdd, monkeypatch) == 0
    assert len(connexions[0].requetes) == 3 and connexions[0].commits == 1 and connexions[0].fermee
    assert "Base prête sur localhost:3306" in capsys.readouterr().out


# ---------- Échecs expliqués ----------

@pytest.mark.parametrize(
    ("errno", "message", "conseil"),
    [
        (errorcode.CR_CONN_HOST_ERROR, "injoignable", "bind-address"),
        (errorcode.ER_ACCESS_DENIED_ERROR, "accès refusé", "GRANT"),
        (errorcode.ER_BAD_DB_ERROR, "n'existe pas", "CREATE DATABASE"),
    ],
    ids=["serveur-injoignable", "acces-refuse", "base-absente"],
)
def test_echec_explique(
    init_bdd: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    errno: int,
    message: str,
    conseil: str,
) -> None:
    def refuser(**_: object) -> None:
        raise mysql.connector.Error(msg="refus", errno=errno)

    monkeypatch.setattr(mysql.connector, "connect", refuser)
    assert lancer(init_bdd, monkeypatch) == 1
    erreurs = capsys.readouterr().err
    assert message in erreurs and conseil in erreurs


def test_configuration_absente(
    init_bdd: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path: Path
) -> None:
    assert lancer(init_bdd, monkeypatch, tmp_path / "absent.ini") == 1
    assert "Configuration invalide" in capsys.readouterr().err
