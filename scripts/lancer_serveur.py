"""Lance le serveur du rond-point en console.

Usage : python scripts/lancer_serveur.py [chemin/vers/config.ini]
Sans argument, le fichier config.ini à la racine du dépôt est utilisé.
"""

import logging
import signal
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
# Le paquet n'est pas installé : on rend src/ importable pour ce script.
sys.path.insert(0, str(RACINE / "src"))

from cherrypie.commun.config import Configuration
from cherrypie.commun.erreurs import ConfigurationInvalideError
from cherrypie.serveur.serveur import Serveur

FORMAT_JOURNAL = "%(asctime)s %(levelname)s %(name)s : %(message)s"
FORMAT_DATE = "%Y-%m-%dT%H:%M:%S"


def main() -> int:
    """Charge la configuration, démarre le serveur et le fait tourner jusqu'à Ctrl+C.

    Returns:
        int: code de sortie du programme, 0 si tout s'est bien passé.
    """
    logging.basicConfig(level=logging.INFO, format=FORMAT_JOURNAL, datefmt=FORMAT_DATE)
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else RACINE / "config.ini"
    try:
        config = Configuration.depuis_fichier(chemin)
    except ConfigurationInvalideError as erreur:
        print(f"Configuration invalide : {erreur}", file=sys.stderr)
        if not chemin.exists():
            print("Créez-le à partir de config.exemple.ini (voir le README).", file=sys.stderr)
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
