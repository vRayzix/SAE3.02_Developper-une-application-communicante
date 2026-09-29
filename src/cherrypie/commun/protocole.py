"""Format des messages échangés entre le serveur, les clients et la supervision.

La description complète du protocole se trouve dans docs/protocole.md.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum

from cherrypie.commun.erreurs import TrameInvalideError

CHAMPS_MESSAGE = {"type", "id", "donnees"}
CHAMPS_ENVELOPPE = {"ts", "nonce", "hmac"}


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


class Message:
    """Message applicatif : son type, l'identifiant de son émetteur et ses données.

    C'est ce que manipulent le serveur et les clients. Sur le réseau, il voyage
    dans une enveloppe qui ajoute l'horodatage, le nonce et le HMAC.
    """

    def __init__(self, type_message: TypeMessage, emetteur: str, donnees: dict | None = None) -> None:
        """Crée un message.

        Args:
            type_message (TypeMessage): type du message.
            emetteur (str): identifiant de l'émetteur (ex. "voiture_12" ou "serveur").
            donnees (dict | None): contenu propre au type de message, vide par défaut.

        Raises:
            TypeError: si le type n'est pas un TypeMessage ou si les données ne sont pas un dictionnaire.
            ValueError: si l'émetteur n'est pas un identifiant non vide.
        """
        if not isinstance(type_message, TypeMessage):
            raise TypeError(f"type de message invalide : {type_message!r}")
        if not isinstance(emetteur, str) or not emetteur:
            raise ValueError(f"l'émetteur doit être un identifiant non vide (reçu : {emetteur!r})")
        if donnees is None:
            donnees = {}
        if not isinstance(donnees, dict):
            raise TypeError("les données d'un message doivent former un dictionnaire")
        self.__type = type_message
        self.__emetteur = emetteur
        # Copie : le message ne doit pas changer si l'appelant modifie son dictionnaire ensuite.
        self.__donnees = dict(donnees)

    @classmethod
    def depuis_dict(cls, contenu: dict) -> Message:
        """Reconstruit un message à partir d'un dictionnaire reçu du réseau.

        Args:
            contenu (dict): dictionnaire issu de json.loads, avec les champs « type », « id » et « donnees ».

        Returns:
            Message: le message reconstruit.

        Raises:
            TrameInvalideError: si un champ manque ou contient une valeur invalide.
        """
        if not isinstance(contenu, dict):
            raise TrameInvalideError("un message doit être un objet JSON")
        manquants = CHAMPS_MESSAGE - contenu.keys()
        if manquants:
            raise TrameInvalideError(f"champs manquants dans le message : {', '.join(sorted(manquants))}")
        try:
            type_message = TypeMessage(contenu["type"])
        except ValueError as erreur:
            raise TrameInvalideError(f"type de message inconnu : {contenu['type']!r}") from erreur
        try:
            return cls(type_message, contenu["id"], contenu["donnees"])
        except (TypeError, ValueError) as erreur:
            raise TrameInvalideError(f"message invalide : {erreur}") from erreur

    @property
    def type(self) -> TypeMessage:
        """TypeMessage: type du message."""
        return self.__type

    @property
    def emetteur(self) -> str:
        """str: identifiant de l'émetteur."""
        return self.__emetteur

    @property
    def donnees(self) -> dict:
        """dict: contenu propre au type de message (copie)."""
        return dict(self.__donnees)

    def vers_dict(self) -> dict:
        """Convertit le message en dictionnaire prêt pour json.dumps.

        Returns:
            dict: champs « type », « id » et « donnees ».
        """
        return {"type": self.__type.value, "id": self.__emetteur, "donnees": dict(self.__donnees)}

    def __eq__(self, autre: object) -> bool:
        """Deux messages sont égaux s'ils ont le même type, le même émetteur et les mêmes données."""
        if not isinstance(autre, Message):
            return NotImplemented
        return self.vers_dict() == autre.vers_dict()

    def __repr__(self) -> str:
        """Représentation lisible dans les journaux."""
        return f"Message({self.__type.name}, {self.__emetteur!r}, {self.__donnees!r})"


@dataclass(frozen=True)
class Enveloppe:
    """Forme d'un message sur le réseau : le message, plus de quoi l'authentifier.

    Les champs sont mis à plat dans un seul objet JSON :
    {"type", "id", "ts", "nonce", "donnees", "hmac"}.

    Attributes:
        message (Message): message transporté.
        ts (float): horodatage d'émission, en secondes depuis l'epoch.
        nonce (str): valeur aléatoire propre à cette enveloppe, pour repérer les rejeux.
        hmac (str): signature HMAC-SHA256 en hexadécimal, vide tant que l'enveloppe n'est pas signée.
    """

    message: Message
    ts: float
    nonce: str
    hmac: str = ""

    def __post_init__(self) -> None:
        """Vérifie les champs dès la construction.

        Raises:
            TypeError: si un champ n'a pas le bon type.
            ValueError: si l'horodatage n'est pas fini ou si le nonce est vide.
        """
        if not isinstance(self.message, Message):
            raise TypeError("une enveloppe transporte un Message")
        # bool est une sous-classe de int : sans ce test, true passerait pour un horodatage.
        if isinstance(self.ts, bool) or not isinstance(self.ts, (int, float)):
            raise TypeError(f"l'horodatage doit être un nombre (reçu : {self.ts!r})")
        # json.loads accepte NaN et Infinity, qui fausseraient le contrôle anti-rejeu.
        if not math.isfinite(self.ts):
            raise ValueError(f"l'horodatage doit être un nombre fini (reçu : {self.ts!r})")
        if not isinstance(self.nonce, str) or not self.nonce:
            raise ValueError("le nonce doit être une chaîne non vide")
        if not isinstance(self.hmac, str):
            raise TypeError("le HMAC doit être une chaîne hexadécimale")

    @classmethod
    def depuis_dict(cls, contenu: dict) -> Enveloppe:
        """Reconstruit une enveloppe à partir d'un dictionnaire reçu du réseau.

        Args:
            contenu (dict): dictionnaire issu de json.loads.

        Returns:
            Enveloppe: l'enveloppe reconstruite, pas encore vérifiée.

        Raises:
            TrameInvalideError: si un champ manque ou contient une valeur invalide.
        """
        message = Message.depuis_dict(contenu)
        manquants = CHAMPS_ENVELOPPE - contenu.keys()
        if manquants:
            raise TrameInvalideError(f"champs manquants dans l'enveloppe : {', '.join(sorted(manquants))}")
        try:
            return cls(message, contenu["ts"], contenu["nonce"], contenu["hmac"])
        except (TypeError, ValueError) as erreur:
            raise TrameInvalideError(f"enveloppe invalide : {erreur}") from erreur

    @classmethod
    def depuis_octets(cls, octets: bytes) -> Enveloppe:
        """Reconstruit une enveloppe à partir d'une trame TCP ou d'un datagramme UDP.

        Args:
            octets (bytes): JSON encodé en UTF-8.

        Returns:
            Enveloppe: l'enveloppe reconstruite, pas encore vérifiée.

        Raises:
            TrameInvalideError: si les octets ne sont pas un JSON UTF-8 ou si un champ est invalide.
        """
        try:
            contenu = json.loads(octets.decode("utf-8"))
        except UnicodeDecodeError as erreur:
            raise TrameInvalideError("trame non encodée en UTF-8") from erreur
        except json.JSONDecodeError as erreur:
            raise TrameInvalideError(f"JSON invalide : {erreur.msg}") from erreur
        return cls.depuis_dict(contenu)

    def vers_dict(self) -> dict:
        """Convertit l'enveloppe en dictionnaire à plat, prêt pour json.dumps.

        Returns:
            dict: champs du message, plus « ts », « nonce » et « hmac ».
        """
        contenu = self.message.vers_dict()
        contenu.update(ts=self.ts, nonce=self.nonce, hmac=self.hmac)
        return contenu

    def vers_octets(self) -> bytes:
        """Encode l'enveloppe en JSON UTF-8, pour une trame TCP ou un datagramme UDP.

        Returns:
            bytes: le JSON compact de l'enveloppe.
        """
        return json.dumps(self.vers_dict(), separators=(",", ":")).encode("utf-8")
