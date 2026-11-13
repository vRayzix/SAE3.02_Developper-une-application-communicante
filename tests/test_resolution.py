"""Tests de la résolution des paramètres : option > variable d'environnement > config.ini > défaut."""

import getpass
import io
import sys
from pathlib import Path

import pytest

from cherrypie.commun.config import Configuration
from cherrypie.commun.erreurs import ConfigurationInvalideError
from cherrypie.commun.resolution import PARAMETRES, creer_analyseur, resoudre_configuration, saisie_masquee

CHEMIN_EXEMPLE = Path(__file__).resolve().parent.parent / "config.exemple.ini"
ENVIRONNEMENT_SECRETS = {"CHERRYPIE_CLE": "cle_de_test", "CHERRYPIE_BDD_MDP": "mdp_de_test"}


def resoudre(
    tmp_path: Path, arguments: dict | None = None, environnement: dict | None = None, **parametres: object
) -> Configuration:
    """Résout sans toucher à l'environnement réel ; le config.ini par défaut est absent sauf mention contraire."""
    return resoudre_configuration(
        arguments or {}, parametres.pop("chemin_defaut", tmp_path / "absent.ini"), environnement=environnement or {},
        **parametres,
    )


def ecrire_config(dossier: Path, texte: str) -> Path:
    chemin = dossier / "config.ini"
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def valeurs(config: Configuration) -> dict[str, object]:
    """Toutes les propriétés d'une configuration, pour comparer deux configurations."""
    return {nom: getattr(config, nom) for nom, membre in vars(Configuration).items() if isinstance(membre, property)}


# ---------- Priorités ----------

@pytest.mark.parametrize(
    ("option", "variable", "fichier", "attendu"),
    [
        ("option.exemple", "variable.exemple", "fichier.exemple", "option.exemple"),
        (None, "variable.exemple", "fichier.exemple", "variable.exemple"),
        (None, None, "fichier.exemple", "fichier.exemple"),
        (None, None, None, "127.0.0.1"),
    ],
    ids=["option", "variable", "fichier", "defaut"],
)
def test_priorites(tmp_path: Path, option: str | None, variable: str | None, fichier: str | None, attendu: str) -> None:
    chemin = ecrire_config(tmp_path, f"[reseau]\nhote = {fichier}\n") if fichier else tmp_path / "absent.ini"
    config = resoudre(
        tmp_path, {"hote": option}, {"CHERRYPIE_HOTE": variable} if variable else {}, chemin_defaut=chemin
    )
    assert config.hote == attendu


def test_chaque_parametre_suit_son_option_et_sa_variable(tmp_path: Path) -> None:
    options = {"hote": "0.0.0.0", "port_tcp": 6000, "bdd_hote": "bdd.local", "bdd_utilisateur": "rond_point"}
    variables = {"CHERRYPIE_PORT_UDP": "6001", "CHERRYPIE_BDD_PORT": "3307", "CHERRYPIE_BDD_NOM": "historique"}
    config = resoudre(tmp_path, options, variables)
    assert (config.hote, config.port_tcp, config.port_udp) == ("0.0.0.0", 6000, 6001)
    assert {cle: valeur for cle, valeur in config.parametres_bdd.items() if cle != "mot_de_passe"} == {
        "hote": "bdd.local", "port": 3307, "utilisateur": "rond_point", "base": "historique"
    }


def test_variable_vide_ignoree(tmp_path: Path) -> None:
    assert resoudre(tmp_path, environnement={"CHERRYPIE_HOTE": ""}).hote == "127.0.0.1"


def test_port_invalide_dans_l_environnement_nomme_la_variable(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationInvalideError, match="CHERRYPIE_PORT_TCP : port entre 1 et 65535"):
        resoudre(tmp_path, environnement={"CHERRYPIE_PORT_TCP": "cinq_mille"})


@pytest.mark.parametrize(
    ("option", "variable", "fichier", "attendu"),
    [(2.5, "30", "10", 2.5), (None, "30", "10", 30.0), (None, None, "10", 10.0), (None, None, None, 5.0)],
    ids=["option", "variable", "fichier", "defaut"],
)
def test_priorites_fenetre_anti_rejeu(
    tmp_path: Path, option: float | None, variable: str | None, fichier: str | None, attendu: float
) -> None:
    texte = f"[securite]\nfenetre_anti_rejeu = {fichier}\n"
    chemin = ecrire_config(tmp_path, texte) if fichier else tmp_path / "absent.ini"
    config = resoudre(
        tmp_path,
        {"fenetre_anti_rejeu": option},
        {"CHERRYPIE_FENETRE_ANTI_REJEU": variable} if variable else {},
        chemin_defaut=chemin,
    )
    assert config.fenetre_anti_rejeu == pytest.approx(attendu)


@pytest.mark.parametrize("texte", ["0", "-5", "nan", "cinq"])
def test_fenetre_invalide_dans_l_environnement_nomme_la_variable(tmp_path: Path, texte: str) -> None:
    with pytest.raises(ConfigurationInvalideError, match="CHERRYPIE_FENETRE_ANTI_REJEU : nombre de secondes"):
        resoudre(tmp_path, environnement={"CHERRYPIE_FENETRE_ANTI_REJEU": texte})


def test_chaque_parametre_a_sa_propre_variable() -> None:
    variables = [variable for _, _, variable, _ in PARAMETRES.values()]
    assert len(set(variables)) == len(variables) and all(nom.startswith("CHERRYPIE_") for nom in variables)


# ---------- Fichier de configuration ----------

def test_sans_fichier_les_valeurs_de_l_exemple(tmp_path: Path) -> None:
    sans_fichier = resoudre(tmp_path, environnement=ENVIRONNEMENT_SECRETS, secrets=("cle", "bdd_mdp"))
    exemple = Configuration.depuis_fichier(CHEMIN_EXEMPLE)
    attendu = valeurs(exemple) | {
        "cle_hmac": b"cle_de_test", "parametres_bdd": exemple.parametres_bdd | {"mot_de_passe": "mdp_de_test"}
    }
    assert valeurs(sans_fichier) == attendu


def test_exemple_lu_par_l_option_config(tmp_path: Path) -> None:
    config = resoudre(tmp_path, {"config": CHEMIN_EXEMPLE})
    assert valeurs(config) == valeurs(Configuration.depuis_fichier(CHEMIN_EXEMPLE))


def test_fichier_par_defaut_lu_s_il_existe(tmp_path: Path) -> None:
    chemin = ecrire_config(tmp_path, "[delais]\nintervalle_ping = 1\n")
    assert resoudre(tmp_path, chemin_defaut=chemin).intervalle_ping == pytest.approx(1.0)


def test_fichier_de_l_option_config_introuvable(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationInvalideError, match=r"introuvable : .*absent\.ini \(option --config\)"):
        resoudre(tmp_path, {"config": tmp_path / "absent.ini"})


def test_branches_du_fichier_remplacent_celles_par_defaut(tmp_path: Path) -> None:
    texte = "[rond_point]\nbranches = a, b, c\n" + "".join(
        f"[branche.{nom}]\nlibelle = Rue {nom}\ncap = {cap}\nterre_plein = 2\npassage_pieton = 6\n"
        for nom, cap in (("a", 0), ("b", 120), ("c", 240))
    )
    config = resoudre(tmp_path, chemin_defaut=ecrire_config(tmp_path, texte))
    assert [branche.nom for branche in config.branches] == ["a", "b", "c"]


def test_valeur_incoherente_du_fichier_refusee(tmp_path: Path) -> None:
    chemin = ecrire_config(tmp_path, "[delais]\ntimeout_client = 1\n")
    with pytest.raises(ConfigurationInvalideError, match="timeout_client"):
        resoudre(tmp_path, chemin_defaut=chemin)


@pytest.mark.parametrize(
    ("ligne", "variable"),
    [("[securite]\ncle_hmac = secret", "CHERRYPIE_CLE"), ("[bdd]\nmot_de_passe = secret", "CHERRYPIE_BDD_MDP")],
    ids=["cle", "mot-de-passe"],
)
def test_secret_dans_le_fichier_refuse(tmp_path: Path, ligne: str, variable: str) -> None:
    chemin = ecrire_config(tmp_path, ligne + "\n")
    with pytest.raises(ConfigurationInvalideError, match=f"n'est plus lu dans ce fichier.*{variable}"):
        resoudre(tmp_path, chemin_defaut=chemin, environnement=ENVIRONNEMENT_SECRETS)


# ---------- Secrets ----------

def test_secrets_lus_dans_l_environnement_sans_saisie(tmp_path: Path) -> None:
    def saisir(_: str) -> str:
        raise AssertionError("aucune saisie attendue")

    config = resoudre(tmp_path, environnement=ENVIRONNEMENT_SECRETS, secrets=("cle", "bdd_mdp"), saisir=saisir)
    assert config.cle_hmac == b"cle_de_test" and config.parametres_bdd["mot_de_passe"] == "mdp_de_test"


@pytest.mark.parametrize(("secret", "variable"), [("cle", "CHERRYPIE_CLE"), ("bdd_mdp", "CHERRYPIE_BDD_MDP")])
def test_secret_absent_hors_terminal_nomme_sa_variable(tmp_path: Path, secret: str, variable: str) -> None:
    with pytest.raises(ConfigurationInvalideError, match=f"{variable} non définie") as erreur:
        resoudre(tmp_path, secrets=(secret,))
    assert "jamais en option" in str(erreur.value)


def test_secret_absent_saisi_dans_le_terminal(tmp_path: Path) -> None:
    invites: list[str] = []

    def saisir(invite: str) -> str:
        invites.append(invite)
        return "mdp saisi"

    config = resoudre(tmp_path, secrets=("bdd_mdp",), saisir=saisir)
    assert config.parametres_bdd["mot_de_passe"] == "mdp saisi"
    assert invites == ["Mot de passe MariaDB (CHERRYPIE_BDD_MDP) : "]


def test_secret_saisi_vide_refuse(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationInvalideError, match="clé HMAC partagée vide"):
        resoudre(tmp_path, secrets=("cle",), saisir=lambda _: "")


def test_secret_non_demande_ni_lu_ni_saisi(tmp_path: Path) -> None:
    config = resoudre(tmp_path, environnement=ENVIRONNEMENT_SECRETS, secrets=("cle",))
    assert config.cle_hmac == b"cle_de_test" and config.parametres_bdd["mot_de_passe"] == ""


@pytest.mark.parametrize("terminal", [False, True])
def test_saisie_masquee_seulement_dans_un_terminal(monkeypatch: pytest.MonkeyPatch, terminal: bool) -> None:
    entree = io.StringIO()
    entree.isatty = lambda: terminal
    monkeypatch.setattr(sys, "stdin", entree)
    assert saisie_masquee() is (getpass.getpass if terminal else None)


# ---------- Options en ligne de commande ----------

def test_options_du_script_seulement() -> None:
    analyseur = creer_analyseur("essai", ["bdd_hote", "bdd_port"])
    arguments = vars(analyseur.parse_args(["--bdd-hote", "bdd.local", "--bdd-port", "3307"]))
    assert arguments == {"config": None, "bdd_hote": "bdd.local", "bdd_port": 3307}
    with pytest.raises(SystemExit):
        analyseur.parse_args(["--hote", "0.0.0.0"])


@pytest.mark.parametrize(
    "arguments",
    [
        ["--port-tcp", "70000"],
        ["--port-tcp", "cinq_mille"],
        ["--hote", ""],
        ["--fenetre-anti-rejeu", "0"],
        ["--fenetre-anti-rejeu", "inf"],
        ["--cle", "secret"],
    ],
    ids=["port-trop-grand", "port-non-entier", "hote-vide", "fenetre-nulle", "fenetre-infinie", "secret-en-option"],
)
def test_option_refusee(arguments: list[str], capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit):
        creer_analyseur("essai", ["hote", "port_tcp", "fenetre_anti_rejeu"], ["cle"]).parse_args(arguments)
    assert arguments[0] in capsys.readouterr().err


def test_fenetre_anti_rejeu_en_secondes() -> None:
    analyseur = creer_analyseur("essai", ["fenetre_anti_rejeu"])
    assert vars(analyseur.parse_args(["--fenetre-anti-rejeu", "45"])) == {"config": None, "fenetre_anti_rejeu": 45.0}
    assert "--fenetre-anti-rejeu SECONDES" in analyseur.format_help()


def test_aide_cite_les_variables_des_secrets() -> None:
    aide = creer_analyseur("essai", ["hote"], ["cle", "bdd_mdp"]).format_help()
    assert "CHERRYPIE_HOTE" in aide and "CHERRYPIE_CLE" in aide and "CHERRYPIE_BDD_MDP" in aide
