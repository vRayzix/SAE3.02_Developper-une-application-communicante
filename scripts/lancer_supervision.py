"""Lance la fenêtre de supervision du rond-point.

Usage : python scripts/lancer_supervision.py [chemin/vers/config.ini]
Sans argument, le fichier config.ini à la racine du dépôt est utilisé. Le serveur peut
être lancé avant ou après : la supervision se connecte dès qu'il répond.
"""

import logging
import signal
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
# Le paquet n'est pas installé : on rend src/ importable pour ce script.
sys.path.insert(0, str(RACINE / "src"))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from cherrypie.commun.config import Configuration
from cherrypie.commun.erreurs import ConfigurationInvalideError
from cherrypie.ihm.fenetre_supervision import FenetreSupervision

FORMAT_JOURNAL = "%(asctime)s %(levelname)s %(name)s : %(message)s"
FORMAT_DATE = "%Y-%m-%dT%H:%M:%S"
# Qt garde la main dans sa boucle d'événements : ce minuteur la rend à Python assez
# souvent pour qu'un Ctrl+C dans la console soit traité.
INTERVALLE_SIGNAUX_MS = 200


def main() -> int:
    """Charge la configuration, ouvre la fenêtre et la fait tourner jusqu'à sa fermeture.

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
    application = QApplication(sys.argv)
    fenetre = FenetreSupervision(config)
    fenetre.show()
    fenetre.demarrer()
    # Ctrl+C ferme la fenêtre, qui arrête alors ses threads comme avec le bouton de fermeture.
    signal.signal(signal.SIGINT, lambda *_: fenetre.close())
    signal.signal(signal.SIGTERM, lambda *_: fenetre.close())
    minuteur = QTimer()
    minuteur.timeout.connect(lambda: None)
    minuteur.start(INTERVALLE_SIGNAUX_MS)
    print(f"Supervision lancée, serveur attendu sur {config.hote}:{config.port_tcp}. Ctrl+C pour fermer.", flush=True)
    return application.exec()


if __name__ == "__main__":
    sys.exit(main())
