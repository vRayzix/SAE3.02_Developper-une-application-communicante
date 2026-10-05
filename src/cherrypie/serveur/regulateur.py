"""Régulateur : décide quelle consigne chaque usager doit suivre.

Quand un véhicule prioritaire (VP) traverse, ses segments réservés devant lui doivent
rester libres :

1. un usager sur l'anneau qui est, ou va passer, sur un de ces segments se range : DEGAGEZ ;
2. un usager en file sur la branche d'entrée d'un VP encore en approche serre à droite
   pour le laisser passer : CHANGEZ_VOIE ;
3. un usager en approche dont le trajet passe par un de ces segments attend avant
   d'entrer : ATTENDEZ ;
4. un piéton qui attend devant le passage de la branche d'entrée ou de sortie d'un VP
   attend pour traverser : ATTENDEZ.

Sans VP, le régulateur dose les entrées : si une branche est en densité forte, la moins
chargée des autres entrées occupées, si elle n'est pas elle-même en densité forte, est
temporisée (ATTENDEZ). Moins de véhicules passent alors devant l'entrée saturée, qui
peut se vider.

Dans tous les autres cas, l'usager circule librement ; s'il avait une consigne, il
reçoit OK_PASSER. Le régulateur se souvient de la dernière consigne envoyée à chaque
usager et ne renvoie que les changements.
"""

from __future__ import annotations

from cherrypie.commun.protocole import CodeNotification
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import Etape
from cherrypie.modele.usager import Pieton, Usager, VehiculePrioritaire
from cherrypie.serveur.densite import CalculateurDensite, NiveauDensite
from cherrypie.serveur.notifications import (
    TEXTE_ATTENDEZ_DOSAGE,
    TEXTE_ATTENDEZ_PIETON,
    TEXTE_ATTENDEZ_VP,
    TEXTE_CHANGEZ_VOIE,
    TEXTE_DEGAGEZ,
    TEXTE_OK_PASSER,
    Notification,
)
from cherrypie.serveur.passages import PassageEnCours
from cherrypie.serveur.registre import Registre


class Regulateur:
    """Décide, à chaque cadence, des consignes à envoyer aux usagers."""

    def __init__(self, rond_point: RondPoint) -> None:
        """Crée un régulateur qui n'a encore envoyé aucune consigne.

        Args:
            rond_point (RondPoint): rond-point régulé.
        """
        self.__rond_point = rond_point
        self.__consignes_envoyees: dict[str, CodeNotification] = {}
        self.__entrees_bloquees: set[str] = set()

    @property
    def rond_point(self) -> RondPoint:
        """RondPoint: rond-point régulé."""
        return self.__rond_point

    @property
    def consignes_envoyees(self) -> dict[str, CodeNotification]:
        """dict[str, CodeNotification]: consigne en cours de chaque usager qui en a une (copie)."""
        return dict(self.__consignes_envoyees)

    @property
    def entrees_bloquees(self) -> list[str]:
        """list[str]: branches où au moins un usager attend sur ordre du régulateur, triées par nom."""
        return sorted(self.__entrees_bloquees)

    def decider(
        self, registre: Registre, passages: list[PassageEnCours], densites: dict[str, float]
    ) -> list[Notification]:
        """Compare la consigne voulue pour chaque usager à celle déjà envoyée.

        Args:
            registre (Registre): usagers connectés, avec leur dernière étape connue.
            passages (list[PassageEnCours]): VP annoncés dont la traversée n'est pas finie.
            densites (dict[str, float]): densité de chaque branche, pour le dosage des entrées.

        Returns:
            list[Notification]: consignes nouvelles ou levées, à envoyer à leurs destinataires.
        """
        vps = [(registre.obtenir(passage.identifiant), passage) for passage in passages]
        devant_les_vps = set().union(*(self.__segments_devant(vp, passage) for vp, passage in vps))
        branche_temporisee = None if vps else self.__branche_a_temporiser(densites)
        notifications = []
        for usager in registre.usagers:
            voulue = self.__consigne_voulue(usager, vps, devant_les_vps, branche_temporisee)
            notification = self.__changement(usager.identifiant, voulue)
            if notification is not None:
                notifications.append(notification)
        self.__entrees_bloquees = {
            usager.branche_entree
            for usager in registre.usagers
            if self.__consignes_envoyees.get(usager.identifiant) is CodeNotification.ATTENDEZ
        }
        return notifications

    def oublier(self, identifiant: str) -> None:
        """Oublie la consigne d'un usager parti.

        S'il revient sur une nouvelle session, il repart sans consigne : la prochaine
        décision lui renverra celle qui vaut encore.

        Args:
            identifiant (str): identifiant de l'usager.
        """
        self.__consignes_envoyees.pop(identifiant, None)

    def __consigne_voulue(
        self,
        usager: Usager,
        vps: list[tuple[Usager, PassageEnCours]],
        devant_les_vps: set[str],
        branche_temporisee: str | None,
    ) -> tuple[CodeNotification, str] | None:
        """Applique les règles, dans l'ordre, à un usager ; None s'il circule librement."""
        if isinstance(usager, VehiculePrioritaire):
            return None
        if not vps:
            return self.__consigne_de_dosage(usager, branche_temporisee)
        if isinstance(usager, Pieton):
            branches_des_vps = {branche for _, passage in vps for branche in (passage.entree, passage.sortie)}
            if usager.etape is Etape.APPROCHE and usager.branche_entree in branches_des_vps:
                return CodeNotification.ATTENDEZ, TEXTE_ATTENDEZ_PIETON
            return None
        sur_le_chemin_d_un_vp = bool(set(self.__chemin_restant(usager)) & devant_les_vps)
        if usager.etape is Etape.ANNEAU and sur_le_chemin_d_un_vp:
            return CodeNotification.DEGAGEZ, TEXTE_DEGAGEZ
        if usager.etape is Etape.APPROCHE:
            if any(vp.etape is Etape.APPROCHE and usager.branche_entree == vp.branche_entree for vp, _ in vps):
                return CodeNotification.CHANGEZ_VOIE, TEXTE_CHANGEZ_VOIE
            if sur_le_chemin_d_un_vp:
                return CodeNotification.ATTENDEZ, TEXTE_ATTENDEZ_VP
        return None

    @staticmethod
    def __consigne_de_dosage(usager: Usager, branche_temporisee: str | None) -> tuple[CodeNotification, str] | None:
        """Temporise les véhicules en approche sur la branche choisie par le dosage."""
        if (
            branche_temporisee is not None
            and not isinstance(usager, Pieton)
            and usager.etape is Etape.APPROCHE
            and usager.branche_entree == branche_temporisee
        ):
            return CodeNotification.ATTENDEZ, TEXTE_ATTENDEZ_DOSAGE
        return None

    @staticmethod
    def __branche_a_temporiser(densites: dict[str, float]) -> str | None:
        """Choisit l'entrée à temporiser quand une branche est en densité forte, None sinon.

        C'est la moins chargée des entrées occupées qui ne sont pas elles-mêmes en densité
        forte ; à égalité, la première dans l'ordre des branches.
        """
        niveaux = {branche: CalculateurDensite.niveau(densite) for branche, densite in densites.items()}
        if NiveauDensite.FORTE not in niveaux.values():
            return None
        candidates = [
            (densite, branche)
            for branche, densite in densites.items()
            if densite > 0 and niveaux[branche] is not NiveauDensite.FORTE
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda candidate: candidate[0])[1]

    def __changement(self, identifiant: str, voulue: tuple[CodeNotification, str] | None) -> Notification | None:
        """Renvoie la notification à envoyer si la consigne voulue diffère de celle déjà envoyée."""
        code = None if voulue is None else voulue[0]
        if code is self.__consignes_envoyees.get(identifiant):
            return None
        if voulue is None:
            del self.__consignes_envoyees[identifiant]
            return Notification(identifiant, CodeNotification.OK_PASSER, TEXTE_OK_PASSER)
        self.__consignes_envoyees[identifiant] = code
        return Notification(identifiant, code, voulue[1])

    def __chemin_restant(self, usager: Usager) -> list[str]:
        """Segments de l'anneau qu'un véhicule doit encore parcourir, segment en cours compris."""
        segments = [segment.nom for segment in usager.calculer_trajectoire(self.__rond_point).segments]
        if usager.etape is Etape.APPROCHE:
            return segments
        if usager.etape is Etape.ANNEAU and usager.segment in segments:
            return segments[segments.index(usager.segment):]
        return []

    @staticmethod
    def __segments_devant(vp: Usager, passage: PassageEnCours) -> set[str]:
        """Segments réservés que le VP n'a pas encore quittés, à l'échelle d'un segment."""
        reserves = list(passage.segments_reserves)
        if vp.etape is Etape.APPROCHE:
            return set(reserves)
        if vp.etape is Etape.ANNEAU and vp.segment in reserves:
            return set(reserves[reserves.index(vp.segment):])
        return set()
