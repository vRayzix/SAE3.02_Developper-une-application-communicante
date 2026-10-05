"""Relais entre un client usager, qui tourne dans son propre thread, et l'IHM."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from cherrypie.client.client_usager import EtatConnexion
from cherrypie.commun.protocole import CodeNotification


class RelaisClient(QObject):
    """Transforme les rappels d'un ClientUsager en signaux Qt.

    Le client appelle ses rappels depuis son thread. Le relais, créé dans le thread de
    l'IHM, se contente d'émettre un signal : Qt le remet alors aux widgets dans leur
    thread, sans qu'aucun thread de travail ne les touche. Chaque signal porte
    l'identifiant de l'usager, pour que l'IHM sache de quel client il vient.

    Signals:
        position_changee (str, dict): identifiant et état de l'usager après un pas (format de Usager.vers_dict()).
        notification_recue (str, str, str, bool): identifiant, code de la consigne, texte, True si elle est appliquée.
        connexion_changee (str, str, str): identifiant, état de la connexion (valeur de EtatConnexion) et détail.
    """

    position_changee = pyqtSignal(str, dict)
    notification_recue = pyqtSignal(str, str, str, bool)
    connexion_changee = pyqtSignal(str, str, str)

    def __init__(self, identifiant: str) -> None:
        """Crée le relais d'un client.

        Args:
            identifiant (str): identifiant de l'usager du client.
        """
        super().__init__()
        self.__identifiant = identifiant

    @property
    def identifiant(self) -> str:
        """str: identifiant de l'usager du client relayé."""
        return self.__identifiant

    def sur_position(self, usager: dict) -> None:
        """Rappel de position du client : émet position_changee.

        Args:
            usager (dict): état de l'usager après un pas.
        """
        self.position_changee.emit(self.__identifiant, usager)

    def sur_notification(self, code: CodeNotification, texte: str, appliquee: bool) -> None:
        """Rappel de consigne du client : émet notification_recue.

        Args:
            code (CodeNotification): consigne reçue.
            texte (str): texte qui l'accompagne.
            appliquee (bool): True si l'usager l'applique.
        """
        self.notification_recue.emit(self.__identifiant, code.value, texte, appliquee)

    def sur_connexion(self, etat: EtatConnexion, detail: str) -> None:
        """Rappel d'état de connexion du client : émet connexion_changee.

        Args:
            etat (EtatConnexion): nouvel état de la connexion.
            detail (str): explication lisible.
        """
        self.connexion_changee.emit(self.__identifiant, etat.value, detail)
