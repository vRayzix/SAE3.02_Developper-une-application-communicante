"""Ce que voit chaque conducteur : la place libre devant lui et l'anneau à son entrée.

Chaque client roule sans voir les autres. Le serveur, qui connaît toutes les
positions, calcule pour chaque véhicule la distance jusqu'à l'obstacle le plus proche
devant lui sur sa voie, et s'il doit céder le passage avant d'entrer sur l'anneau.
Ce n'est pas une consigne de régulation : c'est ce qu'un conducteur verrait par son
pare-brise, et cela vaut que la régulation soit active ou non.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import Branche, RondPoint
from cherrypie.modele.trajectoire import DISTANCE_PASSAGE_PIETON, Etape
from cherrypie.modele.usager import Pieton, Usager
from cherrypie.serveur.registre import Registre

# Au-delà de cette distance, un obstacle ne gêne pas encore : la voie est dite libre.
PORTEE_VUE = 50.0
# Deux usagers dont le décalage latéral diffère d'au moins cette valeur ne sont pas sur la
# même voie : un usager rangé sur le côté ne gêne pas ceux qui roulent au milieu.
ECART_MEME_VOIE = 1.0
# Pour entrer, il faut que l'anneau soit libre sur ces distances, avant et après le point
# d'entrée. Ces marges empêchent l'anneau de se remplir au point de se bloquer en boucle.
LIBRE_AMONT = 15.0
LIBRE_AVAL = 10.0


@dataclass(frozen=True)
class Vue:
    """Ce que voit un conducteur.

    Attributes:
        distance (float | None): distance jusqu'à l'obstacle le plus proche devant lui sur sa
            voie, en mètres ; None si la voie est libre.
        ceder (bool): True s'il doit attendre sur la ligne d'entrée que l'anneau se libère.
    """

    distance: float | None
    ceder: bool


class Circulation:
    """Calcule ce que voit chaque véhicule, à partir des dernières positions reçues."""

    def __init__(self, rond_point: RondPoint) -> None:
        """Crée le calcul pour un rond-point.

        Args:
            rond_point (RondPoint): rond-point parcouru par les usagers.
        """
        self.__rond_point = rond_point

    @property
    def rond_point(self) -> RondPoint:
        """RondPoint: rond-point parcouru par les usagers."""
        return self.__rond_point

    def voir(self, registre: Registre) -> dict[str, Vue]:
        """Calcule ce que voit chaque véhicule dont la position est connue.

        Les piétons n'ont pas de vue : ils ne roulent pas sur la chaussée. En revanche, un
        piéton en train de traverser bloque les véhicules avant son passage piéton.

        Args:
            registre (Registre): usagers connectés, avec leur dernière position et leur étape.

        Returns:
            dict[str, Vue]: la vue de chaque véhicule, par identifiant.
        """
        vehicules = [
            usager for usager in registre.usagers if not isinstance(usager, Pieton) and usager.position is not None
        ]
        passages_occupes = {
            usager.branche_entree
            for usager in registre.usagers
            if isinstance(usager, Pieton) and usager.etape is Etape.TRAVERSEE
        }
        return {
            vehicule.identifiant: self.__vue(rang, vehicules, passages_occupes)
            for rang, vehicule in enumerate(vehicules)
        }

    def __vue(self, rang: int, vehicules: list[Usager], passages_occupes: set[str]) -> Vue:
        """Calcule la vue du véhicule de rang donné."""
        usager = vehicules[rang]
        if usager.etape is Etape.APPROCHE:
            branche = self.__rond_point.branche(usager.branche_entree)
            distances = self.__devant_sur_la_branche(rang, vehicules, branche, Etape.APPROCHE, passages_occupes)
            return Vue(self.__plus_proche(distances), not self.__anneau_libre(branche, vehicules))
        if usager.etape is Etape.ANNEAU:
            return Vue(self.__plus_proche(self.__devant_sur_l_anneau(rang, vehicules, passages_occupes)), False)
        branche = self.__rond_point.branche(usager.branche_sortie)
        distances = self.__devant_sur_la_branche(rang, vehicules, branche, Etape.SORTIE, passages_occupes)
        return Vue(self.__plus_proche(distances), False)

    def __devant_sur_la_branche(
        self, rang: int, vehicules: list[Usager], branche: Branche, etape: Etape, passages_occupes: set[str]
    ) -> list[float]:
        """Distances aux obstacles devant un véhicule en approche ou en sortie sur une branche."""
        usager = vehicules[rang]
        # En approche on roule vers le centre, en sortie on s'en éloigne.
        sens = -1.0 if etape is Etape.APPROCHE else 1.0
        abscisse = sens * self.__le_long(usager.position, branche)
        distances = []
        for autre_rang, autre in enumerate(vehicules):
            if autre_rang == rang or autre.etape is not etape or self.__branche_de(autre) != branche.nom:
                continue
            if not self.__meme_voie(usager, autre):
                continue
            autre_abscisse = sens * self.__le_long(autre.position, branche)
            # À égalité, le premier arrivé au registre est devant.
            if autre_abscisse > abscisse or (autre_abscisse == abscisse and autre_rang < rang):
                distances.append(autre_abscisse - abscisse)
        passage = sens * (self.__rond_point.rayon + DISTANCE_PASSAGE_PIETON)
        if branche.nom in passages_occupes and passage > abscisse:
            distances.append(passage - abscisse)
        return distances

    def __devant_sur_l_anneau(self, rang: int, vehicules: list[Usager], passages_occupes: set[str]) -> list[float]:
        """Distances aux obstacles devant un véhicule sur l'anneau, jusqu'au bout de sa branche de sortie."""
        usager = vehicules[rang]
        rayon = self.__rond_point.rayon
        angle = self.__angle(usager.position)
        sortie = self.__rond_point.branche(usager.branche_sortie)
        # Ce qui se trouve sur l'anneau au-delà de sa sortie n'est plus sur son chemin.
        reste_anneau = rayon * ((math.radians(sortie.angle) - angle) % math.tau)
        distances = []
        for autre_rang, autre in enumerate(vehicules):
            if autre_rang == rang or not self.__meme_voie(usager, autre):
                continue
            if autre.etape is Etape.ANNEAU:
                devant = rayon * ((self.__angle(autre.position) - angle) % math.tau)
                if devant <= reste_anneau and (devant > 0 or autre_rang < rang):
                    distances.append(devant)
            elif autre.etape is Etape.SORTIE and autre.branche_sortie == sortie.nom:
                distances.append(reste_anneau + self.__le_long(autre.position, sortie) - rayon)
        if sortie.nom in passages_occupes:
            distances.append(reste_anneau + DISTANCE_PASSAGE_PIETON)
        return distances

    def __anneau_libre(self, branche: Branche, vehicules: list[Usager]) -> bool:
        """Indique si l'anneau est libre autour du point d'entrée d'une branche.

        Un véhicule rangé sur le côté de l'anneau ne compte pas : il laisse la voie libre.
        """
        point = math.radians(branche.angle)
        rayon = self.__rond_point.rayon
        for vehicule in vehicules:
            if vehicule.etape is not Etape.ANNEAU or self.__decalage(vehicule) >= ECART_MEME_VOIE:
                continue
            angle = self.__angle(vehicule.position)
            amont = rayon * ((point - angle) % math.tau)
            aval = rayon * ((angle - point) % math.tau)
            if amont < LIBRE_AMONT or aval < LIBRE_AVAL:
                return False
        return True

    def __meme_voie(self, usager: Usager, autre: Usager) -> bool:
        """Indique si deux véhicules roulent sur la même voie, d'après leurs décalages latéraux."""
        return abs(self.__decalage(usager) - self.__decalage(autre)) < ECART_MEME_VOIE

    def __decalage(self, usager: Usager) -> float:
        """Écart latéral d'un véhicule par rapport au milieu de sa voie, en mètres."""
        if usager.etape is Etape.ANNEAU:
            return abs(math.hypot(usager.position.x, usager.position.y) - self.__rond_point.rayon)
        branche = self.__rond_point.branche(self.__branche_de(usager))
        return abs(self.__ecart_a_l_axe(usager.position, branche))

    @staticmethod
    def __branche_de(usager: Usager) -> str:
        """Branche où roule un véhicule hors de l'anneau : son entrée en approche, sa sortie ensuite."""
        return usager.branche_entree if usager.etape is Etape.APPROCHE else usager.branche_sortie

    @staticmethod
    def __le_long(position: Position, branche: Branche) -> float:
        """Distance au centre mesurée le long de l'axe d'une branche."""
        angle = math.radians(branche.angle)
        return position.x * math.cos(angle) + position.y * math.sin(angle)

    @staticmethod
    def __ecart_a_l_axe(position: Position, branche: Branche) -> float:
        """Écart à l'axe d'une branche, positif vers la droite d'un usager qui arrive."""
        angle = math.radians(branche.angle)
        return -position.x * math.sin(angle) + position.y * math.cos(angle)

    @staticmethod
    def __angle(position: Position) -> float:
        """Angle d'une position vue du centre, en radians, entre 0 et 2π."""
        return math.atan2(position.y, position.x) % math.tau

    @staticmethod
    def __plus_proche(distances: list[float]) -> float | None:
        """Distance à l'obstacle le plus proche, None s'il est hors de portée ou s'il n'y en a pas."""
        if not distances or min(distances) > PORTEE_VUE:
            return None
        return min(distances)
