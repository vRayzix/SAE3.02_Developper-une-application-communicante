"""Rond-point de Bel Air pour les tests, tel que le décrit config.exemple.ini."""

from pathlib import Path

from cherrypie.commun.config import Configuration, ParametresBranche
from cherrypie.modele.rond_point import RondPoint

CHEMIN_EXEMPLE = Path(__file__).resolve().parent.parent / "config.exemple.ini"
NATIONS_NORD = "nations_nord"
JEAN_DE_LA_BRUYERE = "jean_de_la_bruyere"
NATIONS_SUD = "nations_sud"
ALBERT_CAMUS = "albert_camus"


def config_exemple() -> Configuration:
    """Configuration d'exemple, telle que livrée dans le dépôt."""
    return Configuration.depuis_fichier(CHEMIN_EXEMPLE)


def rond_point_bel_air(rayon: float | None = None, capacite: int | None = None) -> RondPoint:
    """Rond-point de la configuration d'exemple, avec un autre rayon ou une autre capacité si besoin."""
    config = config_exemple()
    return RondPoint(
        config.branches,
        config.rayon if rayon is None else rayon,
        config.largeur_voie_anneau,
        config.largeur_chaussee,
        config.longueur_branche,
        config.capacite_par_branche if capacite is None else capacite,
    )


def rond_point_a_trois_branches() -> RondPoint:
    """Petit rond-point à trois branches régulièrement réparties, aux dimensions de l'exemple."""
    config = config_exemple()
    branches = [
        ParametresBranche(nom, f"Rue {nom}", cap, 2.0, 6.0) for nom, cap in (("a", 0.0), ("b", 120.0), ("c", 240.0))
    ]
    return RondPoint(
        branches, config.rayon, config.largeur_voie_anneau, config.largeur_chaussee, config.longueur_branche, 8
    )
