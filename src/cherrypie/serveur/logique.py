"""Logique du serveur, indépendante du réseau.

La boucle réseau (serveur.py) confie à LogiqueServeur chaque message reçu, puis
envoie ce qu'elle renvoie. Aucune méthode ne touche une socket : toute la logique
se teste sans réseau.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from cherrypie.commun.erreurs import BrancheInconnueError, TrameInvalideError
from cherrypie.commun.protocole import Message, TypeMessage
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import Etape
from cherrypie.modele.usager import Usager, VehiculePrioritaire
from cherrypie.serveur.passages import PassageEnCours, PassageVp
from cherrypie.serveur.registre import Registre
from cherrypie.serveur.session import Session

IDENTIFIANT_SERVEUR = "serveur"
CHAMPS_HELLO = ("categorie", "entree", "sortie")
CHAMPS_POS = ("x", "y", "vitesse", "segment", "etape")

journal = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reponse:
    """Suite à donner à un message reçu en TCP.

    Attributes:
        messages (tuple[Message, ...]): messages à renvoyer à l'émetteur, dans l'ordre.
        fermer (bool): True si la session doit être fermée ensuite.
    """

    messages: tuple[Message, ...] = ()
    fermer: bool = False


class LogiqueServeur:
    """Décisions du serveur : sessions, registre des usagers et réponses aux messages."""

    def __init__(self, rond_point: RondPoint, timeout_client: float) -> None:
        """Crée la logique d'un serveur, sans session ni usager.

        Args:
            rond_point (RondPoint): rond-point géré par le serveur.
            timeout_client (float): silence au-delà duquel une session expire, en secondes.

        Raises:
            ValueError: si le timeout n'est pas strictement positif.
        """
        if not timeout_client > 0:
            raise ValueError(f"le timeout des clients doit être positif (reçu : {timeout_client})")
        self.__rond_point = rond_point
        self.__timeout_client = timeout_client
        self.__registre = Registre()
        self.__sessions: dict[int, Session] = {}
        self.__passages_en_cours: dict[str, PassageEnCours] = {}
        self.__passages: list[PassageVp] = []
        self.__regulation_active = True
        self.__total_sessions = 0

    @property
    def rond_point(self) -> RondPoint:
        """RondPoint: rond-point géré par le serveur."""
        return self.__rond_point

    @property
    def timeout_client(self) -> float:
        """float: silence au-delà duquel une session expire, en secondes."""
        return self.__timeout_client

    @property
    def registre(self) -> Registre:
        """Registre: usagers connectés."""
        return self.__registre

    @property
    def sessions(self) -> list[Session]:
        """list[Session]: sessions ouvertes (copie)."""
        return list(self.__sessions.values())

    @property
    def total_sessions(self) -> int:
        """int: nombre de sessions ouvertes depuis le démarrage, qui sert aussi à les numéroter."""
        return self.__total_sessions

    @property
    def passages_en_cours(self) -> list[PassageEnCours]:
        """list[PassageEnCours]: VP annoncés dont la traversée n'est pas finie (copie)."""
        return list(self.__passages_en_cours.values())

    @property
    def passages(self) -> list[PassageVp]:
        """list[PassageVp]: traversées de VP mesurées depuis le démarrage, à enregistrer en base (copie)."""
        return list(self.__passages)

    @property
    def regulation_active(self) -> bool:
        """bool: True si le serveur régule le trafic, False s'il sert de référence pour la mesure."""
        return self.__regulation_active

    @property
    def vp_actif(self) -> bool:
        """bool: True si au moins un VP annoncé n'a pas fini sa traversée."""
        return bool(self.__passages_en_cours)

    def ouvrir_session(self, maintenant: float) -> int:
        """Ouvre une session pour une nouvelle connexion TCP.

        Args:
            maintenant (float): instant de la connexion, sur l'horloge monotone du serveur.

        Returns:
            int: numéro de la session, que la boucle réseau associe à sa socket.
        """
        self.__total_sessions += 1
        numero = self.__total_sessions
        self.__sessions[numero] = Session(numero, maintenant)
        return numero

    def fermer_session(self, numero: int) -> Usager | None:
        """Oublie une session et retire son usager du registre.

        Args:
            numero (int): numéro de la session.

        Returns:
            Usager | None: l'usager retiré, None si la session n'en avait pas ou était déjà fermée.
        """
        session = self.__sessions.pop(numero, None)
        if session is None or session.identifiant is None:
            return None
        if self.__passages_en_cours.pop(session.identifiant, None) is not None:
            journal.warning("VP %s disparu avant son VP_FIN : sa réservation est levée, sans mesure", session.identifiant)
        return self.__registre.retirer(session.identifiant)

    def traiter_tcp(self, numero: int, message: Message, maintenant: float) -> Reponse:
        """Traite un message reçu sur une session TCP.

        Args:
            numero (int): numéro de la session qui a reçu le message.
            message (Message): message déjà authentifié (HMAC et anti-rejeu vérifiés).
            maintenant (float): instant de réception, sur l'horloge monotone du serveur.

        Returns:
            Reponse: messages à renvoyer à l'émetteur, et fermeture éventuelle de la session.

        Raises:
            TrameInvalideError: si le message parle au nom d'un autre usager que celui de
                la session, ou si son type n'a pas sa place sur une session TCP.
        """
        session = self.__sessions[numero]
        # Contrôle d'identité : une fois le HELLO passé, la session ne parle qu'au nom de son usager.
        if session.identifiant is not None and message.emetteur != session.identifiant:
            raise TrameInvalideError(f"message de {message.emetteur} reçu sur la session de {session.identifiant}")
        session.derniere_activite = maintenant
        if message.type is TypeMessage.HELLO:
            return self.__accueillir(session, message)
        if message.type is TypeMessage.PING:
            return Reponse((Message(TypeMessage.PONG, IDENTIFIANT_SERVEUR),))
        if message.type is TypeMessage.ABONNEMENT:
            return self.__abonner(session)
        if message.type is TypeMessage.BYE:
            return Reponse(fermer=True)
        if message.type is TypeMessage.VP_ALERT:
            return self.__signaler_vp(session, message)
        if message.type is TypeMessage.VP_FIN:
            return self.__terminer_vp(session, maintenant)
        raise TrameInvalideError(f"message {message.type.value} inattendu sur une session TCP")

    def traiter_udp(self, message: Message, maintenant: float) -> None:
        """Met à jour un usager à partir d'une position reçue en UDP.

        Si l'usager est un VP annoncé, sa première position sur l'anneau démarre la mesure
        de sa traversée.

        Args:
            message (Message): message déjà authentifié (HMAC et anti-rejeu vérifiés).
            maintenant (float): instant de réception, sur l'horloge monotone du serveur.

        Raises:
            TrameInvalideError: si le message n'est pas un POS ou si ses données sont invalides.
            UsagerInconnuError: si l'émetteur n'a pas de session TCP ouverte.
        """
        if message.type is not TypeMessage.POS:
            raise TrameInvalideError(f"seuls les POS passent par UDP (reçu : {message.type.value})")
        # Contrôle d'identité : seuls les usagers dont la session TCP est ouverte sont au registre.
        usager = self.__registre.obtenir(message.emetteur)
        donnees = message.donnees
        manquants = [champ for champ in CHAMPS_POS if champ not in donnees]
        if manquants:
            raise TrameInvalideError(f"POS incomplet, il manque : {', '.join(manquants)}")
        noms_segments = [segment.nom for segment in self.__rond_point.segments]
        if donnees["segment"] is not None and donnees["segment"] not in noms_segments:
            raise TrameInvalideError(f"POS sur un segment inconnu : {donnees['segment']!r}")
        try:
            etape = Etape(donnees["etape"])
        except ValueError as erreur:
            raise TrameInvalideError(f"POS avec une étape inconnue : {donnees['etape']!r}") from erreur
        # Le segment n'a de sens que sur l'anneau : la régulation s'appuie sur les deux à la fois.
        if (etape is Etape.ANNEAU) != (donnees["segment"] is not None):
            raise TrameInvalideError(f"POS incohérent : étape {etape.value} et segment {donnees['segment']!r}")
        try:
            position = Position(donnees["x"], donnees["y"])
            # La vitesse est la première valeur modifiée : si elle est refusée, l'usager reste tel quel.
            usager.vitesse = donnees["vitesse"]
        except (TypeError, ValueError) as erreur:
            raise TrameInvalideError(f"POS invalide de {message.emetteur} : {erreur}") from erreur
        usager.segment = donnees["segment"]
        usager.etape = etape
        usager.position = position
        passage = self.__passages_en_cours.get(usager.identifiant)
        if passage is not None:
            passage.noter_etape(etape, maintenant, self.__regulation_active)

    def sessions_expirees(self, maintenant: float) -> list[int]:
        """Liste les sessions restées silencieuses plus longtemps que le timeout.

        La boucle réseau les ferme ensuite : un client qui ne donne plus de nouvelles
        ne pourrait de toute façon plus recevoir de consignes.

        Args:
            maintenant (float): instant présent, sur l'horloge monotone du serveur.

        Returns:
            list[int]: numéros des sessions expirées.
        """
        return [
            session.numero
            for session in self.__sessions.values()
            if session.est_expiree(maintenant, self.__timeout_client)
        ]

    def superviseurs(self) -> list[int]:
        """Liste les sessions abonnées aux STATE.

        Returns:
            list[int]: numéros des sessions de supervision.
        """
        return [session.numero for session in self.__sessions.values() if session.superviseur]

    def construire_etat(self) -> Message:
        """Construit le STATE diffusé aux supervisions.

        Returns:
            Message: STATE qui liste les usagers connectés et leur dernier état connu.
        """
        usagers = [usager.vers_dict() for usager in self.__registre.usagers]
        return Message(TypeMessage.STATE, IDENTIFIANT_SERVEUR, {"usagers": usagers})

    def __accueillir(self, session: Session, message: Message) -> Reponse:
        """Inscrit l'usager annoncé par un HELLO, ou lui explique pourquoi il est refusé."""
        if session.identifiant is not None or session.superviseur:
            return self.__refuser(message.emetteur, "cette session est déjà enregistrée", reessayer=False)
        if self.__registre.contient(message.emetteur):
            # Refus provisoire : l'autre session de cet identifiant a pu disparaître sans
            # prévenir ; elle expirera au bout de timeout_client et le client pourra réessayer.
            raison = f"l'identifiant {message.emetteur} est déjà connecté"
            return self.__refuser(message.emetteur, raison, reessayer=True)
        try:
            usager = self.__creer_usager(message)
        except (ValueError, TypeError, BrancheInconnueError) as refus:
            return self.__refuser(message.emetteur, str(refus), reessayer=False)
        self.__registre.ajouter(usager)
        session.identifiant = usager.identifiant
        journal.info(
            "usager %s inscrit (%s, de %s vers %s)",
            usager.identifiant, usager.CATEGORIE, usager.branche_entree, usager.branche_sortie,
        )
        return Reponse((self.__accuse_hello(True),))

    def __creer_usager(self, message: Message) -> Usager:
        """Crée l'usager décrit par un HELLO, après avoir vérifié ses champs et ses branches."""
        donnees = message.donnees
        manquants = [champ for champ in CHAMPS_HELLO if champ not in donnees]
        if manquants:
            raise ValueError(f"HELLO incomplet, il manque : {', '.join(manquants)}")
        usager = Usager.depuis_dict({"id": message.emetteur, **{champ: donnees[champ] for champ in CHAMPS_HELLO}})
        # Lève BrancheInconnueError si l'une des deux branches n'existe pas dans ce rond-point.
        self.__rond_point.branche(usager.branche_entree)
        self.__rond_point.branche(usager.branche_sortie)
        return usager

    def __signaler_vp(self, session: Session, message: Message) -> Reponse:
        """Enregistre l'annonce d'un VP et réserve les segments de sa trajectoire."""
        vp = self.__usager_de(session)
        if not isinstance(vp, VehiculePrioritaire):
            raise TrameInvalideError(f"VP_ALERT de {vp.identifiant}, qui n'est pas un véhicule prioritaire")
        donnees = message.donnees
        if (donnees.get("entree"), donnees.get("sortie")) != (vp.branche_entree, vp.branche_sortie):
            raise TrameInvalideError(f"VP_ALERT de {vp.identifiant} différent du trajet annoncé dans son HELLO")
        eta = donnees.get("eta")
        # bool est une sous-classe de int ; et écrit ainsi, le test refuse aussi NaN.
        if isinstance(eta, bool) or not isinstance(eta, (int, float)) or not 0 <= eta < math.inf:
            raise TrameInvalideError(f"VP_ALERT de {vp.identifiant} avec un eta invalide : {eta!r}")
        if vp.identifiant not in self.__passages_en_cours:
            segments = [segment.nom for segment in vp.calculer_trajectoire(self.__rond_point).segments]
            self.__passages_en_cours[vp.identifiant] = PassageEnCours(
                vp.identifiant, vp.branche_entree, vp.branche_sortie, segments
            )
            journal.info(
                "VP %s annoncé de %s vers %s, à l'anneau dans %.1f s ; segments réservés : %s",
                vp.identifiant, vp.branche_entree, vp.branche_sortie, eta, ", ".join(segments),
            )
        return Reponse()

    def __terminer_vp(self, session: Session, maintenant: float) -> Reponse:
        """Clôt la traversée d'un VP sorti de l'anneau et conserve sa mesure."""
        vp = self.__usager_de(session)
        passage = self.__passages_en_cours.pop(vp.identifiant, None)
        if passage is None:
            raise TrameInvalideError(f"VP_FIN de {vp.identifiant} sans VP_ALERT")
        mesure = passage.terminer(maintenant)
        if mesure is None:
            journal.warning("VP %s sorti sans avoir été vu sur l'anneau : pas de mesure", vp.identifiant)
        else:
            self.__passages.append(mesure)
            journal.info(
                "VP %s : %.1f s sur l'anneau, régulation %s",
                vp.identifiant, mesure.duree, "active" if mesure.regulation else "inactive",
            )
        return Reponse()

    def __usager_de(self, session: Session) -> Usager:
        """Renvoie l'usager inscrit sur une session, pour un message qui en exige un."""
        if session.identifiant is None:
            raise TrameInvalideError(f"message réservé à une session d'usager inscrit (session {session.numero})")
        return self.__registre.obtenir(session.identifiant)

    def __abonner(self, session: Session) -> Reponse:
        """Abonne une session de supervision aux STATE."""
        if session.identifiant is not None:
            raise TrameInvalideError(f"l'usager {session.identifiant} ne peut pas s'abonner aux STATE")
        session.superviseur = True
        journal.info("supervision abonnée aux STATE (session %d)", session.numero)
        return Reponse()

    @staticmethod
    def __refuser(emetteur: str, raison: str, reessayer: bool) -> Reponse:
        """Refuse un HELLO, en disant au client s'il peut réessayer plus tard."""
        journal.info("HELLO de %s refusé : %s", emetteur, raison)
        return Reponse((LogiqueServeur.__accuse_hello(False, raison, reessayer),))

    @staticmethod
    def __accuse_hello(accepte: bool, raison: str | None = None, reessayer: bool = False) -> Message:
        """Construit la réponse à un HELLO ; un refus dit pourquoi, et si un nouvel essai peut réussir."""
        donnees: dict = {"accepte": accepte}
        if not accepte:
            donnees["raison"] = raison
            donnees["reessayer"] = reessayer
        return Message(TypeMessage.HELLO_ACK, IDENTIFIANT_SERVEUR, donnees)
