"""Section « Suivi » : les clients en route et les dernières consignes qu'ils ont reçues."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtWidgets import (
    QGroupBox,
    QHeaderView,
    QListWidget,
    QListWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cherrypie.client.client_usager import EtatConnexion
from cherrypie.ihm.lanceur_clients import LanceurClients
from cherrypie.ihm.style import LIBELLES_CONNEXION

COLONNES_CLIENTS = ["Usager", "Trajet", "Connexion", "Consigne"]
COLONNE_TRAJET = 1
COLONNE_CONNEXION = 2
COLONNE_CONSIGNE = 3
SANS_CONSIGNE = "aucune"
NOMBRE_MAX_CONSIGNES = 50


class PanneauSuivi(QWidget):
    """Liste des clients lancés depuis la supervision, et dernières consignes reçues.

    Le panneau ne lance rien : il affiche ce que signale le lanceur de clients. Un client
    disparaît de la liste quand il a terminé ; les consignes les plus anciennes sont oubliées.
    """

    def __init__(self, lanceur: LanceurClients, parent: QWidget | None = None) -> None:
        """Construit le panneau et le relie au lanceur.

        Args:
            lanceur (LanceurClients): lanceur dont on suit les clients.
            parent (QWidget | None): widget parent.
        """
        super().__init__(parent)
        self.__lignes: dict[str, QTreeWidgetItem] = {}
        self.__liste_clients = QTreeWidget()
        self.__liste_clients.setHeaderLabels(COLONNES_CLIENTS)
        self.__liste_clients.setRootIsDecorated(False)
        entete = self.__liste_clients.header()
        entete.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # Les noms de rues sont longs : la colonne du trajet prend la place qui reste, quitte à les abréger.
        entete.setSectionResizeMode(COLONNE_TRAJET, QHeaderView.ResizeMode.Stretch)
        entete.setStretchLastSection(False)
        self.__consignes = QListWidget()
        self.__disposer()
        lanceur.client_lance.connect(self.__ajouter_client)
        lanceur.position_changee.connect(self.__noter_position)
        lanceur.connexion_changee.connect(self.__noter_connexion)
        lanceur.notification_recue.connect(self.__noter_consigne)

    @property
    def liste_clients(self) -> QTreeWidget:
        """QTreeWidget: une ligne par client en route."""
        return self.__liste_clients

    @property
    def consignes(self) -> QListWidget:
        """QListWidget: dernières consignes reçues par les clients lancés, la plus récente en haut."""
        return self.__consignes

    def __ajouter_client(self, identifiant: str, trajet: str) -> None:
        """Ajoute la ligne d'un client qui vient d'être lancé."""
        ligne = QTreeWidgetItem([identifiant, trajet, "", SANS_CONSIGNE])
        ligne.setToolTip(COLONNE_TRAJET, trajet)
        self.__liste_clients.addTopLevelItem(ligne)
        self.__lignes[identifiant] = ligne

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

    def __noter_consigne(self, identifiant: str, code: str, texte: str, appliquee: bool) -> None:
        """Ajoute une consigne en haut de la liste, et oublie les plus anciennes."""
        heure = datetime.now().time().isoformat(timespec="seconds")
        ligne = QListWidgetItem(f"{heure}  {identifiant} : {code}" + ("" if appliquee else " (ignorée)"))
        ligne.setToolTip(texte)
        self.__consignes.insertItem(0, ligne)
        while self.__consignes.count() > NOMBRE_MAX_CONSIGNES:
            self.__consignes.takeItem(self.__consignes.count() - 1)

    def __disposer(self) -> None:
        """Empile les clients en route et les dernières consignes."""
        groupe_clients = QGroupBox("Clients en route")
        QVBoxLayout(groupe_clients).addWidget(self.__liste_clients)
        groupe_consignes = QGroupBox("Dernières consignes")
        QVBoxLayout(groupe_consignes).addWidget(self.__consignes)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.addWidget(groupe_clients, 1)
        disposition.addWidget(groupe_consignes, 1)
