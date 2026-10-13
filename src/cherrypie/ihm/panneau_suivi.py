"""Section « Suivi » : les clients en route, puis les consignes qu'ils reçoivent et les événements du serveur."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtGui import QBrush, QColor
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
from cherrypie.ihm.evenements import EvenementsServeur
from cherrypie.ihm.lanceur_clients import LanceurClients
from cherrypie.ihm.style import COULEUR_EVENEMENT, COULEURS_MESSAGE, LIBELLES_CONNEXION, OPACITE_FOND_MESSAGE

COLONNES_CLIENTS = ["Usager", "Trajet", "Connexion", "Consigne"]
COLONNE_TRAJET = 1
COLONNE_CONNEXION = 2
COLONNE_CONSIGNE = 3
SANS_CONSIGNE = "aucune"
# La liste des messages garde les plus récents ; un message regroupé nomme au plus ce
# nombre de destinataires, les autres sont comptés et listés dans l'info-bulle.
NOMBRE_MAX_MESSAGES = 100
DESTINATAIRES_AFFICHES = 3
EMETTEUR_SERVEUR = "Serveur"


class PanneauSuivi(QWidget):
    """Clients lancés depuis la supervision, puis liste des messages.

    Le panneau ne lance rien : il affiche ce que signale le lanceur de clients, et les
    événements que la fenêtre lui transmet à chaque STATE. Un client disparaît de la liste
    quand il a terminé. Chaque message tient sur une ligne, la plus récente en haut, colorée
    selon sa consigne : « 15:31:14  voiture_3 ← DEGAGEZ : texte ». Un message identique au
    précédent ne crée pas de ligne : il s'ajoute à ses destinataires, ou à son compte.
    """

    def __init__(self, lanceur: LanceurClients, parent: QWidget | None = None) -> None:
        """Construit le panneau et le relie au lanceur.

        Args:
            lanceur (LanceurClients): lanceur dont on suit les clients.
            parent (QWidget | None): widget parent.
        """
        super().__init__(parent)
        self.__lignes: dict[str, QTreeWidgetItem] = {}
        self.__evenements = EvenementsServeur({branche.nom: branche.libelle for branche in lanceur.config.branches})
        # Message de la ligne du haut et ses destinataires, avec leur nombre de réceptions.
        self.__dernier_message: tuple | None = None
        self.__destinataires: dict[str, int] = {}
        self.__liste_clients = QTreeWidget()
        self.__liste_clients.setHeaderLabels(COLONNES_CLIENTS)
        self.__liste_clients.setRootIsDecorated(False)
        entete = self.__liste_clients.header()
        entete.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        # Les noms de rues sont longs : la colonne du trajet prend la place qui reste, quitte à les abréger.
        entete.setSectionResizeMode(COLONNE_TRAJET, QHeaderView.ResizeMode.Stretch)
        entete.setStretchLastSection(False)
        self.__messages = QListWidget()
        self.__messages.setWordWrap(True)
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
    def messages(self) -> QListWidget:
        """QListWidget: consignes reçues par les clients lancés et événements du serveur, le plus récent en haut."""
        return self.__messages

    def noter_etat(self, etat: dict) -> None:
        """Ajoute à la liste les événements que révèle un STATE.

        Args:
            etat (dict): données d'un STATE reçu par la supervision.
        """
        for evenement in self.__evenements.comparer(etat, datetime.now()):
            self.__ajouter_message(("evenement", evenement), EMETTEUR_SERVEUR, f" : {evenement}", COULEUR_EVENEMENT)

    def oublier_etat(self) -> None:
        """Oublie le dernier STATE, après une déconnexion : le suivant ne produira pas d'événement."""
        self.__evenements.oublier()

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
        """Ajoute la consigne reçue par un client, ou la regroupe avec la précédente si elle est identique."""
        suite = f" ← {code} : {texte}" + ("" if appliquee else " (ignorée)")
        self.__ajouter_message(("consigne", code, texte, appliquee), identifiant, suite, COULEURS_MESSAGE[code])

    def __ajouter_message(self, cle: tuple, destinataire: str, suite: str, couleur: QColor) -> None:
        """Ajoute un message en haut de la liste, ou complète la ligne du haut si c'est le même message.

        La ligne s'écrit : heure, destinataires, puis la suite du message.
        """
        if cle != self.__dernier_message or self.__messages.count() == 0:
            self.__dernier_message = cle
            self.__destinataires = {}
            ligne = QListWidgetItem()
            fond = QColor(couleur)
            fond.setAlpha(OPACITE_FOND_MESSAGE)
            ligne.setBackground(QBrush(fond))
            self.__messages.insertItem(0, ligne)
            while self.__messages.count() > NOMBRE_MAX_MESSAGES:
                self.__messages.takeItem(self.__messages.count() - 1)
        self.__destinataires[destinataire] = self.__destinataires.get(destinataire, 0) + 1
        heure = datetime.now().time().isoformat(timespec="seconds")
        ligne = self.__messages.item(0)
        ligne.setText(f"{heure}  {self.__nommer(self.__destinataires)}{suite}")
        ligne.setToolTip(", ".join(self.__destinataires))

    @staticmethod
    def __nommer(destinataires: dict[str, int]) -> str:
        """Nomme les destinataires d'un message regroupé, avec le nombre de réceptions de chacun."""
        noms = [nom if fois == 1 else f"{nom} (×{fois})" for nom, fois in destinataires.items()]
        if len(noms) <= DESTINATAIRES_AFFICHES:
            return ", ".join(noms)
        return ", ".join(noms[:DESTINATAIRES_AFFICHES]) + f" et {len(noms) - DESTINATAIRES_AFFICHES} autres"

    def __disposer(self) -> None:
        """Empile les clients en route et les messages."""
        groupe_clients = QGroupBox("Clients en route")
        QVBoxLayout(groupe_clients).addWidget(self.__liste_clients)
        groupe_messages = QGroupBox("Consignes et événements")
        QVBoxLayout(groupe_messages).addWidget(self.__messages)
        disposition = QVBoxLayout(self)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.addWidget(groupe_clients, 1)
        disposition.addWidget(groupe_messages, 1)
