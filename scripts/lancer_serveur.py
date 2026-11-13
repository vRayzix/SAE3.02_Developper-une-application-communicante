"""Lance le serveur du rond-point en console.

Exemple : CHERRYPIE_CLE=... python3 scripts/lancer_serveur.py --hote 0.0.0.0 --bdd-hote <adresse de la VM bdd>
"""

import logging
import signal
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
# Le paquet n'est pas installé : on rend src/ importable pour ce script.
sys.path.insert(0, str(RACINE / "src"))

from cherrypie.commun.erreurs import ConfigurationInvalideError
from cherrypie.commun.resolution import creer_analyseur, resoudre_configuration, saisie_masquee
from cherrypie.serveur.serveur import Serveur

FORMAT_JOURNAL = "%(asctime)s %(levelname)s %(name)s : %(message)s"
FORMAT_DATE = "%Y-%m-%dT%H:%M:%S"
CHEMIN_CONFIG = RACINE / "config.ini"
PARAMETRES = ["hote", "port_tcp", "port_udp", "bdd_hote", "bdd_port", "bdd_utilisateur", "bdd_nom"]
SECRETS = ["cle", "bdd_mdp"]


def main(argv: list[str] | None = None) -> int:
    """Résout la configuration, démarre le serveur et le fait tourner jusqu'à Ctrl+C.

    Args:
        argv (list[str] | None): arguments de la ligne de commande, sys.argv[1:] par défaut.

    Returns:
        int: code de sortie du programme, 0 si tout s'est bien passé.
    """
    arguments = creer_analyseur(__doc__, PARAMETRES, SECRETS).parse_args(argv)
    logging.basicConfig(level=logging.INFO, format=FORMAT_JOURNAL, datefmt=FORMAT_DATE)
    try:
        config = resoudre_configuration(vars(arguments), CHEMIN_CONFIG, SECRETS, saisir=saisie_masquee())
    except ConfigurationInvalideError as erreur:
        print(f"Configuration invalide : {erreur}", file=sys.stderr)
        return 1
    serveur = Serveur(config)
    try:
        serveur.demarrer()
    except OSError as erreur:
        print(
            f"Impossible d'ouvrir le port TCP {config.port_tcp} ou le port UDP {config.port_udp} : {erreur}",
            file=sys.stderr,
        )
        return 1
    # Un kill (SIGTERM) arrête le serveur aussi proprement que Ctrl+C.
    signal.signal(signal.SIGTERM, lambda *_: serveur.arreter())
    print(
        f"Serveur du rond-point démarré sur {config.hote} "
        f"(TCP {config.port_tcp}, UDP {config.port_udp}). Ctrl+C pour l'arrêter.",
        flush=True,
    )
    try:
        serveur.servir()
    except KeyboardInterrupt:
        # servir() a déjà fermé ses sockets en sortant.
        print("Arrêt demandé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
