"""Génère les captures d'écran de la supervision citées dans le README.

Usage : python scripts/generer_captures.py [dossier]
Sans argument, les images vont dans docs/captures/. Le script lance un serveur et la
fenêtre de supervision dans ce processus, sur des ports libres et sans rien afficher
(plateforme Qt offscreen). Il compose le même scénario dans la section « Scénario » et le
joue deux fois, avec puis sans régulation, en prenant chaque capture au même délai après
le départ du véhicule prioritaire. Pendant le passage régulé, il capture aussi la fenêtre
à trois tailles d'écran et la section « Suivi ». Les deux serveurs écrivent leur historique
dans la même base en mémoire, la doublure des tests : l'onglet « Statistiques », capturé à
la fin, compare les deux traversées sans demander de MariaDB.
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
# Le paquet n'est pas installé : on rend src/ importable pour ce script, et tests/ pour la
# doublure de la base.
sys.path.insert(0, str(RACINE / "src"))
sys.path.insert(0, str(RACINE / "tests"))
# La plateforme est lue à la création de l'application Qt : il faut la fixer avant.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from doublure_bdd import DoublureBdd

from cherrypie.commun.config import Configuration
from cherrypie.ihm.fenetre_supervision import FenetreSupervision
from cherrypie.serveur.serveur import Serveur

# Lignes du scénario : (catégorie, entrée, sortie, nombre, délai depuis la ligne précédente).
# Le trafic part d'un coup ; le VP part quand il est arrivé au rond-point.
DELAI_AVANT_VP = 3.5
SCENARIO = [
    ("voiture", "nations_sud", "albert_camus", 3, 0.0),
    ("voiture", "jean_de_la_bruyere", "nations_sud", 2, 0.0),
    ("moto", "albert_camus", "nations_nord", 1, 0.0),
    ("trottinette", "nations_nord", "jean_de_la_bruyere", 1, 0.0),
    ("pieton", "nations_nord", "nations_nord", 1, 0.0),
    ("vp", "nations_sud", "nations_nord", 1, DELAI_AVANT_VP),
]
# Délais en secondes : la capture au repos précède le départ du VP ; au bout de 8 s, le VP
# régulé roule sur l'anneau, l'autre attend encore derrière la file.
DELAI_CAPTURE_REPOS = 3.0
DELAI_CAPTURE_VP = 8.0
# Avec régulation, le VP double les voitures rangées de sa branche à peu près à ce délai après son départ.
DELAI_CAPTURE_DEPASSEMENT = 2.4
# Taille des captures principales, puis tailles d'écran de portable vérifiées.
TAILLE_CAPTURE = (1280, 720)
TAILLES_ECRAN = [(1024, 640), (1280, 720), (1440, 800)]
# Temps laissé à la fenêtre pour se redisposer après un changement de taille ou d'onglet.
DELAI_DISPOSITION = 0.3
ONGLET_SUIVI = 1
DELAI_CONNEXION = 5.0
# Attente maximale de la fin de la traversée du VP, mesurée au VP_FIN, en secondes.
DELAI_FIN_TRAVERSEE = 30.0
# Relevés de densité plus serrés que dans l'exemple, pour que les courbes aient des points.
INTERVALLE_RELEVES = "1"
PAUSE_BOUCLE = 0.01


def configuration() -> Configuration:
    """Reprend config.exemple.ini, sur 127.0.0.1 et des ports libres."""
    parseur = configparser.ConfigParser(interpolation=None)
    parseur.read(RACINE / "config.exemple.ini", encoding="utf-8")
    parseur["reseau"]["hote"] = "127.0.0.1"
    parseur["bdd"]["intervalle_releves"] = INTERVALLE_RELEVES
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


def patienter_jusqu_a(condition: Callable[[], bool], description: str, delai: float = DELAI_CONNEXION) -> None:
    """Laisse tourner la boucle Qt jusqu'à ce qu'une condition soit vraie, au plus `delai` secondes."""
    fin = time.monotonic() + delai
    while not condition():
        if time.monotonic() > fin:
            raise TimeoutError(f"délai dépassé en attendant : {description}")
        QCoreApplication.processEvents()
        time.sleep(PAUSE_BOUCLE)


def composer(fenetre: FenetreSupervision) -> None:
    """Compose le scénario dans la section « Scénario », comme le ferait l'utilisateur."""
    panneau = fenetre.panneau_scenario
    for categorie, entree, sortie, nombre, delai in SCENARIO:
        panneau.choix_categorie.setCurrentIndex(panneau.choix_categorie.findData(categorie))
        panneau.choix_entree.setCurrentIndex(panneau.choix_entree.findData(entree))
        panneau.choix_sortie.setCurrentIndex(panneau.choix_sortie.findData(sortie))
        panneau.choix_nombre.setValue(nombre)
        panneau.choix_delai.setValue(delai)
        panneau.ajouter()


def jouer(regulation: bool, dossier: Path, base: DoublureBdd) -> None:
    """Joue le scénario sur un serveur neuf, qui écrit dans la base donnée, et enregistre les captures."""
    config = configuration()
    serveur = Serveur(config, base)
    serveur.demarrer()
    fil_serveur = threading.Thread(target=serveur.servir, daemon=True)
    fil_serveur.start()
    fenetre = FenetreSupervision(config)
    fenetre.resize(*TAILLE_CAPTURE)
    fenetre.show()
    fenetre.demarrer()
    patienter_jusqu_a(lambda: fenetre.indicateur_regulation.text() == "active", "connexion de la supervision")
    if not regulation:
        fenetre.case_regulation.click()
        patienter_jusqu_a(lambda: fenetre.indicateur_regulation.text() == "inactive", "régulation coupée")
    composer(fenetre)
    fenetre.panneau_scenario.lancer()
    patienter(DELAI_CAPTURE_REPOS)
    if regulation:
        enregistrer(fenetre, dossier / "repos.png")
        patienter(DELAI_AVANT_VP - DELAI_CAPTURE_REPOS + DELAI_CAPTURE_DEPASSEMENT)
        enregistrer(fenetre, dossier / "vp_double.png")
        patienter(DELAI_CAPTURE_VP - DELAI_CAPTURE_DEPASSEMENT)
    else:
        patienter(DELAI_AVANT_VP - DELAI_CAPTURE_REPOS + DELAI_CAPTURE_VP)
    enregistrer(fenetre, dossier / f"vp_{'avec' if regulation else 'sans'}_regulation.png")
    if regulation:
        capturer_les_tailles(fenetre, dossier)
    # La traversée n'est mesurée qu'au VP_FIN : on l'attend avant de tout fermer.
    patienter_jusqu_a(lambda: bool(serveur.logique.passages), "fin de la traversée du VP", DELAI_FIN_TRAVERSEE)
    if not regulation:
        capturer_les_statistiques(fenetre, dossier)
    fenetre.close()
    serveur.arreter()
    fil_serveur.join()


def capturer_les_tailles(fenetre: FenetreSupervision, dossier: Path) -> None:
    """Capture la fenêtre à chaque taille d'écran, puis la section « Suivi »."""
    for largeur, hauteur in TAILLES_ECRAN:
        fenetre.resize(largeur, hauteur)
        patienter(DELAI_DISPOSITION)
        enregistrer(fenetre, dossier / f"fenetre_{largeur}x{hauteur}.png")
    fenetre.resize(*TAILLE_CAPTURE)
    fenetre.sections.setCurrentIndex(ONGLET_SUIVI)
    patienter(DELAI_DISPOSITION)
    enregistrer(fenetre, dossier / "suivi.png")


def capturer_les_statistiques(fenetre: FenetreSupervision, dossier: Path) -> None:
    """Ouvre l'onglet « Statistiques », qui les demande au serveur, puis le capture."""
    fenetre.onglets.setCurrentWidget(fenetre.panneau_stats)
    patienter_jusqu_a(lambda: "traversée(s) de VP" in fenetre.panneau_stats.etat.text(), "statistiques du serveur")
    patienter(DELAI_DISPOSITION)
    enregistrer(fenetre, dossier / "statistiques.png")


def enregistrer(fenetre: FenetreSupervision, chemin: Path) -> None:
    """Enregistre une capture de la fenêtre."""
    if not fenetre.grab().save(str(chemin)):
        raise OSError(f"capture non enregistrée : {chemin}")
    print(f"Capture enregistrée : {chemin.relative_to(RACINE) if chemin.is_relative_to(RACINE) else chemin}")


def main() -> int:
    """Génère les captures : repos, VP qui double, VP avec et sans régulation, tailles, « Suivi » et statistiques.

    Returns:
        int: code de sortie du programme, 0 si tout s'est bien passé.
    """
    logging.basicConfig(level=logging.WARNING)
    dossier = Path(sys.argv[1]) if len(sys.argv) > 1 else RACINE / "docs" / "captures"
    dossier.mkdir(parents=True, exist_ok=True)
    application = QApplication(sys.argv)
    try:
        base = DoublureBdd()
        jouer(regulation=True, dossier=dossier, base=base)
        jouer(regulation=False, dossier=dossier, base=base)
    except (OSError, TimeoutError) as erreur:
        print(f"Captures interrompues : {erreur}", file=sys.stderr)
        return 1
    finally:
        application.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
