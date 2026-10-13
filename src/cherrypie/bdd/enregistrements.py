"""Enregistrements de l'historique, tels que le serveur les confie à la base."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TypeConnexion(Enum):
    """Arrivée ou départ d'un usager, dans la table evenement_connexion."""

    CONNEXION = "connexion"
    DECONNEXION = "deconnexion"


@dataclass(frozen=True)
class ReleveDensite:
    """Densité d'une branche à un instant.

    Attributes:
        instant (datetime): date et heure du relevé.
        branche (str): identifiant de la branche.
        densite (float): usagers présents / capacité, entre 0 et 1.
    """

    instant: datetime
    branche: str
    densite: float


@dataclass(frozen=True)
class EvenementConnexion:
    """Connexion ou déconnexion d'un usager.

    Attributes:
        instant (datetime): date et heure de l'événement.
        usager (str): identifiant de l'usager.
        categorie (str): catégorie de l'usager (ex. "voiture").
        evenement (TypeConnexion): connexion ou déconnexion.
        detail (str): ce qui s'est passé, par exemple la raison d'une déconnexion.
    """

    instant: datetime
    usager: str
    categorie: str
    evenement: TypeConnexion
    detail: str
