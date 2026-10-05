"""Fenêtre de supervision : le rond-point en 2D, l'état du serveur, la création d'usagers et les consignes."""

from __future__ import annotations

import logging
from datetime import datetime

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QCloseEvent, QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from cherrypie.client.client_usager import EtatConnexion
from cherrypie.commun.config import Configuration
from cherrypie.ihm.legende import Legende
from cherrypie.ihm.panneau_creation import PanneauCreation
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
LARGEUR_INITIALE = 1280
HAUTEUR_INITIALE = 820
LARGEUR_PANNEAU = 380
COLONNES_LEGENDE = 7
NOMBRE_MAX_CONSIGNES = 50
# Attente maximale de l'arrêt de chaque thread (clients, réseau) à la fermeture, en secondes.
DELAI_ARRET = 2.0
MILLISECONDES_PAR_SECONDE = 1000
INCONNU = "inconnue"

journal = logging.getLogger(__name__)


class FenetreSupervision(QMainWindow):
    """Fenêtre principale de la supervision.

    L'onglet « Rond-point » montre la scène 2D et sa légende, l'état du serveur avec
    l'interrupteur de régulation, le panneau de création d'usagers et les dernières
    consignes reçues par les usagers lancés ici. Le réseau tourne dans un QThread ; tout ce
    qu'il reçoit arrive ici par signaux Qt, dans le thread de l'IHM. La fenêtre n'interprète
    rien : elle affiche l'état diffusé par le serveur.
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
        self.__panneau_creation = PanneauCreation(config)
        self.__etat_connexion = QLabel(LIBELLES_CONNEXION[EtatConnexion.DECONNECTE])
        self.__indicateur_regulation = QLabel(INCONNU)
        self.__indicateur_vp = QLabel(INCONNU)
        self.__case_regulation = QCheckBox("Régulation active")
        self.__case_regulation.setEnabled(False)
        self.__consignes = QListWidget()
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
    def panneau_creation(self) -> PanneauCreation:
        """PanneauCreation: panneau qui lance des usagers locaux."""
        return self.__panneau_creation

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
    def consignes(self) -> QListWidget:
        """QListWidget: dernières consignes reçues par les usagers lancés ici, la plus récente en haut."""
        return self.__consignes

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
        """Arrête les clients lancés ici et le réseau, puis attend la fin de leurs threads."""
        self.__panneau_creation.arreter_clients(DELAI_ARRET)
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
            self.__colorer(self.__indicateur_regulation, INCONNU, COULEUR_INDICATEUR_INACTIF)
            self.__colorer(self.__indicateur_vp, INCONNU, COULEUR_INDICATEUR_INACTIF)

    def __regler(self, coche: bool) -> None:
        """Transmet au réseau le réglage demandé par un clic sur l'interrupteur."""
        self.__reseau.demander_reglage(coche)

    def __noter_consigne(self, identifiant: str, code: str, texte: str, appliquee: bool) -> None:
        """Ajoute une consigne en haut de la liste, et oublie les plus anciennes."""
        heure = datetime.now().time().isoformat(timespec="seconds")
        ligne = QListWidgetItem(f"{heure}  {identifiant} : {code}" + ("" if appliquee else " (ignorée)"))
        ligne.setToolTip(texte)
        self.__consignes.insertItem(0, ligne)
        while self.__consignes.count() > NOMBRE_MAX_CONSIGNES:
            self.__consignes.takeItem(self.__consignes.count() - 1)

    @staticmethod
    def __colorer(etiquette: QLabel, texte: str, couleur: QColor) -> None:
        """Écrit un indicateur dans sa couleur."""
        etiquette.setText(texte)
        etiquette.setStyleSheet(f"color: {couleur.name()}; font-weight: bold;")

    def __relier(self) -> None:
        """Relie le réseau, le panneau de création et l'interrupteur aux méthodes de la fenêtre."""
        self.__fil.started.connect(self.__reseau.tourner)
        # quit() peut être appelée depuis n'importe quel thread. Reliée en direct, elle ne
        # dépend pas de la boucle de l'IHM, bloquée dans wait() pendant la fermeture.
        self.__reseau.termine.connect(self.__fil.quit, Qt.ConnectionType.DirectConnection)
        self.__reseau.etat_recu.connect(self.__afficher_etat)
        self.__reseau.connexion_changee.connect(self.__noter_connexion)
        self.__panneau_creation.notification_recue.connect(self.__noter_consigne)
        self.__case_regulation.clicked.connect(self.__regler)

    def __disposer(self) -> None:
        """Place la scène et sa légende à gauche, les panneaux à droite, dans l'onglet « Rond-point »."""
        serveur = QGroupBox("Serveur")
        formulaire = QFormLayout(serveur)
        formulaire.addRow("Connexion", self.__etat_connexion)
        formulaire.addRow("Régulation", self.__indicateur_regulation)
        formulaire.addRow("Véhicule prioritaire", self.__indicateur_vp)
        formulaire.addRow(self.__case_regulation)
        groupe_consignes = QGroupBox("Dernières consignes")
        QVBoxLayout(groupe_consignes).addWidget(self.__consignes)
        panneaux = QWidget()
        panneaux.setFixedWidth(LARGEUR_PANNEAU)
        colonne_droite = QVBoxLayout(panneaux)
        colonne_droite.setContentsMargins(0, 0, 0, 0)
        colonne_droite.addWidget(serveur)
        colonne_droite.addWidget(self.__panneau_creation, 1)
        colonne_droite.addWidget(groupe_consignes, 1)
        colonne_gauche = QVBoxLayout()
        colonne_gauche.addWidget(self.__vue, 1)
        colonne_gauche.addWidget(self.__legende)
        page = QWidget()
        disposition = QHBoxLayout(page)
        disposition.addLayout(colonne_gauche, 1)
        disposition.addWidget(panneaux)
        self.__onglets.addTab(page, "Rond-point")
        self.setCentralWidget(self.__onglets)
        self.setWindowTitle(TITRE)
        self.resize(LARGEUR_INITIALE, HAUTEUR_INITIALE)
