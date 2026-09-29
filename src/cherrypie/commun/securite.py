"""Signature HMAC-SHA256 des enveloppes.

On garantit l'authenticité et l'intégrité des trames, pas leur confidentialité :
aucune bibliothèque de chiffrement externe n'est autorisée, et un chiffrement
maison donnerait une fausse impression de sécurité (voir docs/securite.md).
"""

import dataclasses
import hashlib
import hmac
import json
import secrets
import time

from cherrypie.commun.erreurs import SignatureInvalideError
from cherrypie.commun.protocole import Enveloppe, Message

# 8 octets aléatoires, soit 16 caractères hexadécimaux : tirer deux fois le même
# nonce pendant la fenêtre anti-rejeu de quelques secondes est improbable.
TAILLE_NONCE = 8


class Signataire:
    """Signe les messages sortants et vérifie les enveloppes entrantes.

    Le serveur et tous les clients partagent la même clé, lue dans config.ini.
    """

    def __init__(self, cle: bytes) -> None:
        """Crée un signataire.

        Args:
            cle (bytes): clé HMAC partagée.

        Raises:
            ValueError: si la clé est vide.
        """
        if not cle:
            raise ValueError("la clé HMAC ne peut pas être vide")
        self.__cle = bytes(cle)

    @property
    def cle(self) -> bytes:
        """bytes: clé HMAC partagée."""
        return self.__cle

    def signer(self, message: Message) -> Enveloppe:
        """Emballe un message dans une enveloppe horodatée, avec un nonce neuf et son HMAC.

        Args:
            message (Message): message à envoyer.

        Returns:
            Enveloppe: l'enveloppe signée, prête à être encodée.
        """
        enveloppe = Enveloppe(message, time.time(), secrets.token_hex(TAILLE_NONCE))
        return dataclasses.replace(enveloppe, hmac=self.__calculer_hmac(enveloppe))

    def verifier(self, enveloppe: Enveloppe) -> None:
        """Vérifie que le HMAC d'une enveloppe correspond à son contenu.

        Args:
            enveloppe (Enveloppe): enveloppe reçue.

        Raises:
            SignatureInvalideError: si le HMAC est absent ou ne correspond pas au contenu.
        """
        attendu = self.__calculer_hmac(enveloppe)
        # Comparaison en octets, parce que compare_digest lève TypeError sur une chaîne
        # non ASCII. Elle se fait en temps constant : chronométrer les refus ne permet
        # pas de deviner le HMAC octet par octet.
        if not hmac.compare_digest(attendu.encode("ascii"), enveloppe.hmac.encode("utf-8")):
            raise SignatureInvalideError(f"HMAC invalide sur un message de {enveloppe.message.emetteur}")

    def __calculer_hmac(self, enveloppe: Enveloppe) -> str:
        """Calcule le HMAC d'une enveloppe sur son JSON canonique, champ hmac exclu."""
        contenu = enveloppe.vers_dict()
        del contenu["hmac"]
        # Clés triées et séparateurs fixes : l'émetteur et le récepteur signent
        # exactement les mêmes octets, quel que soit l'ordre des champs reçus.
        canonique = json.dumps(contenu, sort_keys=True, separators=(",", ":"))
        return hmac.new(self.__cle, canonique.encode("utf-8"), hashlib.sha256).hexdigest()
