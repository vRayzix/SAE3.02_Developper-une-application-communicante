"""Trajectoires des usagers : suite de tronçons droits et d'arcs de l'anneau.

Un véhicule passe par trois étapes : l'approche sur la chaussée d'entrée de sa branche,
l'anneau, puis la sortie sur la chaussée de sortie de sa branche de sortie. Sur l'anneau,
il rejoint sa voie, la suit, change de voie s'il le faut, puis rejoint la chaussée de
sortie. Un piéton ne prend pas l'anneau : il rejoint le passage piéton de sa branche, la
traverse d'un trottoir à l'autre (deux chaussées et le terre-plein), puis s'éloigne.
L'avancement d'un usager est la distance qu'il a parcourue depuis son départ.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from cherrypie.commun.config import TOUR_COMPLET
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import ANGLE_DU_NORD, Branche, RondPoint, Segment

# Trottoir parcouru par un piéton avant et après sa traversée, en mètres.
LONGUEUR_TROTTOIR = 4.0
# Distances parcourues sur l'anneau pour rejoindre sa voie en arrivant de la chaussée
# d'entrée, pour passer d'une voie à l'autre, et pour rejoindre la chaussée de sortie.
LONGUEUR_INSERTION = 8.0
LONGUEUR_CHANGEMENT_VOIE = 10.0
LONGUEUR_DEGAGEMENT = 8.0
# Sur un parcours court, chacune de ces transitions n'en occupe pas plus que cette part.
PART_MAX_TRANSITION = 0.3
# Une transition est découpée en morceaux d'au plus cet angle, en degrés : l'usager y
# avance alors à vitesse presque constante, alors que sa distance au centre change.
ANGLE_MAX_TRANSITION = 3.0
# Un usager rangé sur sa chaussée garde cette distance entre son milieu et le bord, en
# mètres. Elle est un peu plus courte que la demi-largeur d'une voiture : il serre le bord
# jusqu'à y poser les roues, et le VP le double avec un espace qu'on voit à l'écran.
MARGE_BORD_CHAUSSEE = 0.6


def cap_de_la_direction(dx: float, dy: float) -> float:
    """Convertit une direction du repère du rond-point en cap.

    Args:
        dx (float): composante vers l'est.
        dy (float): composante vers le nord.

    Returns:
        float: cap en degrés depuis le nord, dans le sens des aiguilles d'une montre, entre 0 et 360.
    """
    return (ANGLE_DU_NORD - math.degrees(math.atan2(dy, dx))) % TOUR_COMPLET


class Etape(Enum):
    """Partie de sa trajectoire où se trouve un usager."""

    APPROCHE = "approche"
    ANNEAU = "anneau"
    TRAVERSEE = "traversee"
    SORTIE = "sortie"


@dataclass(frozen=True)
class TronconDroit:
    """Tronçon parcouru en ligne droite, sur une branche.

    Attributes:
        etape (Etape): étape de la trajectoire à laquelle appartient le tronçon.
        depart (Position): point de départ.
        arrivee (Position): point d'arrivée.
        place_a_droite (float): écart que l'usager peut prendre sur sa droite pour se ranger, en mètres.
    """

    etape: Etape
    depart: Position
    arrivee: Position
    place_a_droite: float = 0.0

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

    def cap_a(self, distance: float) -> float:
        """Donne le cap suivi sur le tronçon, le même tout du long.

        Args:
            distance (float): distance depuis le début du tronçon, en mètres.

        Returns:
            float: cap en degrés depuis le nord.
        """
        return cap_de_la_direction(self.arrivee.x - self.depart.x, self.arrivee.y - self.depart.y)


@dataclass(frozen=True)
class TronconArc:
    """Morceau de trajectoire sur l'anneau, à l'intérieur d'un segment.

    L'angle et la distance au centre varient régulièrement du début à la fin du morceau.
    À distance constante, l'usager suit une voie ; sinon, il passe d'une voie à l'autre, ou
    d'une chaussée de branche à une voie de l'anneau.

    Attributes:
        segment (Segment): segment de l'anneau où se trouve le morceau.
        angle_debut (float): angle du début, en degrés.
        angle_fin (float): angle de la fin, en degrés, plus grand que celui du début
            (on tourne dans le sens des angles croissants).
        rayon_debut (float): distance au centre au début, en mètres.
        rayon_fin (float): distance au centre à la fin, en mètres.
        place_a_droite (float): écart que l'usager peut prendre vers l'extérieur pour se ranger, en mètres.
    """

    segment: Segment
    angle_debut: float
    angle_fin: float
    rayon_debut: float
    rayon_fin: float
    place_a_droite: float = 0.0

    def __post_init__(self) -> None:
        """Refuse un morceau qui ne tourne pas dans le sens de circulation.

        Raises:
            ValueError: si l'angle de fin n'est pas plus grand que celui du début.
        """
        if not self.angle_fin > self.angle_debut:
            raise ValueError("un arc de l'anneau se parcourt dans le sens des angles croissants")

    @property
    def etape(self) -> Etape:
        """Etape: toujours ANNEAU."""
        return Etape.ANNEAU

    @property
    def longueur(self) -> float:
        """float: longueur du morceau, en mètres, en comptant le déplacement vers le centre ou l'extérieur."""
        rayon_moyen = (self.rayon_debut + self.rayon_fin) / 2
        ouverture = math.radians(self.angle_fin - self.angle_debut)
        return math.hypot(rayon_moyen * ouverture, self.rayon_fin - self.rayon_debut)

    def position_a(self, distance: float, decalage: float) -> Position:
        """Calcule la position atteinte après une distance parcourue sur le morceau.

        Args:
            distance (float): distance depuis le début du morceau, en mètres.
            decalage (float): écart latéral en mètres, positif vers la droite du sens de marche.

        Returns:
            Position: la position correspondante.
        """
        part = distance / self.longueur
        angle = math.radians(self.angle_debut + part * (self.angle_fin - self.angle_debut))
        # En tournant dans le sens inverse des aiguilles d'une montre, la droite du
        # sens de marche est l'extérieur de l'anneau.
        distance_au_centre = self.rayon_debut + part * (self.rayon_fin - self.rayon_debut) + decalage
        return Position(distance_au_centre * math.cos(angle), distance_au_centre * math.sin(angle))

    def cap_a(self, distance: float) -> float:
        """Donne le cap suivi après une distance parcourue sur le morceau.

        Args:
            distance (float): distance depuis le début du morceau, en mètres.

        Returns:
            float: cap en degrés depuis le nord, tangent au morceau.
        """
        part = distance / self.longueur
        angle = math.radians(self.angle_debut + part * (self.angle_fin - self.angle_debut))
        rayon = self.rayon_debut + part * (self.rayon_fin - self.rayon_debut)
        # Dérivée de la position : la variation de distance au centre, puis la rotation.
        rotation = math.radians(self.angle_fin - self.angle_debut)
        ecartement = self.rayon_fin - self.rayon_debut
        dx = ecartement * math.cos(angle) - rayon * rotation * math.sin(angle)
        dy = ecartement * math.sin(angle) + rayon * rotation * math.cos(angle)
        return cap_de_la_direction(dx, dy)


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
    def pour_vehicule(cls, rond_point: RondPoint, entree: str, sortie: str, prioritaire: bool = False) -> Trajectoire:
        """Construit la trajectoire d'un véhicule : approche, anneau, puis sortie.

        Sur l'anneau, un véhicule qui sort à la première sortie roule sur la voie
        extérieure. Les autres roulent sur la voie intérieure et se rabattent sur la voie
        extérieure au début du segment qui mène à leur sortie. Un véhicule prioritaire
        reste sur la voie intérieure de bout en bout.

        Args:
            rond_point (RondPoint): rond-point traversé.
            entree (str): nom de la branche d'entrée.
            sortie (str): nom de la branche de sortie.
            prioritaire (bool): True pour un véhicule prioritaire.

        Returns:
            Trajectoire: la trajectoire du véhicule.

        Raises:
            BrancheInconnueError: si l'une des deux branches n'existe pas.
        """
        branche_entree = rond_point.branche(entree)
        branche_sortie = rond_point.branche(sortie)
        bord = rond_point.rayon_bord
        extremite = bord + rond_point.longueur_branche
        voie_entree = branche_entree.decalage_voie
        voie_sortie = -branche_sortie.decalage_voie
        approche = TronconDroit(
            Etape.APPROCHE,
            branche_entree.point(extremite, voie_entree),
            branche_entree.point(bord, voie_entree),
            cls.__place_sur_la_chaussee(branche_entree),
        )
        sortie_branche = TronconDroit(
            Etape.SORTIE,
            branche_sortie.point(bord, voie_sortie),
            branche_sortie.point(extremite, voie_sortie),
            cls.__place_sur_la_chaussee(branche_sortie),
        )
        return cls([approche, *cls.__arcs(rond_point, branche_entree, branche_sortie, prioritaire), sortie_branche])

    @classmethod
    def pour_pieton(cls, rond_point: RondPoint, branche: str) -> Trajectoire:
        """Construit la trajectoire d'un piéton qui traverse une branche sur son passage piéton.

        Le piéton part du trottoir côté chaussée d'entrée, s'arrête au bord de la
        chaussée s'il doit attendre, traverse les deux chaussées et le terre-plein, puis
        s'éloigne sur le trottoir d'en face.

        Args:
            rond_point (RondPoint): rond-point traversé.
            branche (str): nom de la branche traversée.

        Returns:
            Trajectoire: la trajectoire du piéton.

        Raises:
            BrancheInconnueError: si la branche n'existe pas.
        """
        branche_traversee = rond_point.branche(branche)
        distance = rond_point.rayon_bord + branche_traversee.passage_pieton
        bord = branche_traversee.demi_largeur
        depart = branche_traversee.point(distance, bord + LONGUEUR_TROTTOIR)
        bord_entree = branche_traversee.point(distance, bord)
        bord_sortie = branche_traversee.point(distance, -bord)
        arrivee = branche_traversee.point(distance, -bord - LONGUEUR_TROTTOIR)
        return cls([
            TronconDroit(Etape.APPROCHE, depart, bord_entree),
            TronconDroit(Etape.TRAVERSEE, bord_entree, bord_sortie),
            TronconDroit(Etape.SORTIE, bord_sortie, arrivee),
        ])

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
        """float: distance jusqu'à la ligne d'entrée, au bout de l'approche, où s'arrête un usager qui attend.

        Pour un véhicule, la ligne est au bord de l'anneau ; pour un piéton, au bord de la chaussée.
        """
        longueur = 0.0
        for troncon in self.__troncons:
            if troncon.etape is not Etape.APPROCHE:
                break
            longueur += troncon.longueur
        return longueur

    @property
    def segments(self) -> list[Segment]:
        """list[Segment]: segments de l'anneau parcourus, dans l'ordre de passage, chacun une fois."""
        segments: list[Segment] = []
        for troncon in self.__troncons:
            if troncon.segment is not None and (not segments or segments[-1] is not troncon.segment):
                segments.append(troncon.segment)
        return segments

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

    def cap_a(self, avancement: float) -> float:
        """Donne le cap d'un usager, la direction dans laquelle il avance.

        Args:
            avancement (float): distance parcourue depuis le départ, en mètres.

        Returns:
            float: cap en degrés depuis le nord, dans le sens des aiguilles d'une montre.

        Raises:
            ValueError: si l'avancement est négatif ou n'est pas un nombre fini.
        """
        troncon, distance = self.__troncon_a(avancement)
        return troncon.cap_a(distance)

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

    def place_a_droite_a(self, avancement: float) -> float:
        """Donne l'écart qu'un usager peut prendre sur sa droite pour se ranger, là où il se trouve.

        Sur une branche, il serre le bord de sa chaussée. Sur la voie intérieure de
        l'anneau, il passe sur la voie extérieure ; sur la voie extérieure, il y est déjà.

        Args:
            avancement (float): distance parcourue depuis le départ, en mètres.

        Returns:
            float: écart en mètres, positif ou nul.

        Raises:
            ValueError: si l'avancement est négatif ou n'est pas un nombre fini.
        """
        troncon, _ = self.__troncon_a(avancement)
        return troncon.place_a_droite

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
            # Un point pile à la jonction de deux tronçons appartient au premier : un
            # usager arrêté sur la ligne d'entrée est encore en approche.
            if reste <= troncon.longueur:
                return troncon, reste
            reste -= troncon.longueur
        dernier = self.__troncons[-1]
        return dernier, dernier.longueur

    @staticmethod
    def __place_sur_la_chaussee(branche: Branche) -> float:
        """Écart possible vers le bord de la chaussée pour un usager qui se range."""
        return max(0.0, branche.largeur_chaussee / 2 - MARGE_BORD_CHAUSSEE)

    @staticmethod
    def __arcs(rond_point: RondPoint, entree: Branche, sortie: Branche, prioritaire: bool) -> list[TronconArc]:
        """Découpe le passage sur l'anneau en morceaux, chacun à l'intérieur d'un segment.

        Le chemin est décrit par des points (angle, distance au centre) reliés en ligne
        droite dans ce repère : raccord depuis la chaussée d'entrée, voie suivie,
        changement de voie éventuel, raccord vers la chaussée de sortie.
        """
        segments = rond_point.segments_entre(entree.nom, sortie.nom)
        # Les angles s'accumulent d'un segment à l'autre, sans revenir à 0 après 360°.
        limites = [entree.angle]
        for segment in segments:
            limites.append(limites[-1] + segment.ouverture)
        debut = limites[0] + rond_point.ecart_raccord(entree)
        fin = limites[-1] - rond_point.ecart_raccord(sortie)
        voies = [
            rond_point.rayon_voie_interieure
            if prioritaire or rang < len(segments) - 1
            else rond_point.rayon_voie_exterieure
            for rang in range(len(segments))
        ]

        def ouverture(longueur: float, rayon: float) -> float:
            return min(math.degrees(longueur / rayon), PART_MAX_TRANSITION * (fin - debut))

        points = [
            (debut, math.hypot(rond_point.rayon_bord, entree.decalage_voie)),
            (debut + ouverture(LONGUEUR_INSERTION, voies[0]), voies[0]),
        ]
        for rang in range(1, len(segments)):
            if voies[rang] != voies[rang - 1]:
                depart_changement = max(limites[rang], points[-1][0])
                points.append((depart_changement, voies[rang - 1]))
                points.append((depart_changement + ouverture(LONGUEUR_CHANGEMENT_VOIE, voies[rang]), voies[rang]))
        points.append((fin - ouverture(LONGUEUR_DEGAGEMENT, voies[-1]), voies[-1]))
        points.append((fin, math.hypot(rond_point.rayon_bord, sortie.decalage_voie)))
        # Sur un parcours très court, les transitions se chevauchent : on ne garde que les
        # points qui avancent dans le sens de circulation.
        chemin = [points[0]]
        for angle, rayon in points[1:-1]:
            if chemin[-1][0] < angle < points[-1][0]:
                chemin.append((angle, rayon))
        chemin.append(points[-1])
        return Trajectoire.__decouper(chemin, limites, segments, rond_point.rayon_voie_exterieure)

    @staticmethod
    def __decouper(
        chemin: list[tuple[float, float]], limites: list[float], segments: list[Segment], rayon_exterieur: float
    ) -> list[TronconArc]:
        """Coupe le chemin aux limites des segments, pour que chaque morceau appartienne à un seul segment.

        Les transitions sont en plus découpées en petits morceaux d'au plus ANGLE_MAX_TRANSITION.
        """
        morceaux = []
        for (angle_debut, rayon_debut), (angle_fin, rayon_fin) in zip(chemin, chemin[1:]):
            coupures = [angle_debut, *(limite for limite in limites if angle_debut < limite < angle_fin), angle_fin]
            if rayon_debut != rayon_fin:
                nombre = math.ceil((angle_fin - angle_debut) / ANGLE_MAX_TRANSITION)
                pas = (angle_fin - angle_debut) / nombre
                coupures = sorted({*coupures, *(angle_debut + rang * pas for rang in range(1, nombre))})
            pente = (rayon_fin - rayon_debut) / (angle_fin - angle_debut)
            for debut, fin in zip(coupures, coupures[1:]):
                rang = max(rang for rang, limite in enumerate(limites[:-1]) if limite <= (debut + fin) / 2)
                rayon_a = rayon_debut + pente * (debut - angle_debut)
                rayon_b = rayon_debut + pente * (fin - angle_debut)
                # Sur la voie intérieure, se ranger veut dire passer sur la voie extérieure.
                place = max(0.0, rayon_exterieur - rayon_b)
                morceaux.append(TronconArc(segments[rang], debut, fin, rayon_a, rayon_b, place))
        return morceaux
