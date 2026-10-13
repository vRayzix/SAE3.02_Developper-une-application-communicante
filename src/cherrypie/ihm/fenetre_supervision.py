"""Fenêtre de supervision : le rond-point en 2D, l'état du serveur, le scénario de lancement et le suivi."""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QCloseEvent, QColor, QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cherrypie.client.client_usager import EtatConnexion
from cherrypie.commun.config import Configuration
from cherrypie.ihm.lanceur_clients import LanceurClients
from cherrypie.ihm.legende import Legende
from cherrypie.ihm.panneau_scenario import PanneauScenario
from cherrypie.ihm.panneau_stats import PanneauStats
from cherrypie.ihm.panneau_suivi import PanneauSuivi
from cherrypie.ihm.scene_rond_point import SceneRondPoint, VueRondPoint
from cherrypie.ihm.style import (
    COULEUR_INDICATEUR_ACTIF,
    COULEUR_INDICATEUR_INACTIF,
    COULEURS_CATEGORIE,
    LIBELLES_CONNEXION,
)
from cherrypie.ihm.thread_reseau import ReseauSupervision
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.usager import VehiculePrioritaire

TITRE = "CherryPie : supervision du rond-point"
# Taille en dessous de laquelle la fenêtre ne descend pas : tout reste lisible sur l'écran d'un portable.
LARGEUR_MINIMALE = 1000
HAUTEUR_MINIMALE = 640
# À l'ouverture, la fenêtre prend cette part de l'écran.
PART_ECRAN = 0.85
# La largeur se partage entre la scène et le panneau latéral selon ces parts, à l'ouverture comme quand elle change.
PARTS_SCENE = 3
PARTS_PANNEAU = 2
COLONNES_LEGENDE = 4
# Attente maximale de l'arrêt du thread réseau à la fermeture, en secondes.
DELAI_ARRET = 2.0
MILLISECONDES_PAR_SECONDE = 1000
INCONNU = "inconnue"

journal = logging.getLogger(__name__)


class FenetreSupervision(QMainWindow):
    """Fenêtre principale de la supervision.

    L'onglet « Rond-point » montre à gauche la scène 2D et sa légende, à droite l'état du
    serveur avec l'interrupteur de régulation, puis deux sections : « Scénario », où l'on
    compose et lance les usagers, et « Suivi », qui montre les clients en route, leurs
    consignes et les événements du serveur. L'onglet « Statistiques » montre les temps de
    traversée du VP et la densité dans le temps, que le serveur lit en base à la demande.
    Le réseau tourne dans un QThread ; tout ce qu'il reçoit arrive ici par signaux Qt,
    dans le thread de l'IHM. La fenêtre n'interprète rien : elle affiche
    l'état diffusé par le serveur.
    """

    def __init__(self, config: Configuration) -> None:
        """Construit la fenêtre et prépare le réseau ; demarrer() le lance.

        Args:
            config (Configuration): configuration partagée avec le serveur.
        """
        super().__init__()
        self.__config = config
        self.__scene = SceneRondPoint(RondPoint.depuis_config(config))
        self.__vue = VueRondPoint(self.__scene)
        self.__legende = Legende(COLONNES_LEGENDE)
        self.__lanceur = LanceurClients(config)
        self.__panneau_scenario = PanneauScenario(self.__lanceur)
        self.__panneau_suivi = PanneauSuivi(self.__lanceur)
        self.__panneau_stats = PanneauStats({branche.nom: branche.libelle for branche in config.branches})
        self.__etat_connexion = QLabel(LIBELLES_CONNEXION[EtatConnexion.DECONNECTE])
        self.__indicateur_regulation = QLabel(INCONNU)
        self.__indicateur_vp = QLabel(INCONNU)
        self.__case_regulation = QCheckBox("Régulation active")
        self.__case_regulation.setEnabled(False)
        self.__sections = QTabWidget()
        self.__panneau_lateral = QScrollArea()
        self.__separateur = QSplitter()
        self.__onglets = QTabWidget()
        # Après chaque connexion, la case reprend l'état du serveur au premier STATE reçu.
        self.__case_a_aligner = True
        self.__fil = QThread(self)
        self.__reseau = ReseauSupervision(config)
        self.__reseau.moveToThread(self.__fil)
        self.__relier()
        self.__disposer()

    @property
    def config(self) -> Configuration:
        """Configuration: configuration de la supervision."""
        return self.__config

    @property
    def scene(self) -> SceneRondPoint:
        """SceneRondPoint: scène 2D du rond-point."""
        return self.__scene

    @property
    def vue(self) -> VueRondPoint:
        """VueRondPoint: vue qui affiche la scène."""
        return self.__vue

    @property
    def legende(self) -> Legende:
        """Legende: légende de la scène."""
        return self.__legende

    @property
    def lanceur(self) -> LanceurClients:
        """LanceurClients: lanceur des clients usagers locaux."""
        return self.__lanceur

    @property
    def panneau_scenario(self) -> PanneauScenario:
        """PanneauScenario: section qui compose et lance le scénario."""
        return self.__panneau_scenario

    @property
    def panneau_suivi(self) -> PanneauSuivi:
        """PanneauSuivi: section qui suit les clients lancés et leurs consignes."""
        return self.__panneau_suivi

    @property
    def panneau_stats(self) -> PanneauStats:
        """PanneauStats: onglet des statistiques, lues en base par le serveur."""
        return self.__panneau_stats

    @property
    def sections(self) -> QTabWidget:
        """QTabWidget: sections « Scénario » et « Suivi » du panneau latéral."""
        return self.__sections

    @property
    def panneau_lateral(self) -> QScrollArea:
        """QScrollArea: panneau à droite de la scène, qui défile s'il manque de hauteur."""
        return self.__panneau_lateral

    @property
    def separateur(self) -> QSplitter:
        """QSplitter: séparateur déplaçable entre la scène et le panneau latéral."""
        return self.__separateur

    @property
    def etat_connexion(self) -> QLabel:
        """QLabel: état de la connexion au serveur."""
        return self.__etat_connexion

    @property
    def indicateur_regulation(self) -> QLabel:
        """QLabel: régulation en vigueur sur le serveur, d'après le dernier STATE."""
        return self.__indicateur_regulation

    @property
    def indicateur_vp(self) -> QLabel:
        """QLabel: présence d'un véhicule prioritaire en traversée, d'après le dernier STATE."""
        return self.__indicateur_vp

    @property
    def case_regulation(self) -> QCheckBox:
        """QCheckBox: interrupteur qui demande au serveur d'activer ou de couper la régulation."""
        return self.__case_regulation

    @property
    def onglets(self) -> QTabWidget:
        """QTabWidget: onglets de la fenêtre."""
        return self.__onglets

    @property
    def reseau(self) -> ReseauSupervision:
        """ReseauSupervision: travailleur réseau, qui vit dans le QThread de la fenêtre."""
        return self.__reseau

    @property
    def fil(self) -> QThread:
        """QThread: thread du réseau."""
        return self.__fil

    def demarrer(self) -> None:
        """Lance le thread réseau : connexion, abonnement aux STATE et heartbeat."""
        self.__fil.start()

    def arreter(self) -> None:
        """Arrête le scénario, les clients lancés ici et le réseau, puis attend la fin de leurs threads."""
        self.__panneau_scenario.arreter_tout()
        self.__reseau.arreter()
        if not self.__fil.wait(int(DELAI_ARRET * MILLISECONDES_PAR_SECONDE)):
            journal.warning("le thread réseau de la supervision ne s'est pas arrêté à temps")

    def closeEvent(self, evenement: QCloseEvent) -> None:
        """Arrête proprement tous les threads avant de fermer la fenêtre.

        Args:
            evenement (QCloseEvent): demande de fermeture reçue de Qt.
        """
        self.arreter()
        super().closeEvent(evenement)

    def __afficher_etat(self, etat: dict) -> None:
        """Affiche un STATE : la scène, puis les indicateurs du serveur."""
        self.__scene.afficher_etat(etat)
        regulation = etat["regulation"] is True
        self.__colorer(
            self.__indicateur_regulation,
            "active" if regulation else "inactive",
            COULEUR_INDICATEUR_ACTIF if regulation else COULEUR_INDICATEUR_INACTIF,
        )
        vp_actif = etat["vp_actif"] is True
        self.__colorer(
            self.__indicateur_vp,
            "en traversée" if vp_actif else "aucun",
            COULEURS_CATEGORIE[VehiculePrioritaire.CATEGORIE] if vp_actif else COULEUR_INDICATEUR_INACTIF,
        )
        if self.__case_a_aligner:
            # setChecked n'émet pas clicked : aligner la case n'envoie pas de REGLAGE.
            self.__case_regulation.setChecked(regulation)
            self.__case_a_aligner = False

    def __noter_connexion(self, etat: str, detail: str) -> None:
        """Affiche l'état de la connexion ; l'interrupteur n'est actif qu'une fois connecté."""
        etat_connexion = EtatConnexion(etat)
        connecte = etat_connexion is EtatConnexion.CONNECTE
        couleur = COULEUR_INDICATEUR_ACTIF if connecte else COULEUR_INDICATEUR_INACTIF
        self.__colorer(self.__etat_connexion, LIBELLES_CONNEXION[etat_connexion], couleur)
        self.__etat_connexion.setToolTip(detail)
        self.__case_regulation.setEnabled(connecte)
        if connecte:
            self.__case_a_aligner = True
        else:
            # Reconnecté, la supervision ne sait pas ce qui a changé entre-temps : pas d'événement inventé.
            self.__panneau_suivi.oublier_etat()
            self.__colorer(self.__indicateur_regulation, INCONNU, COULEUR_INDICATEUR_INACTIF)
            self.__colorer(self.__indicateur_vp, INCONNU, COULEUR_INDICATEUR_INACTIF)

    def __regler(self, coche: bool) -> None:
        """Transmet au réseau le réglage demandé par un clic sur l'interrupteur."""
        self.__reseau.demander_reglage(coche)

    def __actualiser_si_statistiques(self, rang: int) -> None:
        """Demande les statistiques au serveur quand l'onglet qui les montre devient visible."""
        if self.__onglets.widget(rang) is self.__panneau_stats:
            self.__reseau.demander_statistiques()

    @staticmethod
    def __colorer(etiquette: QLabel, texte: str, couleur: QColor) -> None:
        """Écrit un indicateur dans sa couleur."""
        etiquette.setText(texte)
        etiquette.setStyleSheet(f"color: {couleur.name()}; font-weight: bold;")

    def __relier(self) -> None:
        """Relie le réseau et l'interrupteur aux méthodes de la fenêtre, et les STATE à la section « Suivi »."""
        self.__fil.started.connect(self.__reseau.tourner)
        # quit() peut être appelée depuis n'importe quel thread. Reliée en direct, elle ne
        # dépend pas de la boucle de l'IHM, bloquée dans wait() pendant la fermeture.
        self.__reseau.termine.connect(self.__fil.quit, Qt.ConnectionType.DirectConnection)
        self.__reseau.etat_recu.connect(self.__afficher_etat)
        self.__reseau.etat_recu.connect(self.__panneau_suivi.noter_etat)
        self.__reseau.connexion_changee.connect(self.__noter_connexion)
        self.__case_regulation.clicked.connect(self.__regler)
        self.__reseau.statistiques_recues.connect(self.__panneau_stats.afficher)
        self.__panneau_stats.actualisation_demandee.connect(self.__reseau.demander_statistiques)
        # Ouvrir l'onglet des statistiques les actualise : elles ont pu changer depuis.
        self.__onglets.currentChanged.connect(self.__actualiser_si_statistiques)

    def __disposer(self) -> None:
        """Place la scène et sa légende à gauche, le panneau latéral à droite, dans l'onglet « Rond-point ».

        Rien n'a de taille fixe : la scène suit la place qu'on lui laisse, le séparateur se
        déplace, et le panneau latéral défile si la fenêtre manque de hauteur.
        """
        # Deux indicateurs par rangée : le panneau garde sa hauteur pour les sections.
        serveur = QGroupBox("Serveur")
        grille = QGridLayout(serveur)
        grille.addWidget(QLabel("Connexion"), 0, 0)
        grille.addWidget(self.__etat_connexion, 0, 1)
        grille.addWidget(QLabel("Régulation"), 0, 2)
        grille.addWidget(self.__indicateur_regulation, 0, 3)
        grille.addWidget(QLabel("Véhicule prioritaire"), 1, 0)
        grille.addWidget(self.__indicateur_vp, 1, 1)
        grille.addWidget(self.__case_regulation, 1, 2, 1, 2)
        grille.setColumnStretch(1, 1)
        grille.setColumnStretch(3, 1)
        self.__sections.addTab(self.__panneau_scenario, "Scénario")
        self.__sections.addTab(self.__panneau_suivi, "Suivi")
        contenu_lateral = QWidget()
        colonne_droite = QVBoxLayout(contenu_lateral)
        # Les marges des onglets suffisent : celles du panneau prendraient la hauteur qui manque sur un portable.
        colonne_droite.setContentsMargins(0, 0, 0, 0)
        colonne_droite.addWidget(serveur)
        colonne_droite.addWidget(self.__sections, 1)
        self.__panneau_lateral.setWidget(contenu_lateral)
        self.__panneau_lateral.setWidgetResizable(True)
        self.__panneau_lateral.setFrameShape(QScrollArea.Shape.NoFrame)
        self.__panneau_lateral.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Le panneau ne défile qu'en hauteur : il garde la largeur de son contenu, plus la barre de défilement.
        self.__panneau_lateral.setMinimumWidth(
            contenu_lateral.minimumSizeHint().width() + self.__panneau_lateral.verticalScrollBar().sizeHint().width()
        )
        colonne_gauche = QWidget()
        disposition_gauche = QVBoxLayout(colonne_gauche)
        disposition_gauche.addWidget(self.__vue, 1)
        disposition_gauche.addWidget(self.__legende)
        self.__separateur.addWidget(colonne_gauche)
        self.__separateur.addWidget(self.__panneau_lateral)
        self.__separateur.setChildrenCollapsible(False)
        self.__onglets.addTab(self.__separateur, "Rond-point")
        self.__onglets.addTab(self.__panneau_stats, "Statistiques")
        self.setCentralWidget(self.__onglets)
        self.setWindowTitle(TITRE)
        self.setMinimumSize(LARGEUR_MINIMALE, HAUTEUR_MINIMALE)
        self.__dimensionner()

    def __dimensionner(self) -> None:
        """Donne à la fenêtre une part de l'écran, puis partage sa largeur entre la scène et le panneau."""
        ecran = QGuiApplication.primaryScreen()
        if ecran is not None:
            self.resize(ecran.availableGeometry().size() * PART_ECRAN)
        largeur_scene = round(self.width() * PARTS_SCENE / (PARTS_SCENE + PARTS_PANNEAU))
        self.__separateur.setSizes([largeur_scene, self.width() - largeur_scene])
        self.__separateur.setStretchFactor(0, PARTS_SCENE)
        self.__separateur.setStretchFactor(1, PARTS_PANNEAU)
