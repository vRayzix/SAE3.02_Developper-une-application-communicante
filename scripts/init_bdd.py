"""Crée les tables de l'historique dans la base MariaDB.

Exemple : CHERRYPIE_BDD_MDP=... python3 scripts/init_bdd.py --bdd-hote <adresse de la VM bdd>
Le script exécute src/cherrypie/bdd/schema.sql et dit clairement ce qui ne va pas :
serveur injoignable, accès refusé ou base absente. Il peut être relancé sans rien perdre.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
# Le paquet n'est pas installé : on rend src/ importable pour ce script.
sys.path.insert(0, str(RACINE / "src"))

from cherrypie.bdd.acces_bdd import AccesBdd
from cherrypie.commun.erreurs import (
    AccesBddRefuseError,
    BaseAbsenteError,
    BddError,
    BddInjoignableError,
    ConfigurationInvalideError,
)
from cherrypie.commun.resolution import creer_analyseur, resoudre_configuration, saisie_masquee

SCHEMA = RACINE / "src" / "cherrypie" / "bdd" / "schema.sql"
CHEMIN_CONFIG = RACINE / "config.ini"
PARAMETRES = ["bdd_hote", "bdd_port", "bdd_utilisateur", "bdd_nom"]
SECRETS = ["bdd_mdp"]
# Ce qu'il faut vérifier pour chaque cause d'échec, en plus du message de l'erreur.
CONSEILS = {
    BddInjoignableError: (
        "Vérifiez que MariaDB tourne (systemctl status mariadb), que --bdd-hote et --bdd-port sont justes,\n"
        "que bind-address autorise les connexions distantes et que le pare-feu laisse passer le port 3306."
    ),
    AccesBddRefuseError: (
        "Vérifiez --bdd-utilisateur et CHERRYPIE_BDD_MDP, et que l'utilisateur est autorisé depuis l'adresse\n"
        "de cette machine (CREATE USER 'cherrypie'@'<adresse>' ... ; GRANT ... ; voir le README)."
    ),
    BaseAbsenteError: "Créez-la sur le serveur MariaDB : CREATE DATABASE cherrypie CHARACTER SET utf8mb4;",
}


def main(argv: list[str] | None = None) -> int:
    """Résout la configuration, se connecte à la base et crée les tables.

    Args:
        argv (list[str] | None): arguments de la ligne de commande, sys.argv[1:] par défaut.

    Returns:
        int: code de sortie du programme, 0 si les tables sont prêtes.
    """
    arguments = creer_analyseur(__doc__, PARAMETRES, SECRETS).parse_args(argv)
    try:
        config = resoudre_configuration(vars(arguments), CHEMIN_CONFIG, SECRETS, saisir=saisie_masquee())
    except ConfigurationInvalideError as erreur:
        print(f"Configuration invalide : {erreur}", file=sys.stderr)
        return 1
    acces = AccesBdd(config.parametres_bdd, config.delai_connexion_bdd)
    try:
        acces.connecter()
        acces.executer_script(SCHEMA.read_text(encoding="utf-8"))
    except BddError as erreur:
        print(f"Échec : {erreur}", file=sys.stderr)
        conseil = CONSEILS.get(type(erreur))
        if conseil is not None:
            print(conseil, file=sys.stderr)
        return 1
    finally:
        acces.fermer()
    print(f"Base prête sur {acces.adresse} : tables passage_vp, releve_densite et evenement_connexion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
