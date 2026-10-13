"""Crée les tables de l'historique dans la base MariaDB décrite par config.ini.

Usage : python scripts/init_bdd.py [chemin/vers/config.ini]
Sans argument, le fichier config.ini à la racine du dépôt est utilisé. Le script se
connecte avec les identifiants de la section [bdd], exécute src/cherrypie/bdd/schema.sql
et dit clairement ce qui ne va pas : serveur injoignable, accès refusé ou base absente.
Il peut être relancé sans rien perdre.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
# Le paquet n'est pas installé : on rend src/ importable pour ce script.
sys.path.insert(0, str(RACINE / "src"))

from cherrypie.bdd.acces_bdd import AccesBdd
from cherrypie.commun.config import Configuration
from cherrypie.commun.erreurs import (
    AccesBddRefuseError,
    BaseAbsenteError,
    BddError,
    BddInjoignableError,
    ConfigurationInvalideError,
)

SCHEMA = RACINE / "src" / "cherrypie" / "bdd" / "schema.sql"
# Ce qu'il faut vérifier pour chaque cause d'échec, en plus du message de l'erreur.
CONSEILS = {
    BddInjoignableError: (
        "Vérifiez que MariaDB tourne (sudo systemctl status mariadb), que [bdd] hote et port sont justes,\n"
        "que bind-address autorise les connexions distantes et que le pare-feu laisse passer le port 3306."
    ),
    AccesBddRefuseError: (
        "Vérifiez [bdd] utilisateur et mot_de_passe, et que l'utilisateur est autorisé depuis l'adresse\n"
        "de cette machine (CREATE USER 'cherrypie'@'<adresse>' ... ; GRANT ... ; voir le README)."
    ),
    BaseAbsenteError: "Créez-la sur le serveur MariaDB : CREATE DATABASE cherrypie CHARACTER SET utf8mb4;",
}


def main() -> int:
    """Charge la configuration, se connecte à la base et crée les tables.

    Returns:
        int: code de sortie du programme, 0 si les tables sont prêtes.
    """
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else RACINE / "config.ini"
    try:
        config = Configuration.depuis_fichier(chemin)
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
