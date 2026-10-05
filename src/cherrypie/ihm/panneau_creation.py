"""Panneau de création : lance des clients usagers locaux, qui se connectent au serveur comme les autres."""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cherrypie.client.client_usager import ClientUsager, EtatConnexion
from cherrypie.commun.config import Configuration
from cherrypie.ihm.relais_client import RelaisClient
from cherrypie.ihm.style import LIBELLES_CONNEXION, NOMS_CATEGORIE
from cherrypie.modele.usager import CLASSES_PAR_CATEGORIE, Pieton

NOMBRE_MAX_PAR_CLIC = 10
COLONNES_CLIENTS = ["Usager", "Trajet", "Connexion", "Consigne"]
COLONNE_CONNEXION = 2
COLONNE_CONSIGNE = 3
SANS_CONSIGNE = "aucune"

journal = logging.getLogger(__name__)


class PanneauCreation(QGroupBox):
    """Choix d'un type d'usager, d'une entrée et d'une sortie ; chaque clic lance des clients.

    Chaque client tourne dans son thread et signale ce qui lui arrive par un RelaisClient,
    qui le remet au panneau sous forme de signaux Qt. Le panneau liste les clients en
    route et retire chacun d'eux quand il a terminé. Un piéton traverse une seule branche :
    pour lui, la sortie suit l'entrée.

    Signals:
        notification_recue (str, str, str, bool): consigne reçue par un client lancé
            (identifiant, code, texte, True si elle est appliquée).
    """

    notification_recue = pyqtSignal(str, str, str, bool)

    def __init__(self, config: Configuration, parent: QWidget | None = None) -> None:
        """Construit le panneau.

        Args:
            config (Configuration): configuration donnée aux clients lancés (serveur, branches).
            parent (QWidget | None): widget parent.
        """
        super().__init__("Créer des usagers", parent)
        self.__config = config
        self.__clients: list[ClientUsager] = []
        self.__lignes: dict[str, QTreeWidgetItem] = {}
        self.__compteurs = {categorie: 0 for categorie in CLASSES_PAR_CATEGORIE}
        self.__choix_categorie = QComboBox()
        for categorie in CLASSES_PAR_CATEGORIE:
            self.__choix_categorie.addItem(NOMS_CATEGORIE[categorie], categorie)
        self.__choix_entree = QComboBox()
        self.__choix_entree.addItems(config.branches)
        self.__choix_sortie = QComboBox()
        self.__choix_sortie.addItems(config.branches)
        self.__choix_nombre = QSpinBox()
        self.__choix_nombre.setRange(1, NOMBRE_MAX_PAR_CLIC)
        self.__bouton_lancer = QPushButton("Lancer")
        self.__liste_clients = QTreeWidget()
        self.__liste_clients.setHeaderLabels(COLONNES_CLIENTS)
        self.__liste_clients.setRootIsDecorated(False)
        self.__disposer()
        self.__choix_categorie.currentIndexChanged.connect(self.__adapter_sortie)
        self.__choix_entree.currentIndexChanged.connect(self.__adapter_sortie)
        self.__bouton_lancer.clicked.connect(self.lancer)

    @property
    def config(self) -> Configuration:
        """Configuration: configuration donnée aux clients lancés."""
        return self.__config

    @property
    def clients(self) -> list[ClientUsager]:
        """list[ClientUsager]: clients lancés dont le thread n'a pas encore été oublié (copie)."""
        return list(self.__clients)

    @property
    def choix_categorie(self) -> QComboBox:
        """QComboBox: type d'usager à créer ; la donnée de chaque entrée est la catégorie."""
        return self.__choix_categorie

    @property
    def choix_entree(self) -> QComboBox:
        """QComboBox: branche d'entrée."""
        return self.__choix_entree

    @property
    def choix_sortie(self) -> QComboBox:
        """QComboBox: branche de sortie, imposée égale à l'entrée pour un piéton."""
        return self.__choix_sortie

    @property
    def choix_nombre(self) -> QSpinBox:
        """QSpinBox: nombre d'usagers lancés à chaque clic."""
        return self.__choix_nombre

    @property
    def bouton_lancer(self) -> QPushButton:
        """QPushButton: lance les usagers choisis."""
        return self.__bouton_lancer

    @property
    def liste_clients(self) -> QTreeWidget:
        """QTreeWidget: une ligne par client en route."""
        return self.__liste_clients

    def lancer(self) -> list[ClientUsager]:
        """Crée les usagers choisis et lance un client pour chacun.

        Returns:
            list[ClientUsager]: les clients lancés, déjà démarrés.
        """
        # Les clients arrivés au bout ont fini leur thread : inutile de les garder.
        self.__clients = [client for client in self.__clients if client.is_alive()]
        categorie = self.__choix_categorie.currentData()
        entree = self.__choix_entree.currentText()
        sortie = self.__choix_sortie.currentText()
        lances = [self.__lancer_un(categorie, entree, sortie) for _ in range(self.__choix_nombre.value())]
        journal.info("%d %s lancé(s) de %s vers %s", len(lances), categorie, entree, sortie)
        return lances

    def arreter_clients(self, delai: float) -> None:
        """Arrête tous les clients lancés et attend la fin de leurs threads.

        Args:
            delai (float): attente maximale pour chaque thread, en secondes.
        """
        for client in self.__clients:
            client.arreter()
        for client in self.__clients:
            client.join(timeout=delai)
            if client.is_alive():
                journal.warning("le client %s ne s'est pas arrêté à temps", client.usager.identifiant)

    def __lancer_un(self, categorie: str, entree: str, sortie: str) -> ClientUsager:
        """Crée un usager, son relais et son client, puis démarre le client."""
        self.__compteurs[categorie] += 1
        identifiant = f"{categorie}_{self.__compteurs[categorie]}"
        usager = CLASSES_PAR_CATEGORIE[categorie](identifiant, entree, sortie)
        relais = RelaisClient(identifiant)
        relais.position_changee.connect(self.__noter_position)
        relais.connexion_changee.connect(self.__noter_connexion)
        relais.notification_recue.connect(self.notification_recue)
        # Le client garde ses rappels, donc le relais : il vit aussi longtemps que lui.
        client = ClientUsager(
            self.__config,
            usager,
            sur_position=relais.sur_position,
            sur_notification=relais.sur_notification,
            sur_connexion=relais.sur_connexion,
        )
        ligne = QTreeWidgetItem([identifiant, f"{entree} vers {sortie}", "", SANS_CONSIGNE])
        self.__liste_clients.addTopLevelItem(ligne)
        self.__lignes[identifiant] = ligne
        self.__clients.append(client)
        client.start()
        return client

    def __noter_position(self, identifiant: str, usager: dict) -> None:
        """Affiche la consigne que suit un client, d'après son dernier pas."""
        ligne = self.__lignes.get(identifiant)
        if ligne is not None:
            ligne.setText(COLONNE_CONSIGNE, usager["consigne"] or SANS_CONSIGNE)

    def __noter_connexion(self, identifiant: str, etat: str, detail: str) -> None:
        """Affiche l'état de connexion d'un client ; retire sa ligne quand il a terminé."""
        ligne = self.__lignes.get(identifiant)
        if ligne is None:
            return
        etat_connexion = EtatConnexion(etat)
        if etat_connexion is EtatConnexion.TERMINE:
            self.__liste_clients.takeTopLevelItem(self.__liste_clients.indexOfTopLevelItem(ligne))
            del self.__lignes[identifiant]
            return
        ligne.setText(COLONNE_CONNEXION, LIBELLES_CONNEXION[etat_connexion])
        ligne.setToolTip(COLONNE_CONNEXION, detail)

    def __adapter_sortie(self) -> None:
        """Un piéton traverse la branche par laquelle il arrive : sa sortie suit l'entrée."""
        pieton = self.__choix_categorie.currentData() == Pieton.CATEGORIE
        if pieton:
            self.__choix_sortie.setCurrentIndex(self.__choix_entree.currentIndex())
        self.__choix_sortie.setEnabled(not pieton)

    def __disposer(self) -> None:
        """Place les choix, le bouton et la liste des clients."""
        formulaire = QFormLayout()
        formulaire.addRow("Type", self.__choix_categorie)
        formulaire.addRow("Entrée", self.__choix_entree)
        formulaire.addRow("Sortie", self.__choix_sortie)
        formulaire.addRow("Nombre", self.__choix_nombre)
        disposition = QVBoxLayout(self)
        disposition.addLayout(formulaire)
        disposition.addWidget(self.__bouton_lancer)
        disposition.addWidget(self.__liste_clients)
