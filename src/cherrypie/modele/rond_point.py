"""Géométrie du rond-point : branches, anneau à deux voies et segments.

Repère : origine au centre de l'anneau, x vers l'est, y vers le nord, distances
en mètres. Les angles sont en degrés, comptés depuis l'est dans le sens inverse
des aiguilles d'une montre, qui est aussi le sens de circulation (comme en France).
La configuration donne, elle, le cap de chaque branche, compté depuis le nord dans
le sens des aiguilles d'une montre, comme sur une carte.
"""

from __future__ import annotations

import math

from cherrypie.commun.config import NOMBRE_MIN_BRANCHES, TOUR_COMPLET, Configuration, ParametresBranche
from cherrypie.commun.erreurs import BrancheInconnueError
from cherrypie.modele.position import Position

# Un cap compté depuis le nord correspond à cet angle mathématique : 90° moins le cap.
ANGLE_DU_NORD = 90.0


class Branche:
    """Route qui arrive sur le rond-point et en repart, en double chaussée.

    En arrivant vers l'anneau, la chaussée d'entrée est à droite du terre-plein et la
    chaussée de sortie à gauche. Chaque chaussée n'a qu'une voie.
    """

    def __init__(self, parametres: ParametresBranche, capacite: int, largeur_chaussee: float) -> None:
        """Crée une branche.

        Args:
            parametres (ParametresBranche): nom, libellé, cap, terre-plein et passage piéton.
            capacite (int): nombre d'usagers à partir duquel la branche est considérée pleine.
            largeur_chaussee (float): largeur de la chaussée de chaque sens, en mètres.

        Raises:
            ValueError: si le nom est vide, si la capacité est inférieure à 1, ou si une
                largeur ou la distance du passage piéton n'est pas positive.
        """
        if not isinstance(parametres.nom, str) or not parametres.nom:
            raise ValueError(f"le nom d'une branche doit être un texte non vide (reçu : {parametres.nom!r})")
        if capacite < 1:
            raise ValueError(f"la capacité d'une branche doit valoir au moins 1 (reçu : {capacite})")
        for description, valeur in (
            ("le terre-plein", parametres.terre_plein),
            ("la distance du passage piéton", parametres.passage_pieton),
            ("la chaussée", largeur_chaussee),
        ):
            if not valeur > 0:
                raise ValueError(f"{description} doit avoir une dimension positive (reçu : {valeur})")
        self.__nom = parametres.nom
        self.__libelle = parametres.libelle
        self.__cap = parametres.cap % TOUR_COMPLET
        self.__capacite = capacite
        self.__terre_plein = parametres.terre_plein
        self.__passage_pieton = parametres.passage_pieton
        self.__largeur_chaussee = largeur_chaussee

    @property
    def nom(self) -> str:
        """str: identifiant de la branche, utilisé dans le protocole (ex. "nations_nord")."""
        return self.__nom

    @property
    def libelle(self) -> str:
        """str: nom de rue affiché par l'IHM."""
        return self.__libelle

    @property
    def cap(self) -> float:
        """float: direction de la branche vue du centre, en degrés depuis le nord, entre 0 et 360."""
        return self.__cap

    @property
    def angle(self) -> float:
        """float: direction de la branche vue du centre, en degrés dans le repère du rond-point, entre 0 et 360."""
        return (ANGLE_DU_NORD - self.__cap) % TOUR_COMPLET

    @property
    def capacite(self) -> int:
        """int: nombre d'usagers à partir duquel la branche est considérée pleine."""
        return self.__capacite

    @property
    def terre_plein(self) -> float:
        """float: largeur du terre-plein entre les deux chaussées, en mètres."""
        return self.__terre_plein

    @property
    def passage_pieton(self) -> float:
        """float: distance entre le bord de l'anneau et le passage piéton, en mètres."""
        return self.__passage_pieton

    @property
    def largeur_chaussee(self) -> float:
        """float: largeur de la chaussée de chaque sens, en mètres."""
        return self.__largeur_chaussee

    @property
    def decalage_voie(self) -> float:
        """float: écart entre l'axe de la branche et le milieu de chaque chaussée, en mètres."""
        return self.__terre_plein / 2 + self.__largeur_chaussee / 2

    @property
    def demi_largeur(self) -> float:
        """float: écart entre l'axe de la branche et le bord extérieur de chaque chaussée, en mètres."""
        return self.__terre_plein / 2 + self.__largeur_chaussee

    def point(self, distance_au_centre: float, decalage: float = 0.0) -> Position:
        """Calcule un point de la branche.

        Args:
            distance_au_centre (float): distance depuis le centre de l'anneau, mesurée le long de l'axe, en mètres.
            decalage (float): écart par rapport à l'axe de la branche, en mètres,
                positif vers la droite d'un usager qui roule vers l'anneau (côté entrée).

        Returns:
            Position: le point demandé.
        """
        angle = math.radians(self.angle)
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
            longueur (float): longueur de l'arc sur l'axe de l'anneau, en mètres.

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
        """float: longueur de l'arc sur l'axe de l'anneau, en mètres."""
        return self.__longueur

    @property
    def ouverture(self) -> float:
        """float: angle entre la branche de départ et celle d'arrivée, dans le sens de circulation, en degrés."""
        return (self.__arrivee.angle - self.__depart.angle) % TOUR_COMPLET

    @property
    def nom(self) -> str:
        """str: nom du segment, formé de ses deux branches (ex. "jean_de_la_bruyere-nations_nord")."""
        return f"{self.__depart.nom}-{self.__arrivee.nom}"


class RondPoint:
    """Anneau à deux voies et branches du rond-point.

    Le rond-point crée lui-même ses branches et ses segments, qui n'existent pas sans
    lui. Les deux voies de l'anneau, intérieure et extérieure, ont la même largeur et
    sont séparées par l'axe de l'anneau. Les segments vont d'une branche à la suivante
    dans le sens de circulation, quel que soit l'ordre des branches dans la configuration.
    """

    def __init__(
        self,
        branches: list[ParametresBranche],
        rayon: float,
        largeur_voie_anneau: float,
        largeur_chaussee: float,
        longueur_branche: float,
        capacite_par_branche: int,
    ) -> None:
        """Construit le rond-point et découpe son anneau en segments.

        Args:
            branches (list[ParametresBranche]): description de chaque branche.
            rayon (float): rayon de l'axe de l'anneau, entre ses deux voies, en mètres.
            largeur_voie_anneau (float): largeur de chaque voie de l'anneau, en mètres.
            largeur_chaussee (float): largeur de la chaussée de chaque sens d'une branche, en mètres.
            longueur_branche (float): longueur de chaque branche depuis le bord de l'anneau, en mètres.
            capacite_par_branche (int): capacité de chaque branche.

        Raises:
            ValueError: s'il y a moins de NOMBRE_MIN_BRANCHES branches, des noms ou des caps
                en double, ou des dimensions incohérentes.
        """
        if len(branches) < NOMBRE_MIN_BRANCHES:
            raise ValueError(f"un rond-point a au moins {NOMBRE_MIN_BRANCHES} branches (reçu : {len(branches)})")
        if len({branche.nom for branche in branches}) != len(branches):
            raise ValueError("deux branches portent le même nom")
        if len({branche.cap % TOUR_COMPLET for branche in branches}) != len(branches):
            raise ValueError("deux branches ont le même cap")
        if not rayon > 0 or not longueur_branche > 0:
            raise ValueError(
                f"le rayon et la longueur des branches doivent être positifs (reçu : {rayon}, {longueur_branche})"
            )
        if not 0 < largeur_voie_anneau < rayon:
            raise ValueError(
                f"une voie de l'anneau doit être moins large que le rayon (reçu : {largeur_voie_anneau})"
            )
        self.__rayon = rayon
        self.__largeur_voie_anneau = largeur_voie_anneau
        self.__longueur_branche = longueur_branche
        self.__branches = [Branche(parametres, capacite_par_branche, largeur_chaussee) for parametres in branches]
        # On circule dans le sens des angles croissants : chaque segment va d'une branche
        # à la suivante dans cet ordre, la dernière rejoignant la première.
        dans_le_sens = sorted(self.__branches, key=lambda branche: branche.angle)
        self.__segments = []
        for rang, branche in enumerate(dans_le_sens):
            suivante = dans_le_sens[(rang + 1) % len(dans_le_sens)]
            ouverture = math.radians((suivante.angle - branche.angle) % TOUR_COMPLET)
            self.__segments.append(Segment(branche, suivante, rayon * ouverture))

    @classmethod
    def depuis_config(cls, config: Configuration) -> RondPoint:
        """Construit le rond-point décrit dans la configuration.

        Args:
            config (Configuration): configuration chargée depuis config.ini.

        Returns:
            RondPoint: le rond-point correspondant.
        """
        return cls(
            config.branches,
            config.rayon,
            config.largeur_voie_anneau,
            config.largeur_chaussee,
            config.longueur_branche,
            config.capacite_par_branche,
        )

    @property
    def rayon(self) -> float:
        """float: rayon de l'axe de l'anneau, entre ses deux voies, en mètres."""
        return self.__rayon

    @property
    def largeur_voie_anneau(self) -> float:
        """float: largeur de chaque voie de l'anneau, en mètres."""
        return self.__largeur_voie_anneau

    @property
    def rayon_voie_interieure(self) -> float:
        """float: rayon du milieu de la voie intérieure, en mètres."""
        return self.__rayon - self.__largeur_voie_anneau / 2

    @property
    def rayon_voie_exterieure(self) -> float:
        """float: rayon du milieu de la voie extérieure, en mètres."""
        return self.__rayon + self.__largeur_voie_anneau / 2

    @property
    def rayon_ilot(self) -> float:
        """float: rayon de l'îlot central, bord intérieur de l'anneau, en mètres."""
        return self.__rayon - self.__largeur_voie_anneau

    @property
    def rayon_bord(self) -> float:
        """float: rayon du bord extérieur de l'anneau, où commencent les branches, en mètres."""
        return self.__rayon + self.__largeur_voie_anneau

    @property
    def longueur_branche(self) -> float:
        """float: longueur de chaque branche depuis le bord de l'anneau, en mètres."""
        return self.__longueur_branche

    @property
    def branches(self) -> list[Branche]:
        """list[Branche]: branches, dans l'ordre de la configuration (copie)."""
        return list(self.__branches)

    @property
    def segments(self) -> list[Segment]:
        """list[Segment]: segments de l'anneau, dans le sens de circulation (copie)."""
        return list(self.__segments)

    def branche(self, nom: str) -> Branche:
        """Retrouve une branche par son nom.

        Args:
            nom (str): identifiant de la branche (ex. "nations_nord").

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

    def ecart_raccord(self, branche: Branche) -> float:
        """Écart angulaire entre l'axe d'une branche et le milieu de ses chaussées au bord de l'anneau.

        Une chaussée d'entrée rejoint l'anneau un peu après l'axe de sa branche, dans le
        sens de circulation, et la chaussée de sortie le quitte d'autant avant.

        Args:
            branche (Branche): branche du rond-point.

        Returns:
            float: écart en degrés.
        """
        return math.degrees(math.atan2(branche.decalage_voie, self.rayon_bord))

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
