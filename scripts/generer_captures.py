"""Génère les captures d'écran de la supervision citées dans le README.

Usage : python scripts/generer_captures.py [dossier]
Sans argument, les images vont dans docs/captures/. Le script lance un serveur et la
fenêtre de supervision dans ce processus, sur des ports libres et sans rien afficher
(plateforme Qt offscreen). Il joue deux fois le même trafic, avec puis sans régulation,
et prend chaque capture au même délai après le départ du véhicule prioritaire.
"""

import configparser
import logging
import os
import socket
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
# Le paquet n'est pas installé : on rend src/ importable pour ce script.
sys.path.insert(0, str(RACINE / "src"))
# La plateforme est lue à la création de l'application Qt : il faut la fixer avant.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from cherrypie.commun.config import Configuration
from cherrypie.ihm.fenetre_supervision import FenetreSupervision
from cherrypie.serveur.serveur import Serveur

# Trafic joué avant l'arrivée du VP : (catégorie, entrée, sortie, nombre).
TRAFIC = [
    ("voiture", "S", "O", 3),
    ("voiture", "E", "S", 2),
    ("moto", "O", "N", 1),
    ("trottinette", "N", "E", 1),
    ("pieton", "N", "N", 1),
]
VP = ("vp", "S", "N", 1)
# Délais en secondes : le temps que le trafic arrive au rond-point, puis celui laissé au VP.
# Au bout de 6 s, le VP régulé roule sur l'anneau, l'autre attend encore derrière la file.
DELAI_AVANT_VP = 3.5
DELAI_CAPTURE_VP = 6.0
DELAI_CONNEXION = 5.0
PAUSE_BOUCLE = 0.01


def configuration() -> Configuration:
    """Reprend config.exemple.ini, sur 127.0.0.1 et des ports libres."""
    parseur = configparser.ConfigParser(interpolation=None)
    parseur.read(RACINE / "config.exemple.ini", encoding="utf-8")
    parseur["reseau"]["hote"] = "127.0.0.1"
    for cle, type_socket in (("port_tcp", socket.SOCK_STREAM), ("port_udp", socket.SOCK_DGRAM)):
        with socket.socket(socket.AF_INET, type_socket) as prise:
            prise.bind(("127.0.0.1", 0))
            parseur["reseau"][cle] = str(prise.getsockname()[1])
    return Configuration(parseur)


def patienter(duree: float) -> None:
    """Laisse tourner la boucle Qt pendant une durée, pour que la fenêtre reçoive les STATE."""
    fin = time.monotonic() + duree
    while time.monotonic() < fin:
        QCoreApplication.processEvents()
        time.sleep(PAUSE_BOUCLE)


def patienter_jusqu_a(condition: Callable[[], bool], description: str) -> None:
    """Laisse tourner la boucle Qt jusqu'à ce qu'une condition soit vraie."""
    fin = time.monotonic() + DELAI_CONNEXION
    while not condition():
        if time.monotonic() > fin:
            raise TimeoutError(f"délai dépassé en attendant : {description}")
        QCoreApplication.processEvents()
        time.sleep(PAUSE_BOUCLE)


def lancer(fenetre: FenetreSupervision, categorie: str, entree: str, sortie: str, nombre: int) -> None:
    """Lance des usagers depuis le panneau de création, comme le ferait l'utilisateur."""
    panneau = fenetre.panneau_creation
    panneau.choix_categorie.setCurrentIndex(panneau.choix_categorie.findData(categorie))
    panneau.choix_entree.setCurrentText(entree)
    panneau.choix_sortie.setCurrentText(sortie)
    panneau.choix_nombre.setValue(nombre)
    panneau.lancer()


def jouer(regulation: bool, dossier: Path, capturer_repos: bool) -> None:
    """Joue le scénario sur un serveur neuf et enregistre les captures."""
    config = configuration()
    serveur = Serveur(config)
    serveur.demarrer()
    fil_serveur = threading.Thread(target=serveur.servir, daemon=True)
    fil_serveur.start()
    fenetre = FenetreSupervision(config)
    fenetre.show()
    fenetre.demarrer()
    patienter_jusqu_a(lambda: fenetre.indicateur_regulation.text() == "active", "connexion de la supervision")
    if not regulation:
        fenetre.case_regulation.click()
        patienter_jusqu_a(lambda: fenetre.indicateur_regulation.text() == "inactive", "régulation coupée")
    for usagers in TRAFIC:
        lancer(fenetre, *usagers)
    patienter(DELAI_AVANT_VP)
    if capturer_repos:
        enregistrer(fenetre, dossier / "repos.png")
    lancer(fenetre, *VP)
    patienter(DELAI_CAPTURE_VP)
    enregistrer(fenetre, dossier / f"vp_{'avec' if regulation else 'sans'}_regulation.png")
    fenetre.close()
    serveur.arreter()
    fil_serveur.join()


def enregistrer(fenetre: FenetreSupervision, chemin: Path) -> None:
    """Enregistre une capture de la fenêtre."""
    if not fenetre.grab().save(str(chemin)):
        raise OSError(f"capture non enregistrée : {chemin}")
    print(f"Capture enregistrée : {chemin.relative_to(RACINE) if chemin.is_relative_to(RACINE) else chemin}")


def main() -> int:
    """Génère les trois captures : rond-point au repos, VP avec régulation, VP sans régulation.

    Returns:
        int: code de sortie du programme, 0 si tout s'est bien passé.
    """
    logging.basicConfig(level=logging.WARNING)
    dossier = Path(sys.argv[1]) if len(sys.argv) > 1 else RACINE / "docs" / "captures"
    dossier.mkdir(parents=True, exist_ok=True)
    application = QApplication(sys.argv)
    try:
        jouer(regulation=True, dossier=dossier, capturer_repos=True)
        jouer(regulation=False, dossier=dossier, capturer_repos=False)
    except (OSError, TimeoutError) as erreur:
        print(f"Captures interrompues : {erreur}", file=sys.stderr)
        return 1
    finally:
        application.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
