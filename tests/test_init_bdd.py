"""Tests du script init_bdd.py : création des tables et messages d'erreur clairs, sans MariaDB."""

from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import mysql.connector
import pytest
from doublure_bdd import FausseConnexion
from mysql.connector import errorcode
from outils import aide_du_script, charger_script

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_SCRIPT = RACINE / "scripts" / "init_bdd.py"


@pytest.fixture
def init_bdd(lancement_isole: Callable[[ModuleType], ModuleType]) -> ModuleType:
    """Le script chargé comme un module, sans config.ini, sans terminal ni variable CHERRYPIE_*."""
    return lancement_isole(charger_script(CHEMIN_SCRIPT))


@pytest.fixture
def connexions(monkeypatch: pytest.MonkeyPatch) -> list[FausseConnexion]:
    """Connexions ouvertes par le script, vers une base factice."""
    ouvertes: list[FausseConnexion] = []

    def connecter(**parametres: object) -> FausseConnexion:
        ouvertes.append(FausseConnexion(**parametres))
        return ouvertes[-1]

    monkeypatch.setattr(mysql.connector, "connect", connecter)
    return ouvertes


# ---------- Réussite ----------

def test_tables_creees(
    init_bdd: ModuleType,
    connexions: list[FausseConnexion],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setenv("CHERRYPIE_BDD_MDP", "mdp_de_test")
    assert init_bdd.main([]) == 0
    assert len(connexions[0].requetes) == 3 and connexions[0].commits == 1 and connexions[0].fermee
    assert "Base prête sur localhost:3306" in capsys.readouterr().out


def test_options_et_mot_de_passe_transmis(
    init_bdd: ModuleType,
    connexions: list[FausseConnexion],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setenv("CHERRYPIE_BDD_MDP", "mdp_de_test")
    monkeypatch.setenv("CHERRYPIE_BDD_PORT", "3307")
    arguments = ["--bdd-hote", "bdd.exemple", "--bdd-utilisateur", "rond_point", "--bdd-nom", "historique"]
    assert init_bdd.main(arguments) == 0
    parametres = connexions[0].parametres
    assert (parametres["host"], parametres["port"], parametres["user"]) == ("bdd.exemple", 3307, "rond_point")
    assert (parametres["password"], parametres["database"]) == ("mdp_de_test", "historique")
    assert "Base prête sur bdd.exemple:3307" in capsys.readouterr().out


def test_aide_sans_pyqt() -> None:
    # Sur la VM code, sans écran, le script ne doit pas charger Qt.
    aide, qt_charge = aide_du_script(CHEMIN_SCRIPT)
    assert "--bdd-hote" in aide and "CHERRYPIE_BDD_MDP" in aide and "--port-tcp" not in aide
    assert not qt_charge


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
    monkeypatch.setenv("CHERRYPIE_BDD_MDP", "mdp_de_test")
    assert init_bdd.main([]) == 1
    erreurs = capsys.readouterr().err
    assert message in erreurs and conseil in erreurs


def test_mot_de_passe_absent(
    init_bdd: ModuleType, connexions: list[FausseConnexion], capsys: pytest.CaptureFixture
) -> None:
    assert init_bdd.main([]) == 1
    assert "CHERRYPIE_BDD_MDP non définie" in capsys.readouterr().err
    assert not connexions


def test_configuration_absente(
    init_bdd: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, tmp_path: Path
) -> None:
    monkeypatch.setenv("CHERRYPIE_BDD_MDP", "mdp_de_test")
    assert init_bdd.main(["--config", str(tmp_path / "absent.ini")]) == 1
    assert "option --config" in capsys.readouterr().err
