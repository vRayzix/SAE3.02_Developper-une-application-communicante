"""Tests du script lancer_serveur.py : options, secrets et démarrage sans config.ini ni PyQt6."""

import signal
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
from outils import aide_du_script, charger_script

from cherrypie.commun.config import Configuration

CHEMIN_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "lancer_serveur.py"


class FauxServeur:
    """Remplace le serveur : il note sa configuration et rend la main aussitôt."""

    lances: list["FauxServeur"] = []

    def __init__(self, config: Configuration) -> None:
        self.config = config
        FauxServeur.lances.append(self)

    def demarrer(self) -> None:
        pass

    def servir(self) -> None:
        pass

    def arreter(self) -> None:
        pass


@pytest.fixture
def lancer_serveur_script(
    lancement_isole: Callable[[ModuleType], ModuleType], monkeypatch: pytest.MonkeyPatch
) -> ModuleType:
    """Le script chargé comme un module, isolé, avec un faux serveur et sans toucher au SIGTERM du processus."""
    script = lancement_isole(charger_script(CHEMIN_SCRIPT))
    FauxServeur.lances = []
    monkeypatch.setattr(script, "Serveur", FauxServeur)
    monkeypatch.setattr(signal, "signal", lambda *_: None)
    return script


# ---------- Démarrage ----------

def test_demarre_sans_config_ini(
    lancer_serveur_script: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("CHERRYPIE_CLE", "cle_de_test")
    monkeypatch.setenv("CHERRYPIE_BDD_MDP", "mdp_de_test")
    monkeypatch.setenv("CHERRYPIE_PORT_UDP", "6001")
    arguments = ["--hote", "0.0.0.0", "--port-tcp", "6000", "--bdd-hote", "bdd.exemple", "--bdd-nom", "historique"]
    assert lancer_serveur_script.main(arguments) == 0
    (serveur,) = FauxServeur.lances
    config = serveur.config
    assert (config.hote, config.port_tcp, config.port_udp, config.cle_hmac) == ("0.0.0.0", 6000, 6001, b"cle_de_test")
    assert config.parametres_bdd == {
        "hote": "bdd.exemple", "port": 3306, "utilisateur": "cherrypie", "mot_de_passe": "mdp_de_test",
        "base": "historique",
    }
    assert "démarré sur 0.0.0.0 (TCP 6000, UDP 6001)" in capsys.readouterr().out


def test_aide_sans_pyqt() -> None:
    # La VM code n'a pas d'écran : le serveur ne doit pas charger Qt.
    aide, qt_charge = aide_du_script(CHEMIN_SCRIPT)
    assert all(option in aide for option in ("--hote", "--port-tcp", "--port-udp", "--bdd-hote", "--bdd-nom"))
    assert "CHERRYPIE_CLE" in aide and "CHERRYPIE_BDD_MDP" in aide
    assert not qt_charge


# ---------- Secrets absents ----------

@pytest.mark.parametrize(
    ("definie", "absente"),
    [("CHERRYPIE_BDD_MDP", "CHERRYPIE_CLE"), ("CHERRYPIE_CLE", "CHERRYPIE_BDD_MDP")],
    ids=["cle", "mot-de-passe"],
)
def test_secret_absent_nomme(
    lancer_serveur_script: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    definie: str,
    absente: str,
) -> None:
    monkeypatch.setenv(definie, "secret")
    assert lancer_serveur_script.main([]) == 1
    assert f"{absente} non définie" in capsys.readouterr().err
    assert not FauxServeur.lances


def test_secret_en_option_refuse(lancer_serveur_script: ModuleType) -> None:
    with pytest.raises(SystemExit):
        lancer_serveur_script.main(["--cle", "secret"])
