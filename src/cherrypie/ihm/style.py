"""Couleurs et dimensions de la supervision, partagées par la scène et la légende.

Les dimensions sont en mètres, comme la scène du rond-point.
"""

from PyQt6.QtGui import QColor

from cherrypie.serveur.densite import NiveauDensite

COULEUR_FOND = QColor("#f4f5f7")
COULEUR_CHAUSSEE = QColor("#c9cdd3")
COULEUR_ILOT = QColor("#cfe3c8")
COULEUR_PASSAGE_PIETON = QColor("#ffffff")
COULEUR_TEXTE = QColor("#2d3436")

# Une couleur et une taille par catégorie d'usager ; le VP ressort par sa couleur et sa taille.
COULEURS_CATEGORIE = {
    "voiture": QColor("#2f6fb3"),
    "moto": QColor("#7b4fa3"),
    "trottinette": QColor("#1a9c9c"),
    "pieton": QColor("#4f7d3a"),
    "vp": QColor("#d62828"),
}
NOMS_CATEGORIE = {
    "voiture": "Voiture",
    "moto": "Moto",
    "trottinette": "Trottinette",
    "pieton": "Piéton",
    "vp": "Véhicule prioritaire",
}
RAYONS_CATEGORIE = {"voiture": 1.8, "moto": 1.2, "trottinette": 1.0, "pieton": 0.8, "vp": 2.4}
COULEUR_CONTOUR_USAGER = QColor("#ffffff")
EPAISSEUR_CONTOUR_USAGER = 0.3

# Un usager qui suit une consigne est cerclé de la couleur de cette consigne.
COULEURS_CONSIGNE = {
    "ATTENDEZ": QColor("#e67e22"),
    "DEGAGEZ": QColor("#f1c40f"),
    "CHANGEZ_VOIE": QColor("#f1c40f"),
}
EPAISSEUR_CONTOUR_CONSIGNE = 0.7

COULEUR_RESERVE = QColor(255, 159, 28, 150)
LARGEUR_RESERVE = 4.0
COULEUR_BLOQUEE = QColor("#c0392b")
EPAISSEUR_BARRE_BLOQUEE = 1.2

COULEURS_DENSITE = {
    NiveauDensite.FAIBLE: QColor("#2e9e5b"),
    NiveauDensite.MOYENNE: QColor("#e0a100"),
    NiveauDensite.FORTE: QColor("#c0392b"),
}
LARGEUR_BANDE_DENSITE = 1.5

# Marge autour du dessin, et écart entre le bout d'une branche et son nom.
MARGE_SCENE = 14.0
ECART_NOM_BRANCHE = 6.0
# Passage piéton : bandes blanches de 0,6 m, espacées d'autant (motif en largeurs de trait).
EPAISSEUR_PASSAGE_PIETON = 3.0
MOTIF_PASSAGE_PIETON = [0.2, 0.2]
TAILLE_TEXTE = 10
