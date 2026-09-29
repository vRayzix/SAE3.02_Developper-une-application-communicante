"""Position d'un point dans le repère du rond-point."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    """Point du plan, en mètres.

    L'origine est le centre de l'anneau, x pointe vers l'est et y vers le nord.

    Attributes:
        x (float): abscisse, en mètres.
        y (float): ordonnée, en mètres.
    """

    x: float
    y: float

    def __post_init__(self) -> None:
        """Vérifie que les deux coordonnées sont des nombres finis.

        Raises:
            TypeError: si une coordonnée n'est pas un nombre.
            ValueError: si une coordonnée est infinie ou NaN.
        """
        for nom, valeur in (("x", self.x), ("y", self.y)):
            # bool est une sous-classe de int : sans ce test, True passerait pour 1.
            if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
                raise TypeError(f"la coordonnée {nom} doit être un nombre (reçu : {valeur!r})")
            if not math.isfinite(valeur):
                raise ValueError(f"la coordonnée {nom} doit être un nombre fini (reçu : {valeur!r})")

    def distance(self, autre: Position) -> float:
        """Calcule la distance en ligne droite jusqu'à un autre point.

        Args:
            autre (Position): point d'arrivée.

        Returns:
            float: distance en mètres.
        """
        return math.hypot(autre.x - self.x, autre.y - self.y)
