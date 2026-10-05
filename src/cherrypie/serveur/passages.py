"""Passages des véhicules prioritaires : suivi pendant la traversée et mesures conservées."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from cherrypie.modele.trajectoire import Etape


@dataclass(frozen=True)
class PassageVp:
    """Traversée mesurée d'un véhicule prioritaire, prête à être enregistrée.

    La mesure va de l'annonce du VP (VP_ALERT) à sa sortie de l'anneau (VP_FIN), avec la
    même définition que la régulation soit active ou non.

    Attributes:
        identifiant (str): identifiant du VP.
        entree (str): branche d'entrée.
        sortie (str): branche de sortie.
        debut (datetime): instant de l'annonce.
        fin (datetime): instant de sortie de l'anneau.
        duree (float): temps de traversée, de l'annonce à la sortie de l'anneau, en secondes.
        duree_anneau (float | None): temps passé sur l'anneau seul, None si le VP n'y a pas été vu.
        regulation (bool): True si la régulation était active à l'annonce du VP.
        densite_moyenne (float): densité moyenne des branches pendant la traversée, entre 0 et 1.
    """

    identifiant: str
    entree: str
    sortie: str
    debut: datetime
    fin: datetime
    duree: float
    duree_anneau: float | None
    regulation: bool
    densite_moyenne: float


class PassageEnCours:
    """Véhicule prioritaire annoncé (VP_ALERT) dont la traversée n'est pas finie.

    Il réserve les segments de sa trajectoire. Le chronomètre part à l'annonce et s'arrête
    au VP_FIN ; la durée passée sur l'anneau seule est gardée à part. Entre les deux, la
    densité moyenne des branches est relevée à chaque cadence du serveur.
    """

    def __init__(
        self,
        identifiant: str,
        entree: str,
        sortie: str,
        segments_reserves: list[str],
        annonce: float,
        regulation: bool,
    ) -> None:
        """Ouvre le suivi d'un VP qui vient de s'annoncer et démarre le chronomètre.

        Args:
            identifiant (str): identifiant du VP.
            entree (str): branche d'entrée.
            sortie (str): branche de sortie.
            segments_reserves (list[str]): noms des segments de sa trajectoire sur l'anneau.
            annonce (float): instant du VP_ALERT, sur l'horloge monotone du serveur.
            regulation (bool): régulation en vigueur à l'annonce.
        """
        self.__identifiant = identifiant
        self.__entree = entree
        self.__sortie = sortie
        self.__segments_reserves = tuple(segments_reserves)
        self.__annonce = annonce
        self.__debut = datetime.now()
        self.__regulation = regulation
        self.__entree_anneau: float | None = None
        self.__releves_densite: list[float] = []

    @property
    def identifiant(self) -> str:
        """str: identifiant du VP."""
        return self.__identifiant

    @property
    def entree(self) -> str:
        """str: branche d'entrée du VP."""
        return self.__entree

    @property
    def sortie(self) -> str:
        """str: branche de sortie du VP."""
        return self.__sortie

    @property
    def segments_reserves(self) -> tuple[str, ...]:
        """tuple[str, ...]: segments de l'anneau réservés au VP, dans l'ordre de passage."""
        return self.__segments_reserves

    @property
    def annonce(self) -> float:
        """float: instant de l'annonce, sur l'horloge monotone du serveur."""
        return self.__annonce

    @property
    def debut(self) -> datetime:
        """datetime: date et heure de l'annonce."""
        return self.__debut

    @property
    def regulation(self) -> bool:
        """bool: régulation en vigueur à l'annonce."""
        return self.__regulation

    @property
    def entree_anneau(self) -> float | None:
        """float | None: instant d'entrée sur l'anneau (horloge monotone), None avant."""
        return self.__entree_anneau

    @property
    def releves_densite(self) -> list[float]:
        """list[float]: densités moyennes relevées pendant la traversée (copie)."""
        return list(self.__releves_densite)

    @property
    def sur_l_anneau(self) -> bool:
        """bool: True une fois que le VP a été vu sur l'anneau."""
        return self.__entree_anneau is not None

    def noter_etape(self, etape: Etape, maintenant: float) -> None:
        """Note l'entrée du VP sur l'anneau, à son premier POS reçu sur l'anneau.

        Args:
            etape (Etape): étape annoncée par le dernier POS du VP.
            maintenant (float): instant de réception, sur l'horloge monotone du serveur.
        """
        if etape is Etape.ANNEAU and self.__entree_anneau is None:
            self.__entree_anneau = maintenant

    def noter_densite(self, densite_moyenne: float) -> None:
        """Relève la densité moyenne des branches pendant la traversée.

        Args:
            densite_moyenne (float): moyenne des densités des branches, entre 0 et 1.
        """
        self.__releves_densite.append(densite_moyenne)

    def terminer(self, maintenant: float) -> PassageVp:
        """Arrête le chronomètre à la sortie de l'anneau.

        Args:
            maintenant (float): instant du VP_FIN, sur l'horloge monotone du serveur.

        Returns:
            PassageVp: la mesure de la traversée.
        """
        duree = maintenant - self.__annonce
        duree_anneau = None if self.__entree_anneau is None else maintenant - self.__entree_anneau
        releves = self.__releves_densite
        densite_moyenne = sum(releves) / len(releves) if releves else 0.0
        return PassageVp(
            self.__identifiant,
            self.__entree,
            self.__sortie,
            self.__debut,
            self.__debut + timedelta(seconds=duree),
            duree,
            duree_anneau,
            self.__regulation,
            densite_moyenne,
        )
