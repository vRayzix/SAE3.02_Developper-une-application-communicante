"""Signature HMAC-SHA256 des enveloppes et protection contre le rejeu.

On garantit l'authenticité, l'intégrité et la fraîcheur des trames, pas leur
confidentialité : aucune bibliothèque de chiffrement externe n'est autorisée,
et un chiffrement maison donnerait une fausse impression de sécurité
(voir docs/securite.md).
"""

import dataclasses
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time

from cherrypie.commun.erreurs import HorodatageHorsFenetreError, RejeuDetecteError, SignatureInvalideError
from cherrypie.commun.protocole import Enveloppe, Message

# 8 octets aléatoires, soit 16 caractères hexadécimaux : tirer deux fois le même
# nonce pendant la fenêtre anti-rejeu de quelques secondes est improbable.
TAILLE_NONCE = 8
# Inscriptions ou abonnements restés sans réponse avant de journaliser le conseil.
ESSAIS_AVANT_CONSEIL = 3
# Une fois par processus : la supervision fait tourner des dizaines de clients, qui
# échoueraient tous pour la même raison.
conseil_journalise = threading.Event()
verrou_conseil = threading.Lock()


def conseil_horloges(fenetre: float) -> str:
    """Ce qu'il faut vérifier quand le serveur et ses clients refusent les trames les uns des autres."""
    return (
        f"vérifier que les horloges des machines ont moins de {fenetre:g} s d'écart (comparer « date +%s » "
        "sous Linux et « ([DateTimeOffset](Get-Date)).ToUnixTimeSeconds() » sous Windows) et que CHERRYPIE_CLE "
        "est identique des deux côtés ; pour dépanner sans régler les horloges : --fenetre-anti-rejeu, "
        "avec la même valeur sur toutes les machines"
    )


def conseiller_une_fois(journal: logging.Logger, constat: str, fenetre: float) -> None:
    """Journalise le constat suivi de conseil_horloges(), une seule fois par processus."""
    with verrou_conseil:
        if conseil_journalise.is_set():
            return
        conseil_journalise.set()
    journal.warning("%s : %s", constat, conseil_horloges(fenetre))


class Signataire:
    """Signe les messages sortants et vérifie les enveloppes entrantes.

    Le serveur et tous les clients partagent la même clé, donnée par CHERRYPIE_CLE ou saisie au lancement.
    """

    def __init__(self, cle: bytes) -> None:
        """Crée un signataire avec la clé HMAC partagée ; ValueError si elle est vide."""
        if not cle:
            raise ValueError("la clé HMAC ne peut pas être vide")
        self.__cle = bytes(cle)

    @property
    def cle(self) -> bytes:
        """bytes: clé HMAC partagée."""
        return self.__cle

    def signer(self, message: Message) -> Enveloppe:
        """Emballe un message dans une enveloppe horodatée, avec un nonce neuf et son HMAC."""
        enveloppe = Enveloppe(message, time.time(), secrets.token_hex(TAILLE_NONCE))
        return dataclasses.replace(enveloppe, hmac=self.__calculer_hmac(enveloppe))

    def verifier(self, enveloppe: Enveloppe) -> None:
        """Vérifie que le HMAC d'une enveloppe correspond à son contenu.

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


class GardeAntiRejeu:
    """Refuse les enveloppes trop anciennes, datées du futur ou déjà reçues.

    Un nonce n'est retenu que le temps de la fenêtre : passé ce délai, l'enveloppe
    qui le porte serait de toute façon refusée pour son horodatage. Le cache reste
    ainsi borné par le trafic reçu pendant une fenêtre.
    """

    def __init__(self, fenetre: float) -> None:
        """Crée une garde anti-rejeu ; fenetre est l'écart maximal accepté avec l'heure locale, en secondes.

        Raises:
            ValueError: si la fenêtre n'est pas strictement positive.
        """
        if fenetre <= 0:
            raise ValueError(f"la fenêtre anti-rejeu doit être strictement positive (reçu : {fenetre})")
        self.__fenetre = fenetre
        self.__nonces_vus: dict[str, float] = {}

    @property
    def fenetre(self) -> float:
        """float: écart maximal accepté avec l'heure locale, en secondes."""
        return self.__fenetre

    @property
    def nonces_vus(self) -> dict[str, float]:
        """dict[str, float]: nonces retenus, associés à l'horodatage de leur enveloppe (copie)."""
        return dict(self.__nonces_vus)

    def controler(self, enveloppe: Enveloppe, maintenant: float) -> None:
        """Vérifie qu'une enveloppe est récente et inédite, puis retient son nonce.

        À appeler après Signataire.verifier() : tant que la signature n'est pas
        vérifiée, l'horodatage et le nonce ont pu être choisis par un attaquant.
        `maintenant` est l'heure locale, en secondes depuis l'epoch.

        Raises:
            HorodatageHorsFenetreError: si l'horodatage sort de la fenêtre.
            RejeuDetecteError: si le nonce a déjà été reçu.
        """
        ecart = maintenant - enveloppe.ts
        if abs(ecart) > self.__fenetre:
            raise HorodatageHorsFenetreError(
                f"horodatage hors fenêtre ({ecart:+.1f} s) sur un message de {enveloppe.message.emetteur}"
            )
        self.__oublier_nonces_expires(maintenant)
        if enveloppe.nonce in self.__nonces_vus:
            raise RejeuDetecteError(f"nonce {enveloppe.nonce} déjà reçu de {enveloppe.message.emetteur}")
        self.__nonces_vus[enveloppe.nonce] = enveloppe.ts

    def __oublier_nonces_expires(self, maintenant: float) -> None:
        """Retire les nonces dont l'enveloppe serait de toute façon refusée pour son horodatage."""
        # Les nonces sont rangés par ordre d'arrivée, donc à peu près par horodatage :
        # on s'arrête au premier encore valable plutôt que de parcourir tout le cache.
        while self.__nonces_vus:
            nonce, ts = next(iter(self.__nonces_vus.items()))
            if maintenant - ts <= self.__fenetre:
                break
            del self.__nonces_vus[nonce]
