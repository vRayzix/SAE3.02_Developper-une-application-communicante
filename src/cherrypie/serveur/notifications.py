"""Notifications envoyées aux usagers : la consigne, son destinataire et un texte lisible."""

from __future__ import annotations

from dataclasses import dataclass

from cherrypie.commun.protocole import CodeNotification, Message, TypeMessage

TEXTE_DEGAGEZ = "Véhicule prioritaire derrière vous : ralentissez et serrez à droite."
TEXTE_CHANGEZ_VOIE = "Véhicule prioritaire derrière vous : serrez à droite pour le laisser passer."
TEXTE_ATTENDEZ_VP = "Véhicule prioritaire en approche : attendez avant d'entrer."
TEXTE_ATTENDEZ_PIETON = "Véhicule prioritaire en approche : attendez pour traverser."
TEXTE_ATTENDEZ_DOSAGE = "Entrée temporisée pour fluidifier le rond-point."
TEXTE_OK_PASSER = "Vous pouvez reprendre votre route."


@dataclass(frozen=True)
class Notification:
    """Consigne destinée à un usager.

    Attributes:
        destinataire (str): identifiant de l'usager.
        code (CodeNotification): consigne à appliquer.
        texte (str): explication lisible, affichée à l'usager.
    """

    destinataire: str
    code: CodeNotification
    texte: str

    def vers_message(self, emetteur: str) -> Message:
        """Construit le message NOTIF à envoyer à l'usager.

        Args:
            emetteur (str): identifiant de l'émetteur, le serveur.

        Returns:
            Message: NOTIF avec le code et le texte de la consigne.
        """
        return Message(TypeMessage.NOTIF, emetteur, {"code": self.code.value, "message": self.texte})
