"""Passages des véhicules prioritaires : suivi pendant la traversée et mesures conservées."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from cherrypie.modele.trajectoire import Etape


@dataclass(frozen=True)
class PassageVp:
    """Traversée mesurée d'un véhicule prioritaire, prête à être enregistrée.

    Attributes:
        identifiant (str): identifiant du VP.
        entree (str): branche d'entrée.
        sortie (str): branche de sortie.
        debut (datetime): instant d'entrée sur l'anneau.
        fin (datetime): instant de sortie de l'anneau.
        duree (float): temps passé sur l'anneau, en secondes.
        regulation (bool): True si la régulation était active quand le VP est entré sur l'anneau.
        densite_moyenne (float): densité moyenne des branches pendant la traversée, entre 0 et 1.
    """

    identifiant: str
    entree: str
    sortie: str
    debut: datetime
    fin: datetime
    duree: float
    regulation: bool
    densite_moyenne: float


class PassageEnCours:
    """Véhicule prioritaire annoncé (VP_ALERT) dont la traversée n'est pas finie.

    Il réserve les segments de sa trajectoire. Le chronomètre part quand le VP entre sur
    l'anneau et s'arrête à son VP_FIN ; entre les deux, la densité moyenne des branches
    est relevée à chaque cadence du serveur.
    """

    def __init__(self, identifiant: str, entree: str, sortie: str, segments_reserves: list[str]) -> None:
        """Ouvre le suivi d'un VP qui vient de s'annoncer.

        Args:
            identifiant (str): identifiant du VP.
            entree (str): branche d'entrée.
            sortie (str): branche de sortie.
            segments_reserves (list[str]): noms des segments de sa trajectoire sur l'anneau.
        """
        self.__identifiant = identifiant
        self.__entree = entree
        self.__sortie = sortie
        self.__segments_reserves = tuple(segments_reserves)
        self.__entree_anneau: float | None = None
        self.__debut: datetime | None = None
        self.__regulation: bool | None = None
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
    def entree_anneau(self) -> float | None:
        """float | None: instant d'entrée sur l'anneau (horloge monotone), None avant."""
        return self.__entree_anneau

    @property
    def debut(self) -> datetime | None:
        """datetime | None: date et heure d'entrée sur l'anneau, None avant."""
        return self.__debut

    @property
    def regulation(self) -> bool | None:
        """bool | None: régulation en vigueur à l'entrée sur l'anneau, None avant."""
        return self.__regulation

    @property
    def releves_densite(self) -> list[float]:
        """list[float]: densités moyennes relevées pendant la traversée (copie)."""
        return list(self.__releves_densite)

    @property
    def sur_l_anneau(self) -> bool:
        """bool: True une fois que le VP a été vu sur l'anneau."""
        return self.__entree_anneau is not None

    def noter_etape(self, etape: Etape, maintenant: float, regulation: bool) -> None:
        """Démarre le chronomètre au premier POS reçu du VP sur l'anneau.

        Args:
            etape (Etape): étape annoncée par le dernier POS du VP.
            maintenant (float): instant de réception, sur l'horloge monotone du serveur.
            regulation (bool): régulation en vigueur à cet instant.
        """
        if etape is Etape.ANNEAU and self.__entree_anneau is None:
            self.__entree_anneau = maintenant
            self.__debut = datetime.now()
            self.__regulation = regulation

    def noter_densite(self, densite_moyenne: float) -> None:
        """Relève la densité moyenne des branches, si le VP est sur l'anneau.

        Args:
            densite_moyenne (float): moyenne des densités des branches, entre 0 et 1.
        """
        if self.sur_l_anneau:
            self.__releves_densite.append(densite_moyenne)

    def terminer(self, maintenant: float) -> PassageVp | None:
        """Arrête le chronomètre à la sortie de l'anneau.

        Args:
            maintenant (float): instant du VP_FIN, sur l'horloge monotone du serveur.

        Returns:
            PassageVp | None: la mesure de la traversée, None si le VP n'a jamais été vu sur l'anneau.
        """
        if self.__entree_anneau is None:
            return None
        duree = maintenant - self.__entree_anneau
        releves = self.__releves_densite
        densite_moyenne = sum(releves) / len(releves) if releves else 0.0
        return PassageVp(
            self.__identifiant,
            self.__entree,
            self.__sortie,
            self.__debut,
            self.__debut + timedelta(seconds=duree),
            duree,
            self.__regulation,
            densite_moyenne,
        )
