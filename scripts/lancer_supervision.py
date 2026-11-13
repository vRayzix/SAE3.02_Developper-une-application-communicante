"""Lance la fenêtre de supervision du rond-point.

Exemple : CHERRYPIE_CLE=... python3 scripts/lancer_supervision.py --hote <adresse de la VM code>
Le serveur peut être lancé avant ou après : la supervision se connecte dès qu'il répond.
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

from cherrypie.commun.erreurs import ConfigurationInvalideError
from cherrypie.commun.resolution import creer_analyseur, resoudre_configuration, saisie_masquee
from cherrypie.ihm.fenetre_supervision import FenetreSupervision

FORMAT_JOURNAL = "%(asctime)s %(levelname)s %(name)s : %(message)s"
FORMAT_DATE = "%Y-%m-%dT%H:%M:%S"
CHEMIN_CONFIG = RACINE / "config.ini"
# Les clients lancés depuis la fenêtre envoient leurs positions en UDP : il faut les deux ports.
PARAMETRES = ["hote", "port_tcp", "port_udp", "fenetre_anti_rejeu"]
SECRETS = ["cle"]
# Qt garde la main dans sa boucle d'événements : ce minuteur la rend à Python assez
# souvent pour qu'un Ctrl+C dans la console soit traité.
INTERVALLE_SIGNAUX_MS = 200


def main(argv: list[str] | None = None) -> int:
    """Résout la configuration, ouvre la fenêtre jusqu'à sa fermeture et renvoie le code de sortie."""
    arguments = creer_analyseur(__doc__, PARAMETRES, SECRETS).parse_args(argv)
    logging.basicConfig(level=logging.INFO, format=FORMAT_JOURNAL, datefmt=FORMAT_DATE)
    try:
        config = resoudre_configuration(vars(arguments), CHEMIN_CONFIG, SECRETS, saisir=saisie_masquee())
    except ConfigurationInvalideError as erreur:
        print(f"Configuration invalide : {erreur}", file=sys.stderr)
        return 1
    # Qt ne reçoit que le nom du programme : les options ont déjà été lues.
    application = QApplication(sys.argv[:1])
    fenetre = FenetreSupervision(config)
    fenetre.showMaximized()
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
