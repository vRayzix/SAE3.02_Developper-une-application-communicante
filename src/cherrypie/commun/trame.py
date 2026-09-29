"""Découpage des trames sur une connexion TCP.

TCP transporte un flux d'octets, sans frontières entre les messages : un recv()
peut renvoyer une demi-trame comme plusieurs trames collées. Chaque trame
commence donc par la longueur de sa charge utile, sur 4 octets en ordre réseau.
"""

import struct

from cherrypie.commun.erreurs import TrameInvalideError

FORMAT_EN_TETE = "!I"
TAILLE_EN_TETE = struct.calcsize(FORMAT_EN_TETE)
# Aucun message légitime n'approche cette taille. Au-delà, on considère le flux
# corrompu plutôt que de réserver des mégaoctets pour une longueur fantaisiste.
TAILLE_MAX_TRAME = 1024 * 1024


class DecoupeurTrames:
    """Reconstitue les trames complètes à partir des octets reçus sur une socket TCP.

    Il faut un découpeur par socket, puisque chacune a son propre flux.
    """

    def __init__(self) -> None:
        """Crée un découpeur au tampon vide."""
        self.__tampon = bytearray()

    @property
    def tampon(self) -> bytes:
        """bytes: octets reçus qui ne forment pas encore une trame complète (copie)."""
        return bytes(self.__tampon)

    def ajouter(self, octets: bytes) -> list[bytes]:
        """Ajoute des octets reçus et renvoie les trames devenues complètes.

        Args:
            octets (bytes): données renvoyées par recv().

        Returns:
            list[bytes]: charges utiles des trames complètes, dans l'ordre d'arrivée.
                La liste est vide si aucune trame n'est encore complète.

        Raises:
            TrameInvalideError: si un en-tête annonce plus de TAILLE_MAX_TRAME octets.
                Le flux ne peut alors plus être resynchronisé : il faut fermer la connexion.
        """
        self.__tampon.extend(octets)
        trames = []
        while len(self.__tampon) >= TAILLE_EN_TETE:
            (longueur,) = struct.unpack_from(FORMAT_EN_TETE, self.__tampon)
            if longueur > TAILLE_MAX_TRAME:
                raise TrameInvalideError(f"trame annoncée de {longueur} octets, limite {TAILLE_MAX_TRAME}")
            fin = TAILLE_EN_TETE + longueur
            if len(self.__tampon) < fin:
                break
            trames.append(bytes(self.__tampon[TAILLE_EN_TETE:fin]))
            del self.__tampon[:fin]
        return trames

    @staticmethod
    def encoder(charge: bytes) -> bytes:
        """Préfixe une charge utile par sa longueur, pour l'envoyer sur TCP.

        Args:
            charge (bytes): octets à envoyer (en pratique, une enveloppe JSON).

        Returns:
            bytes: l'en-tête de longueur suivi de la charge.

        Raises:
            TrameInvalideError: si la charge dépasse TAILLE_MAX_TRAME octets.
        """
        if len(charge) > TAILLE_MAX_TRAME:
            raise TrameInvalideError(f"charge de {len(charge)} octets, limite {TAILLE_MAX_TRAME}")
        return struct.pack(FORMAT_EN_TETE, len(charge)) + charge
