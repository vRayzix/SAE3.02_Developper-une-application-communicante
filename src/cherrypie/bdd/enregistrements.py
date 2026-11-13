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
    """Densité d'une branche à un instant : usagers en approche / capacité, entre 0 et 1."""

    instant: datetime
    branche: str
    densite: float


@dataclass(frozen=True)
class EvenementConnexion:
    """Connexion ou déconnexion d'un usager ; detail donne par exemple la raison d'une déconnexion."""

    instant: datetime
    usager: str
    categorie: str
    evenement: TypeConnexion
    detail: str
