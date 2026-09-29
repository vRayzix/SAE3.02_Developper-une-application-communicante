"""Trajectoires des usagers : suite de tronçons droits et d'arcs de l'anneau.

Un véhicule passe par trois étapes : l'approche sur sa branche d'entrée, un ou
plusieurs segments de l'anneau, puis la sortie sur sa branche de sortie.
L'avancement d'un usager est la distance qu'il a parcourue depuis son départ.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import RondPoint, Segment

# Longueur modélisée de chaque branche, entre son extrémité et l'anneau, en mètres.
LONGUEUR_BRANCHE = 50.0


class Etape(Enum):
    """Partie de sa trajectoire où se trouve un usager."""

    APPROCHE = "approche"
    ANNEAU = "anneau"
    SORTIE = "sortie"


@dataclass(frozen=True)
class TronconDroit:
    """Tronçon parcouru en ligne droite, sur une branche.

    Attributes:
        etape (Etape): étape de la trajectoire à laquelle appartient le tronçon.
        depart (Position): point de départ.
        arrivee (Position): point d'arrivée.
    """

    etape: Etape
    depart: Position
    arrivee: Position

    def __post_init__(self) -> None:
        """Refuse un tronçon de longueur nulle.

        Raises:
            ValueError: si le départ et l'arrivée sont confondus.
        """
        if self.depart == self.arrivee:
            raise ValueError("un tronçon relie deux points distincts")

    @property
    def longueur(self) -> float:
        """float: longueur du tronçon, en mètres."""
        return self.depart.distance(self.arrivee)

    @property
    def segment(self) -> None:
        """None: un tronçon droit n'appartient à aucun segment de l'anneau."""
        return None

    def position_a(self, distance: float, decalage: float) -> Position:
        """Calcule la position atteinte après une distance parcourue sur le tronçon.

        Args:
            distance (float): distance depuis le début du tronçon, en mètres.
            decalage (float): écart latéral en mètres, positif vers la droite du sens de marche.

        Returns:
            Position: la position correspondante.
        """
        longueur = self.longueur
        ux = (self.arrivee.x - self.depart.x) / longueur
        uy = (self.arrivee.y - self.depart.y) / longueur
        # Tourner la direction (ux, uy) d'un quart de tour vers la droite donne (uy, -ux).
        return Position(
            self.depart.x + ux * distance + uy * decalage,
            self.depart.y + uy * distance - ux * decalage,
        )


@dataclass(frozen=True)
class TronconArc:
    """Tronçon de l'anneau : un segment parcouru dans le sens de circulation.

    Attributes:
        segment (Segment): segment de l'anneau parcouru.
        rayon (float): rayon de l'anneau, en mètres.
    """

    segment: Segment
    rayon: float

    @property
    def etape(self) -> Etape:
        """Etape: toujours ANNEAU."""
        return Etape.ANNEAU

    @property
    def longueur(self) -> float:
        """float: longueur de l'arc, en mètres."""
        return self.segment.longueur

    def position_a(self, distance: float, decalage: float) -> Position:
        """Calcule la position atteinte après une distance parcourue sur l'arc.

        Args:
            distance (float): distance depuis le début de l'arc, en mètres.
            decalage (float): écart latéral en mètres, positif vers la droite du sens de marche.

        Returns:
            Position: la position correspondante.
        """
        angle = math.radians(self.segment.depart.angle) + distance / self.rayon
        # En tournant dans le sens inverse des aiguilles d'une montre, la droite du
        # sens de marche est l'extérieur de l'anneau.
        distance_au_centre = self.rayon + decalage
        return Position(distance_au_centre * math.cos(angle), distance_au_centre * math.sin(angle))


Troncon = TronconDroit | TronconArc


class Trajectoire:
    """Chemin complet d'un usager, découpé en tronçons parcourus l'un après l'autre.

    Les méthodes repèrent l'usager par son avancement : la distance qu'il a
    parcourue depuis son point de départ, en mètres.
    """

    def __init__(self, troncons: list[Troncon]) -> None:
        """Crée une trajectoire.

        Args:
            troncons (list[Troncon]): tronçons dans l'ordre de parcours, en commençant par l'approche.

        Raises:
            ValueError: si la liste est vide ou ne commence pas par une approche.
        """
        if not troncons or troncons[0].etape is not Etape.APPROCHE:
            raise ValueError("une trajectoire commence par une approche")
        self.__troncons = list(troncons)

    @classmethod
    def pour_vehicule(cls, rond_point: RondPoint, entree: str, sortie: str) -> Trajectoire:
        """Construit la trajectoire d'un véhicule : approche, anneau, puis sortie.

        Args:
            rond_point (RondPoint): rond-point traversé.
            entree (str): nom de la branche d'entrée.
            sortie (str): nom de la branche de sortie.

        Returns:
            Trajectoire: la trajectoire du véhicule.

        Raises:
            BrancheInconnueError: si l'une des deux branches n'existe pas.
        """
        branche_entree = rond_point.branche(entree)
        branche_sortie = rond_point.branche(sortie)
        bord_anneau = rond_point.rayon
        extremite = rond_point.rayon + LONGUEUR_BRANCHE
        troncon_approche = TronconDroit(
            Etape.APPROCHE, branche_entree.point(extremite), branche_entree.point(bord_anneau)
        )
        troncons_anneau = [
            TronconArc(segment, rond_point.rayon) for segment in rond_point.segments_entre(entree, sortie)
        ]
        troncon_sortie = TronconDroit(Etape.SORTIE, branche_sortie.point(bord_anneau), branche_sortie.point(extremite))
        return cls([troncon_approche, *troncons_anneau, troncon_sortie])

    @property
    def troncons(self) -> list[Troncon]:
        """list[Troncon]: tronçons dans l'ordre de parcours (copie)."""
        return list(self.__troncons)

    @property
    def longueur(self) -> float:
        """float: longueur totale, en mètres."""
        return sum(troncon.longueur for troncon in self.__troncons)

    @property
    def longueur_approche(self) -> float:
        """float: distance jusqu'à la ligne d'entrée, où s'arrête un usager qui doit attendre."""
        longueur = 0.0
        for troncon in self.__troncons:
            if troncon.etape is not Etape.APPROCHE:
                break
            longueur += troncon.longueur
        return longueur

    @property
    def segments(self) -> list[Segment]:
        """list[Segment]: segments de l'anneau parcourus, dans l'ordre de passage."""
        return [troncon.segment for troncon in self.__troncons if troncon.segment is not None]

    def position_a(self, avancement: float, decalage: float = 0.0) -> Position:
        """Calcule la position d'un usager à partir de son avancement.

        Args:
            avancement (float): distance parcourue depuis le départ, en mètres.
                Au-delà de la longueur totale, l'usager reste au bout de sa trajectoire.
            decalage (float): écart latéral en mètres, positif vers la droite du sens de marche.

        Returns:
            Position: la position de l'usager.

        Raises:
            ValueError: si l'avancement est négatif ou n'est pas un nombre fini.
        """
        troncon, distance = self.__troncon_a(avancement)
        return troncon.position_a(distance, decalage)

    def etape_a(self, avancement: float) -> Etape:
        """Donne l'étape où se trouve un usager.

        Args:
            avancement (float): distance parcourue depuis le départ, en mètres.

        Returns:
            Etape: l'étape correspondante.

        Raises:
            ValueError: si l'avancement est négatif ou n'est pas un nombre fini.
        """
        troncon, _ = self.__troncon_a(avancement)
        return troncon.etape

    def segment_a(self, avancement: float) -> Segment | None:
        """Donne le segment de l'anneau où se trouve un usager.

        Args:
            avancement (float): distance parcourue depuis le départ, en mètres.

        Returns:
            Segment | None: le segment occupé, None si l'usager n'est pas sur l'anneau.

        Raises:
            ValueError: si l'avancement est négatif ou n'est pas un nombre fini.
        """
        troncon, _ = self.__troncon_a(avancement)
        return troncon.segment

    def passe_par(self, segment: Segment) -> bool:
        """Indique si la trajectoire emprunte un segment de l'anneau.

        Args:
            segment (Segment): segment du rond-point.

        Returns:
            bool: True si le segment fait partie du trajet.
        """
        return segment in self.segments

    def __troncon_a(self, avancement: float) -> tuple[Troncon, float]:
        """Trouve le tronçon où se trouve un usager et la distance parcourue sur ce tronçon."""
        if not math.isfinite(avancement) or avancement < 0:
            raise ValueError(f"l'avancement doit être un nombre positif ou nul (reçu : {avancement})")
        reste = avancement
        for troncon in self.__troncons:
            # Un point pile à la jonction de deux tronçons appartient au premier :
            # un usager arrêté sur la ligne d'entrée est encore en approche.
            if reste <= troncon.longueur:
                return troncon, reste
            reste -= troncon.longueur
        dernier = self.__troncons[-1]
        return dernier, dernier.longueur
