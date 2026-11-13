"""Paramètres de lancement : option > variable d'environnement > config.ini > valeur par défaut.

La clé HMAC et le mot de passe de la base ne passent ni en option ni par config.ini :
une option se lit dans la liste des processus (ps), et un fichier finit copié ou
versionné. Ils viennent de l'environnement, sinon d'une saisie masquée.
"""

from __future__ import annotations

import argparse
import configparser
import getpass
import os
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from cherrypie.commun.config import PORT_MAX, PORT_MIN, PREFIXE_SECTION_BRANCHE, Configuration, lire_fichier
from cherrypie.commun.erreurs import ConfigurationInvalideError

# Nom de l'option sans « -- » (tirets écrits « _ ») : section et clé de config.ini,
# variable d'environnement, aide.
PARAMETRES = {
    "hote": ("reseau", "hote", "CHERRYPIE_HOTE", "adresse du serveur : celle où il écoute, ou celle où le joindre"),
    "port_tcp": ("reseau", "port_tcp", "CHERRYPIE_PORT_TCP", "port TCP du serveur"),
    "port_udp": ("reseau", "port_udp", "CHERRYPIE_PORT_UDP", "port UDP du serveur, pour les positions"),
    "bdd_hote": ("bdd", "hote", "CHERRYPIE_BDD_HOTE", "adresse du serveur MariaDB"),
    "bdd_port": ("bdd", "port", "CHERRYPIE_BDD_PORT", "port de MariaDB"),
    "bdd_utilisateur": ("bdd", "utilisateur", "CHERRYPIE_BDD_UTILISATEUR", "utilisateur MariaDB"),
    "bdd_nom": ("bdd", "base", "CHERRYPIE_BDD_NOM", "nom de la base"),
}
PARAMETRES_PORT = {"port_tcp", "port_udp", "bdd_port"}
# Nom du secret : section et clé dans la configuration, variable d'environnement, libellé.
SECRETS = {
    "cle": ("securite", "cle_hmac", "CHERRYPIE_CLE", "clé HMAC partagée"),
    "bdd_mdp": ("bdd", "mot_de_passe", "CHERRYPIE_BDD_MDP", "mot de passe MariaDB"),
}
# Les valeurs de config.exemple.ini, sans les secrets : sans fichier, on modélise Bel Air.
DEFAUTS = {
    "reseau": {"hote": "127.0.0.1", "port_tcp": "5050", "port_udp": "5051"},
    "securite": {"fenetre_anti_rejeu": "5"},
    "delais": {
        "intervalle_ping": "2",
        "timeout_client": "6",
        "intervalle_position": "0.2",
        "intervalle_etat": "0.2",
        "backoff_initial": "1",
        "backoff_max": "10",
    },
    "rond_point": {
        "branches": "nations_nord, jean_de_la_bruyere, nations_sud, albert_camus",
        "rayon": "20",
        "largeur_voie_anneau": "4.5",
        "largeur_chaussee": "5",
        "longueur_branche": "50",
        "capacite_par_branche": "8",
    },
    "branche.nations_nord": {
        "libelle": "Bd des Nations (nord)", "cap": "340", "terre_plein": "8", "passage_pieton": "10"
    },
    "branche.jean_de_la_bruyere": {
        "libelle": "Rue Jean de la Bruyère", "cap": "57", "terre_plein": "2.5", "passage_pieton": "8"
    },
    "branche.nations_sud": {
        "libelle": "Bd des Nations (sud)", "cap": "147", "terre_plein": "7.5", "passage_pieton": "6"
    },
    "branche.albert_camus": {
        "libelle": "Rue Albert Camus", "cap": "230", "terre_plein": "3", "passage_pieton": "8"
    },
    "bdd": {
        "hote": "localhost",
        "port": "3306",
        "utilisateur": "cherrypie",
        "base": "cherrypie",
        "delai_connexion": "3",
        "delai_reessai": "10",
        "intervalle_releves": "5",
    },
}


def port(texte: str) -> int:
    """Convertit un numéro de port écrit en texte.

    Raises:
        argparse.ArgumentTypeError: si le texte n'est pas un entier entre 1 et 65535.
    """
    try:
        valeur = int(texte)
    except ValueError:
        valeur = 0
    if not PORT_MIN <= valeur <= PORT_MAX:
        raise argparse.ArgumentTypeError(f"port entre {PORT_MIN} et {PORT_MAX} attendu (lu : {texte!r})")
    return valeur


def texte_non_vide(texte: str) -> str:
    """Refuse une valeur vide.

    Raises:
        argparse.ArgumentTypeError: si le texte est vide.
    """
    if not texte:
        raise argparse.ArgumentTypeError("valeur vide")
    return texte


def creer_analyseur(
    description: str, parametres: Iterable[str], secrets: Iterable[str] = ()
) -> argparse.ArgumentParser:
    """Prépare les options d'un script : --config et les paramètres qu'il utilise.

    Args:
        description (str): texte affiché par --help, en général la docstring du script.
        parametres (Iterable[str]): clés de PARAMETRES à proposer en option.
        secrets (Iterable[str]): clés de SECRETS que le script demande, citées par --help.

    Returns:
        argparse.ArgumentParser: l'analyseur, prêt pour parse_args().
    """
    lignes_secrets = [f"  {SECRETS[nom][2]:<20} {SECRETS[nom][3]}" for nom in secrets]
    epilogue = "Chaque valeur vient de son option, sinon de sa variable d'environnement, sinon de config.ini,\n"
    epilogue += "sinon de la valeur par défaut (celle de config.exemple.ini)."
    if lignes_secrets:
        epilogue += "\n\nSecrets, jamais en option : variable d'environnement, sinon saisie masquée.\n"
        epilogue += "\n".join(lignes_secrets)
    analyseur = argparse.ArgumentParser(
        description=description, epilog=epilogue, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    analyseur.add_argument(
        "--config",
        type=Path,
        metavar="FICHIER",
        help="config.ini facultatif (défaut : celui de la racine du dépôt, s'il existe)",
    )
    for nom in parametres:
        section, cle, variable, aide = PARAMETRES[nom]
        analyseur.add_argument(
            "--" + nom.replace("_", "-"),
            type=port if nom in PARAMETRES_PORT else texte_non_vide,
            metavar="PORT" if nom in PARAMETRES_PORT else cle.upper().replace("HOTE", "ADRESSE"),
            help=f"{aide} ({variable}, [{section}] {cle})",
        )
    return analyseur


def saisie_masquee() -> Callable[[str], str] | None:
    """Renvoie getpass.getpass si l'entrée standard est un terminal, None sinon."""
    return getpass.getpass if sys.stdin is not None and sys.stdin.isatty() else None


def resoudre_configuration(
    arguments: Mapping[str, object],
    chemin_defaut: Path,
    secrets: Iterable[str] = (),
    environnement: Mapping[str, str] | None = None,
    saisir: Callable[[str], str] | None = None,
) -> Configuration:
    """Construit la configuration à partir des options, de l'environnement, de config.ini et des défauts.

    Args:
        arguments (Mapping[str, object]): options analysées (vars(analyseur.parse_args())) ;
            une option absente vaut None.
        chemin_defaut (Path): config.ini lu quand --config n'est pas donné, s'il existe.
        secrets (Iterable[str]): clés de SECRETS dont le programme a besoin.
        environnement (Mapping[str, str] | None): variables d'environnement, os.environ par défaut.
        saisir (Callable[[str], str] | None): saisie masquée d'un secret absent de
            l'environnement (voir saisie_masquee), None hors d'un terminal.

    Returns:
        Configuration: la configuration validée.

    Raises:
        ConfigurationInvalideError: fichier introuvable, secret absent ou valeur incohérente ;
            le message nomme l'option ou la variable qui manque.
    """
    environnement = os.environ if environnement is None else environnement
    parseur = configparser.ConfigParser(interpolation=None)
    parseur.read_dict(DEFAUTS)
    chemin = arguments.get("config")
    if chemin is not None and not Path(chemin).is_file():
        raise ConfigurationInvalideError(f"fichier introuvable : {chemin} (option --config)")
    if chemin is None and chemin_defaut.is_file():
        chemin = chemin_defaut
    if chemin is not None:
        fusionner_fichier(parseur, lire_fichier(chemin), chemin)
    for nom, (section, cle, variable, _) in PARAMETRES.items():
        valeur = arguments.get(nom)
        if valeur is None and environnement.get(variable):
            valeur = convertir_variable(nom, variable, environnement[variable])
        if valeur is not None:
            parseur[section][cle] = str(valeur)
    for nom in secrets:
        section, cle, _, _ = SECRETS[nom]
        parseur[section][cle] = lire_secret(nom, environnement, saisir)
    return Configuration(parseur)


def fusionner_fichier(
    parseur: configparser.ConfigParser, fichier: configparser.ConfigParser, chemin: str | Path
) -> None:
    """Applique le contenu de config.ini par-dessus les valeurs par défaut."""
    for section, cle, variable, _ in SECRETS.values():
        if fichier.has_option(section, cle):
            raise ConfigurationInvalideError(
                f"{chemin} : [{section}] {cle} n'est plus lu dans ce fichier ; "
                f"retirez-le et donnez la valeur par la variable d'environnement {variable} ou à la saisie"
            )
    # Un fichier qui liste ses propres branches remplace celles de Bel Air, sinon les
    # sections par défaut resteraient sans branche correspondante.
    if fichier.has_option("rond_point", "branches"):
        for section in parseur.sections():
            if section.startswith(PREFIXE_SECTION_BRANCHE):
                parseur.remove_section(section)
    parseur.read_dict(fichier)


def convertir_variable(nom: str, variable: str, texte: str) -> str | int:
    """Vérifie la valeur d'une variable d'environnement comme le ferait son option."""
    try:
        return port(texte) if nom in PARAMETRES_PORT else texte
    except argparse.ArgumentTypeError as erreur:
        raise ConfigurationInvalideError(f"variable d'environnement {variable} : {erreur}") from None


def lire_secret(nom: str, environnement: Mapping[str, str], saisir: Callable[[str], str] | None) -> str:
    """Lit un secret dans l'environnement, sinon le fait saisir."""
    _, _, variable, libelle = SECRETS[nom]
    if environnement.get(variable):
        return environnement[variable]
    if saisir is None:
        raise ConfigurationInvalideError(
            f"{variable} non définie : {libelle} à donner par cette variable d'environnement, "
            "ou à saisir en lançant le programme dans un terminal (jamais en option)"
        )
    valeur = saisir(f"{libelle[0].upper()}{libelle[1:]} ({variable}) : ")
    if not valeur:
        raise ConfigurationInvalideError(f"{libelle} vide")
    return valeur
