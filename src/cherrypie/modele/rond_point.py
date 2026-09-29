"""Géométrie du rond-point : branches et segments de l'anneau.

Repère : origine au centre de l'anneau, x vers l'est, y vers le nord, distances
en mètres. Les angles sont en degrés, comptés depuis l'est dans le sens inverse
des aiguilles d'une montre, qui est aussi le sens de circulation (comme en France).
"""

from __future__ import annotations

import math

from cherrypie.commun.config import NOMBRE_MIN_BRANCHES, Configuration
from cherrypie.commun.erreurs import BrancheInconnueError
from cherrypie.modele.position import Position

# La première branche de la configuration est placée au nord et les suivantes
# dans le sens des aiguilles d'une montre : N, E, S et O tombent à leur place.
ANGLE_PREMIERE_BRANCHE = 90.0


class Branche:
    """Route qui arrive sur le rond-point et en repart."""

    def __init__(self, nom: str, angle: float, capacite: int) -> None:
        """Crée une branche.

        Args:
            nom (str): nom de la branche (ex. "N").
            angle (float): direction de la branche vue du centre, en degrés.
            capacite (int): nombre d'usagers à partir duquel la branche est considérée pleine.

        Raises:
            ValueError: si le nom est vide ou si la capacité est inférieure à 1.
        """
        if not isinstance(nom, str) or not nom:
            raise ValueError(f"le nom d'une branche doit être un texte non vide (reçu : {nom!r})")
        if capacite < 1:
            raise ValueError(f"la capacité d'une branche doit valoir au moins 1 (reçu : {capacite})")
        self.__nom = nom
        self.__angle = angle % 360
        self.__capacite = capacite

    @property
    def nom(self) -> str:
        """str: nom de la branche."""
        return self.__nom

    @property
    def angle(self) -> float:
        """float: direction de la branche vue du centre, en degrés, entre 0 et 360."""
        return self.__angle

    @property
    def capacite(self) -> int:
        """int: nombre d'usagers à partir duquel la branche est considérée pleine."""
        return self.__capacite

    def point(self, distance_au_centre: float, decalage: float = 0.0) -> Position:
        """Calcule un point de la branche.

        Args:
            distance_au_centre (float): distance depuis le centre de l'anneau, en mètres.
            decalage (float): écart par rapport à l'axe de la branche, en mètres,
                positif vers la droite d'un usager qui roule vers l'anneau.

        Returns:
            Position: le point demandé.
        """
        angle = math.radians(self.__angle)
        # Pour un usager qui roule vers le centre, sa droite est le vecteur (-sin, cos).
        return Position(
            distance_au_centre * math.cos(angle) - decalage * math.sin(angle),
            distance_au_centre * math.sin(angle) + decalage * math.cos(angle),
        )


class Segment:
    """Portion de l'anneau entre deux branches consécutives, dans le sens de circulation."""

    def __init__(self, depart: Branche, arrivee: Branche, longueur: float) -> None:
        """Crée un segment.

        Args:
            depart (Branche): branche où commence le segment.
            arrivee (Branche): branche suivante, dans le sens de circulation.
            longueur (float): longueur de l'arc, en mètres.

        Raises:
            ValueError: si le départ et l'arrivée sont la même branche ou si la longueur n'est pas positive.
        """
        if depart is arrivee:
            raise ValueError("un segment relie deux branches différentes")
        if not longueur > 0:
            raise ValueError(f"la longueur d'un segment doit être positive (reçu : {longueur})")
        self.__depart = depart
        self.__arrivee = arrivee
        self.__longueur = longueur

    @property
    def depart(self) -> Branche:
        """Branche: branche où commence le segment."""
        return self.__depart

    @property
    def arrivee(self) -> Branche:
        """Branche: branche où finit le segment."""
        return self.__arrivee

    @property
    def longueur(self) -> float:
        """float: longueur de l'arc, en mètres."""
        return self.__longueur

    @property
    def nom(self) -> str:
        """str: nom du segment, formé de ses deux branches (ex. "N-O")."""
        return f"{self.__depart.nom}-{self.__arrivee.nom}"


class RondPoint:
    """Anneau et branches du rond-point.

    Le rond-point crée lui-même ses branches et ses segments, qui n'existent pas
    sans lui. Les branches sont réparties régulièrement autour de l'anneau.
    """

    def __init__(self, noms_branches: list[str], rayon: float, capacite_par_branche: int) -> None:
        """Construit le rond-point et découpe son anneau en segments.

        Args:
            noms_branches (list[str]): noms des branches, dans le sens des aiguilles
                d'une montre en partant du nord.
            rayon (float): rayon de l'anneau, en mètres.
            capacite_par_branche (int): capacité de chaque branche.

        Raises:
            ValueError: s'il y a moins de NOMBRE_MIN_BRANCHES branches, des noms en
                double ou un rayon qui n'est pas positif.
        """
        if len(noms_branches) < NOMBRE_MIN_BRANCHES:
            raise ValueError(f"un rond-point a au moins {NOMBRE_MIN_BRANCHES} branches (reçu : {len(noms_branches)})")
        if len(set(noms_branches)) != len(noms_branches):
            raise ValueError("deux branches portent le même nom")
        if not rayon > 0:
            raise ValueError(f"le rayon doit être positif (reçu : {rayon})")
        ecart = 360 / len(noms_branches)
        self.__rayon = rayon
        self.__branches = [
            Branche(nom, ANGLE_PREMIERE_BRANCHE - rang * ecart, capacite_par_branche)
            for rang, nom in enumerate(noms_branches)
        ]
        # Les branches sont rangées dans le sens des aiguilles d'une montre et l'on
        # circule dans l'autre sens : chaque segment va d'une branche à la précédente.
        longueur_segment = rayon * math.radians(ecart)
        self.__segments = [
            Segment(branche, self.__branches[rang - 1], longueur_segment)
            for rang, branche in enumerate(self.__branches)
        ]

    @classmethod
    def depuis_config(cls, config: Configuration) -> RondPoint:
        """Construit le rond-point décrit dans la configuration.

        Args:
            config (Configuration): configuration chargée depuis config.ini.

        Returns:
            RondPoint: le rond-point correspondant.
        """
        return cls(config.branches, config.rayon, config.capacite_par_branche)

    @property
    def rayon(self) -> float:
        """float: rayon de l'anneau, en mètres."""
        return self.__rayon

    @property
    def branches(self) -> list[Branche]:
        """list[Branche]: branches, dans l'ordre de la configuration (copie)."""
        return list(self.__branches)

    @property
    def segments(self) -> list[Segment]:
        """list[Segment]: segments de l'anneau, un par branche de départ (copie)."""
        return list(self.__segments)

    def branche(self, nom: str) -> Branche:
        """Retrouve une branche par son nom.

        Args:
            nom (str): nom de la branche (ex. "N").

        Returns:
            Branche: la branche demandée.

        Raises:
            BrancheInconnueError: si aucune branche ne porte ce nom.
        """
        for branche in self.__branches:
            if branche.nom == nom:
                return branche
        noms = ", ".join(branche.nom for branche in self.__branches)
        raise BrancheInconnueError(f"branche inconnue : {nom!r} (branches du rond-point : {noms})")

    def segments_entre(self, entree: str, sortie: str) -> list[Segment]:
        """Liste les segments parcourus sur l'anneau pour aller d'une branche à une autre.

        Si l'entrée et la sortie sont la même branche, l'usager fait le tour complet.

        Args:
            entree (str): branche par laquelle l'usager entre sur l'anneau.
            sortie (str): branche par laquelle il le quitte.

        Returns:
            list[Segment]: segments dans l'ordre de passage.

        Raises:
            BrancheInconnueError: si l'une des deux branches n'existe pas.
        """
        branche_courante = self.branche(entree)
        branche_sortie = self.branche(sortie)
        parcours = []
        while True:
            segment = self.__segment_partant_de(branche_courante)
            parcours.append(segment)
            branche_courante = segment.arrivee
            if branche_courante is branche_sortie:
                return parcours

    def __segment_partant_de(self, branche: Branche) -> Segment:
        """Renvoie le segment de l'anneau qui commence à une branche."""
        return next(segment for segment in self.__segments if segment.depart is branche)
