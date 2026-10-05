"""Densité d'occupation des branches du rond-point."""

from __future__ import annotations

from enum import Enum

from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import Etape
from cherrypie.serveur.registre import Registre

# Seuils du cahier des charges : faible en dessous de 0,4, moyenne en dessous de 0,7, forte au-delà.
SEUIL_MOYENNE = 0.4
SEUIL_FORTE = 0.7


class NiveauDensite(Enum):
    """Niveau de densité d'une branche."""

    FAIBLE = "faible"
    MOYENNE = "moyenne"
    FORTE = "forte"


class CalculateurDensite:
    """Calcule la densité de chaque branche à partir des usagers connectés.

    Une branche est occupée par les usagers en approche, qui roulent vers l'anneau ou
    attendent d'y entrer : c'est eux que le dosage des entrées doit répartir. Ceux qui
    repartent par une branche ne gênent plus personne à l'entrée.
    """

    def __init__(self, rond_point: RondPoint) -> None:
        """Crée un calculateur pour un rond-point.

        Args:
            rond_point (RondPoint): rond-point dont on mesure les branches.
        """
        self.__rond_point = rond_point

    @property
    def rond_point(self) -> RondPoint:
        """RondPoint: rond-point dont on mesure les branches."""
        return self.__rond_point

    def calculer(self, registre: Registre) -> dict[str, float]:
        """Calcule la densité de toutes les branches.

        Args:
            registre (Registre): usagers connectés, avec leur dernière étape connue.

        Returns:
            dict[str, float]: pour chaque branche, usagers en approche / capacité, borné entre 0 et 1.
        """
        en_approche = {branche.nom: 0 for branche in self.__rond_point.branches}
        for usager in registre.usagers:
            if usager.etape is Etape.APPROCHE:
                en_approche[usager.branche_entree] += 1
        return {
            branche.nom: min(1.0, en_approche[branche.nom] / branche.capacite)
            for branche in self.__rond_point.branches
        }

    @staticmethod
    def niveau(densite: float) -> NiveauDensite:
        """Classe une densité selon les seuils du cahier des charges.

        Args:
            densite (float): densité d'une branche, entre 0 et 1.

        Returns:
            NiveauDensite: faible en dessous de 0,4, moyenne en dessous de 0,7, forte au-delà.

        Raises:
            ValueError: si la densité n'est pas comprise entre 0 et 1.
        """
        # Écrit ainsi, le test refuse aussi NaN, pour lequel toute comparaison est fausse.
        if not 0 <= densite <= 1:
            raise ValueError(f"une densité est comprise entre 0 et 1 (reçu : {densite})")
        if densite < SEUIL_MOYENNE:
            return NiveauDensite.FAIBLE
        if densite < SEUIL_FORTE:
            return NiveauDensite.MOYENNE
        return NiveauDensite.FORTE
