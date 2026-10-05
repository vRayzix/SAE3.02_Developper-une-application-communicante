"""Avancée d'un usager le long de sa trajectoire, selon la consigne qu'il suit."""

from __future__ import annotations

import math

from cherrypie.commun.protocole import CodeNotification
from cherrypie.modele.trajectoire import Trajectoire
from cherrypie.modele.usager import Usager

# Écart gardé avec l'obstacle de devant, en mètres. Il couvre aussi le retard de la
# position vue par le serveur, qui peut dater d'un pas.
DISTANCE_SECURITE = 6.0


class Deplacement:
    """Fait avancer un usager sur sa trajectoire, pas à pas.

    À chaque pas, l'usager parcourt la distance que sa consigne permet : il ralentit
    pendant un DEGAGEZ, se décale sur sa droite pendant un DEGAGEZ ou un CHANGEZ_VOIE,
    et s'arrête sur la ligne d'entrée pendant un ATTENDEZ s'il ne l'a pas encore franchie.
    Il tient aussi compte de ce que voit le conducteur (message DEVANT) : il garde une
    distance de sécurité avec l'obstacle de devant, et attend sur la ligne d'entrée quand
    il doit céder le passage. La position, la vitesse, le segment et l'étape de l'usager
    sont mis à jour après chaque pas.
    """

    def __init__(self, usager: Usager, trajectoire: Trajectoire) -> None:
        """Place l'usager au départ de sa trajectoire, à l'arrêt.

        Args:
            usager (Usager): usager à faire avancer.
            trajectoire (Trajectoire): chemin qu'il suit.
        """
        self.__usager = usager
        self.__trajectoire = trajectoire
        self.__avancement = 0.0
        self.__limite: float | None = None
        self.__ceder = False
        self.__placer_usager(0.0)

    @property
    def usager(self) -> Usager:
        """Usager: usager qui se déplace."""
        return self.__usager

    @property
    def trajectoire(self) -> Trajectoire:
        """Trajectoire: chemin suivi par l'usager."""
        return self.__trajectoire

    @property
    def avancement(self) -> float:
        """float: distance parcourue depuis le départ, en mètres."""
        return self.__avancement

    @property
    def limite(self) -> float | None:
        """float | None: avancement à ne pas dépasser à cause de l'obstacle de devant, None si la voie est libre."""
        return self.__limite

    @property
    def ceder(self) -> bool:
        """bool: True si l'usager doit attendre sur la ligne d'entrée que l'anneau se libère."""
        return self.__ceder

    @property
    def termine(self) -> bool:
        """bool: True quand l'usager est arrivé au bout de sa trajectoire."""
        return self.__avancement >= self.__trajectoire.longueur

    def noter_devant(self, distance: float | None, ceder: bool) -> None:
        """Prend en compte ce que voit le conducteur, d'après le dernier message DEVANT.

        Args:
            distance (float | None): distance jusqu'à l'obstacle devant, None si la voie est libre.
            ceder (bool): True s'il faut attendre sur la ligne d'entrée que l'anneau se libère.

        Raises:
            ValueError: si la distance est négative ou n'est pas un nombre fini.
        """
        if distance is not None and (not math.isfinite(distance) or distance < 0):
            raise ValueError(f"distance invalide : {distance}")
        self.__limite = None if distance is None else self.__avancement + max(0.0, distance - DISTANCE_SECURITE)
        self.__ceder = ceder

    def avancer(self, duree: float) -> None:
        """Fait avancer l'usager pendant une durée, puis met à jour sa position, sa vitesse, son segment et son étape.

        Args:
            duree (float): durée du pas, en secondes.

        Raises:
            ValueError: si la durée est négative ou n'est pas un nombre fini.
        """
        if not math.isfinite(duree) or duree < 0:
            raise ValueError(f"durée de pas invalide : {duree}")
        vitesse = self.__usager.vitesse_autorisee()
        arrivee = self.__avancement + vitesse * duree
        if self.__doit_s_arreter_a_la_ligne():
            arrivee = min(arrivee, self.__trajectoire.ligne_entree)
        if self.__limite is not None:
            arrivee = min(arrivee, self.__limite)
        # Un obstacle peut se rapprocher : l'usager s'arrête alors, mais ne recule jamais.
        arrivee = max(self.__avancement, min(arrivee, self.__trajectoire.longueur))
        parcouru = arrivee - self.__avancement
        self.__avancement = arrivee
        # La vitesse réelle est plus faible si l'usager a buté sur la ligne ou sur la fin du trajet.
        self.__placer_usager(min(vitesse, parcouru / duree) if duree > 0 else 0.0)

    def __doit_s_arreter_a_la_ligne(self) -> bool:
        """ATTENDEZ ou un cédez-le-passage n'arrêtent un usager que s'il n'a pas encore franchi la ligne."""
        doit_attendre = self.__usager.consigne is CodeNotification.ATTENDEZ or self.__ceder
        return doit_attendre and self.__avancement <= self.__trajectoire.ligne_entree

    def __placer_usager(self, vitesse: float) -> None:
        """Reporte l'avancement sur l'usager : position (décalage compris), vitesse, segment et étape."""
        self.__usager.position = self.__trajectoire.position_a(self.__avancement, self.__usager.decalage_lateral())
        self.__usager.vitesse = vitesse
        segment = self.__trajectoire.segment_a(self.__avancement)
        self.__usager.segment = None if segment is None else segment.nom
        self.__usager.etape = self.__trajectoire.etape_a(self.__avancement)
