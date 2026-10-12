"""Couleurs, dimensions et libellés de la supervision, partagés par la scène, la légende et les panneaux.

Les dimensions sont en mètres, comme la scène du rond-point, sauf mention contraire.
"""

from PyQt6.QtGui import QColor

from cherrypie.client.client_usager import EtatConnexion
from cherrypie.serveur.densite import NiveauDensite

# Palette sobre : chaussée grise, espaces verts doux, marquages blancs.
COULEUR_FOND = QColor("#eceee9")
COULEUR_CHAUSSEE = QColor("#a5aab0")
COULEUR_TERRE_PLEIN = QColor("#b9d3a6")
COULEUR_ILOT = QColor("#a9c98f")
COULEUR_BORDURE = QColor("#f2f2ee")
COULEUR_REFUGE = QColor("#d8d9d3")
COULEUR_MARQUAGE = QColor("#ffffff")
COULEUR_TEXTE = QColor("#2b2d2f")
EPAISSEUR_BORDURE = 0.4

# Marquages au sol. Les motifs de tirets se comptent en largeurs de trait, comme dans Qt.
EPAISSEUR_LIGNE_DE_RIVE = 0.2
EPAISSEUR_SEPARATION_VOIES = 0.25
MOTIF_SEPARATION_VOIES = [12.0, 12.0]
EPAISSEUR_CEDEZ_LE_PASSAGE = 0.5
MOTIF_CEDEZ_LE_PASSAGE = [1.5, 1.5]
# Passage piéton : bande de 3 m le long de la route, rayée de bandes de 0,6 m.
LARGEUR_PASSAGE_PIETON = 3.0
MOTIF_PASSAGE_PIETON = [0.2, 0.2]
# Flèches peintes sur chaque chaussée, à cette distance du bord de l'anneau.
DISTANCE_FLECHE = 22.0
LONGUEUR_FLECHE = 3.5
LARGEUR_FLECHE = 1.6
COULEUR_FLECHE = QColor(255, 255, 255, 170)
# Nombre de points qui dessinent le nez arrondi d'un terre-plein, côté anneau.
POINTS_NEZ_TERRE_PLEIN = 12

# Une couleur et un gabarit (longueur, largeur) par catégorie. Les petits usagers sont un
# peu agrandis pour rester visibles quand la vue montre tout le rond-point.
COULEURS_CATEGORIE = {
    "voiture": QColor("#3d6fb6"),
    "moto": QColor("#7d5ba6"),
    "trottinette": QColor("#2a9d8f"),
    "pieton": QColor("#4f7d3a"),
    "vp": QColor("#d1495b"),
}
NOMS_CATEGORIE = {
    "voiture": "Voiture",
    "moto": "Moto",
    "trottinette": "Trottinette",
    "pieton": "Piéton",
    "vp": "Véhicule prioritaire",
}
GABARITS_CATEGORIE = {
    "voiture": (4.4, 1.9),
    "moto": (2.4, 1.0),
    "trottinette": (1.8, 0.9),
    "pieton": (1.4, 1.4),
    "vp": (5.8, 2.3),
}
ARRONDI_USAGER = 0.4
COULEUR_CONTOUR_USAGER = QColor("#ffffff")
EPAISSEUR_CONTOUR_USAGER = 0.25
# Halo translucide et rampe lumineuse du VP, pour le repérer d'un coup d'œil.
COULEUR_HALO_VP = QColor(209, 73, 91, 70)
RAYON_HALO_VP = 5.5
COULEUR_GYROPHARE = QColor("#e8f1ff")
GABARIT_GYROPHARE = (0.7, 1.7)

# Un usager qui suit une consigne est cerclé de la couleur de cette consigne.
COULEURS_CONSIGNE = {
    "ATTENDEZ": QColor("#f28c28"),
    "DEGAGEZ": QColor("#f6c90e"),
    "CHANGEZ_VOIE": QColor("#f6c90e"),
}
EPAISSEUR_CONTOUR_CONSIGNE = 0.6

# Voie intérieure réservée au VP, sur les segments qu'il va parcourir.
COULEUR_RESERVE = QColor(242, 140, 40, 120)
PART_VOIE_RESERVEE = 0.85
# Entrée temporisée : barre en travers de la chaussée d'entrée, sur la ligne, et feu à côté.
COULEUR_FEU_ENTREE = QColor("#d1495b")
EPAISSEUR_BARRE_ENTREE = 0.8
COTE_FEU_ENTREE = 2.5
ECART_FEU_ENTREE = 0.8
# Passage fermé par un piéton : même barre, posée juste avant les bandes du passage.
ECART_BARRIERE_PASSAGE = 0.8

COULEURS_DENSITE = {
    NiveauDensite.FAIBLE: QColor("#57a773"),
    NiveauDensite.MOYENNE: QColor("#e0a43a"),
    NiveauDensite.FORTE: QColor("#d1495b"),
}
LARGEUR_BANDE_DENSITE = 1.5

# Ordre d'empilement : la chaussée en dessous, puis les marquages, les marques de
# régulation, les usagers, et le VP au-dessus de tout.
PLAN_MARQUAGE = 1
PLAN_MARQUE = 2
PLAN_USAGER = 3
PLAN_VP = 4

MARGE_SCENE = 4.0
# Étiquette de branche : posée côté sortie, à côté de la chaussée, un peu avant le bout de la branche.
RECUL_ETIQUETTE = 16.0
ECART_ETIQUETTE = 1.5
TAILLE_TEXTE = 10

# Indicateurs du panneau « Serveur » : en vert ce qui fonctionne, en gris ce qui est coupé ou inconnu.
COULEUR_INDICATEUR_ACTIF = QColor("#3f8f5b")
COULEUR_INDICATEUR_INACTIF = QColor("#7f8c8d")

LIBELLES_CONNEXION = {
    EtatConnexion.CONNEXION: "connexion en cours",
    EtatConnexion.CONNECTE: "connecté",
    EtatConnexion.DECONNECTE: "déconnecté",
    EtatConnexion.TERMINE: "terminé",
}
