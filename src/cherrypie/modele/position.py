"""Position d'un point dans le repère du rond-point."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    """Point du plan, en mètres : origine au centre de l'anneau, x vers l'est, y vers le nord."""

    x: float
    y: float

    def __post_init__(self) -> None:
        """Vérifie que les deux coordonnées sont des nombres (TypeError) finis (ValueError)."""
        for nom, valeur in (("x", self.x), ("y", self.y)):
            # bool est une sous-classe de int : sans ce test, True passerait pour 1.
            if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
                raise TypeError(f"la coordonnée {nom} doit être un nombre (reçu : {valeur!r})")
            if not math.isfinite(valeur):
                raise ValueError(f"la coordonnée {nom} doit être un nombre fini (reçu : {valeur!r})")

    def distance(self, autre: Position) -> float:
        """Distance en ligne droite jusqu'à un autre point, en mètres."""
        return math.hypot(autre.x - self.x, autre.y - self.y)
