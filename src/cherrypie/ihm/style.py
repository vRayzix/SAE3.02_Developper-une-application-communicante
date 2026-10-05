"""Couleurs, dimensions et libellés de la supervision, partagés par la scène, la légende et les panneaux.

Les dimensions sont en mètres, comme la scène du rond-point.
"""

from PyQt6.QtGui import QColor

from cherrypie.client.client_usager import EtatConnexion
from cherrypie.serveur.densite import NiveauDensite

COULEUR_FOND = QColor("#f4f5f7")
COULEUR_CHAUSSEE = QColor("#c9cdd3")
COULEUR_ILOT = QColor("#cfe3c8")
COULEUR_PASSAGE_PIETON = QColor("#ffffff")
COULEUR_TEXTE = QColor("#2d3436")

# Une couleur et une taille par catégorie d'usager ; le VP ressort par sa couleur et sa taille.
# Les tailles sont un peu exagérées pour rester lisibles quand la vue montre tout le rond-point.
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
RAYONS_CATEGORIE = {"voiture": 2.2, "moto": 1.8, "trottinette": 1.5, "pieton": 1.3, "vp": 3.0}
COULEUR_CONTOUR_USAGER = QColor("#ffffff")
EPAISSEUR_CONTOUR_USAGER = 0.3
# Halo translucide autour du VP, pour le repérer d'un coup d'œil.
COULEUR_HALO_VP = QColor(214, 40, 40, 60)
RAYON_HALO_VP = 6.0

# Un usager qui suit une consigne est cerclé de la couleur de cette consigne.
COULEURS_CONSIGNE = {
    "ATTENDEZ": QColor("#e67e22"),
    "DEGAGEZ": QColor("#f1c40f"),
    "CHANGEZ_VOIE": QColor("#f1c40f"),
}
EPAISSEUR_CONTOUR_CONSIGNE = 0.7

COULEUR_RESERVE = QColor(255, 159, 28, 150)
LARGEUR_RESERVE = 4.0
# Feu carré posé au bord de la voie d'entrée, à hauteur de la ligne, quand l'entrée est temporisée.
COULEUR_FEU_ENTREE = QColor("#c0392b")
COTE_FEU_ENTREE = 3.0
ECART_FEU_ENTREE = 0.5

COULEURS_DENSITE = {
    NiveauDensite.FAIBLE: QColor("#2e9e5b"),
    NiveauDensite.MOYENNE: QColor("#e0a100"),
    NiveauDensite.FORTE: QColor("#c0392b"),
}
LARGEUR_BANDE_DENSITE = 1.5

# Ordre d'empilement : la chaussée en dessous, puis les marques de régulation, puis les usagers.
PLAN_MARQUE = 1
PLAN_USAGER = 2
PLAN_VP = 3

MARGE_SCENE = 6.0
# Étiquette de branche : posée côté sortie, à côté de la chaussée, un peu avant le bout de la branche.
RECUL_ETIQUETTE = 8.0
ECART_ETIQUETTE = 1.5
# Passage piéton : bandes blanches de 0,6 m, espacées d'autant (motif en largeurs de trait).
EPAISSEUR_PASSAGE_PIETON = 3.0
MOTIF_PASSAGE_PIETON = [0.2, 0.2]
TAILLE_TEXTE = 10

LIBELLES_CONNEXION = {
    EtatConnexion.CONNEXION: "connexion en cours",
    EtatConnexion.CONNECTE: "connecté",
    EtatConnexion.DECONNECTE: "déconnecté",
    EtatConnexion.TERMINE: "terminé",
}
