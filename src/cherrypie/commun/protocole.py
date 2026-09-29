"""Format des messages échangés entre le serveur, les clients et la supervision.

La description complète du protocole se trouve dans docs/protocole.md.
"""

from enum import Enum


class TypeMessage(Enum):
    """Types de messages du protocole.

    La valeur de chaque membre est la chaîne transmise dans le champ « type ».
    """

    HELLO = "HELLO"
    HELLO_ACK = "HELLO_ACK"
    POS = "POS"
    VP_ALERT = "VP_ALERT"
    VP_FIN = "VP_FIN"
    NOTIF = "NOTIF"
    STATE = "STATE"
    ABONNEMENT = "ABONNEMENT"
    REGLAGE = "REGLAGE"
    PING = "PING"
    PONG = "PONG"
    BYE = "BYE"


class CodeNotification(Enum):
    """Consignes que le serveur envoie à un usager dans un message NOTIF.

    Rangées ici plutôt que dans le serveur, parce que le client en a besoin
    pour réagir aux consignes reçues.
    """

    DEGAGEZ = "DEGAGEZ"
    CHANGEZ_VOIE = "CHANGEZ_VOIE"
    ATTENDEZ = "ATTENDEZ"
    OK_PASSER = "OK_PASSER"
