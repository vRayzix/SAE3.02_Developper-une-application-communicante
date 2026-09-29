"""Socket TCP d'un client, côté serveur, avec ses tampons de réception et d'envoi."""

from __future__ import annotations

import socket

from cherrypie.commun.trame import DecoupeurTrames

# Octets demandés à chaque lecture : de quoi recevoir plusieurs trames d'un coup.
TAILLE_LECTURE = 65536
# Au-delà, le client ne lit plus ses messages : mieux vaut le déconnecter que de
# garder indéfiniment ses messages en mémoire.
TAILLE_MAX_EN_ATTENTE = 1024 * 1024


class Connexion:
    """Socket TCP d'un client, avec ses tampons de réception et d'envoi.

    La socket est non bloquante : select indique quand lire ou écrire, le découpeur
    recolle les trames arrivées en morceaux, et ce qui n'a pas pu partir attend dans
    le tampon d'envoi. Un client lent ne bloque donc jamais le serveur.
    """

    def __init__(self, prise: socket.socket, adresse: tuple[str, int]) -> None:
        """Prend en charge une socket renvoyée par accept().

        Args:
            prise (socket.socket): socket connectée au client.
            adresse (tuple[str, int]): adresse IP et port du client.
        """
        prise.setblocking(False)
        # Les messages sont petits et attendus tout de suite : on désactive
        # l'algorithme de Nagle, qui les retarderait pour les regrouper.
        prise.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.__socket = prise
        self.__adresse = adresse
        self.__decoupeur = DecoupeurTrames()
        self.__a_envoyer = bytearray()

    @property
    def socket(self) -> socket.socket:
        """socket.socket: socket connectée au client, à surveiller avec select."""
        return self.__socket

    @property
    def adresse(self) -> tuple[str, int]:
        """tuple[str, int]: adresse IP et port du client."""
        return self.__adresse

    @property
    def decoupeur(self) -> DecoupeurTrames:
        """DecoupeurTrames: tampon des octets reçus qui ne forment pas encore une trame."""
        return self.__decoupeur

    @property
    def octets_en_attente(self) -> int:
        """int: nombre d'octets en file d'envoi, que la socket n'a pas encore acceptés."""
        return len(self.__a_envoyer)

    def recevoir(self) -> list[bytes]:
        """Lit ce qui est arrivé et renvoie les trames devenues complètes.

        Une lecture peut contenir un morceau de trame comme plusieurs trames : le
        découpeur garde les morceaux jusqu'à ce que chaque trame soit complète.

        Returns:
            list[bytes]: charges utiles des trames complètes, éventuellement aucune.

        Raises:
            ConnectionResetError: si le client a coupé la connexion brutalement.
            ConnectionError: si le client a fermé la connexion (lecture de 0 octet).
            TrameInvalideError: si le flux annonce une trame démesurée.
        """
        try:
            octets = self.__socket.recv(TAILLE_LECTURE)
        except BlockingIOError:
            # select peut signaler une socket prête alors que rien n'est encore lisible.
            return []
        if not octets:
            raise ConnectionError("connexion fermée par le client")
        return self.__decoupeur.ajouter(octets)

    def envoyer(self, trame: bytes) -> None:
        """Met une trame en file d'envoi, puis envoie tout de suite ce que la socket accepte.

        Args:
            trame (bytes): trame complète, en-tête de longueur compris.

        Raises:
            ConnectionError: si le client ne lit plus ses messages (file pleine), ou s'il
                a disparu (BrokenPipeError, ConnectionResetError).
        """
        if len(self.__a_envoyer) + len(trame) > TAILLE_MAX_EN_ATTENTE:
            raise ConnectionError(f"client trop lent : plus de {TAILLE_MAX_EN_ATTENTE} octets en attente d'envoi")
        self.__a_envoyer.extend(trame)
        self.vider()

    def vider(self) -> None:
        """Envoie ce que la socket accepte sans bloquer ; le reste attend le tour suivant.

        Raises:
            ConnectionError: si le client a disparu (BrokenPipeError, ConnectionResetError).
        """
        if not self.__a_envoyer:
            return
        try:
            envoyes = self.__socket.send(self.__a_envoyer)
        except BlockingIOError:
            return
        del self.__a_envoyer[:envoyes]

    def fermer(self) -> None:
        """Ferme la socket."""
        self.__socket.close()
