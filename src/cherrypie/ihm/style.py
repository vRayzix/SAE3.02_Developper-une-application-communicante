"""Couleurs, dimensions et libellés de la supervision, partagés par la scène, la légende et les panneaux.

Les dimensions sont en mètres, comme la scène du rond-point, sauf mention contraire.
"""

from PyQt6.QtGui import QColor

from cherrypie.client.client_usager import EtatConnexion
from cherrypie.serveur.densite import NiveauDensite

# ---------- Chaussée ----------

COULEUR_FOND = QColor("#eceee9")
COULEUR_CHAUSSEE = QColor("#a5aab0")
COULEUR_TERRE_PLEIN = QColor("#b9d3a6")
COULEUR_ILOT = QColor("#a9c98f")
COULEUR_BORDURE = QColor("#f2f2ee")
COULEUR_REFUGE = QColor("#d8d9d3")
COULEUR_MARQUAGE = QColor("#ffffff")
COULEUR_TEXTE = QColor("#2b2d2f")
EPAISSEUR_BORDURE = 0.4

# ---------- Marquages au sol ----------

# Les motifs de tirets se comptent en largeurs de trait, comme dans Qt : le passage
# piéton, un trait de 3 m de large, est rayé de bandes de 0,6 m.
EPAISSEUR_LIGNE_DE_RIVE = 0.2
EPAISSEUR_SEPARATION_VOIES = 0.25
MOTIF_SEPARATION_VOIES = [12.0, 12.0]
EPAISSEUR_CEDEZ_LE_PASSAGE = 0.5
MOTIF_CEDEZ_LE_PASSAGE = [1.5, 1.5]
LARGEUR_PASSAGE_PIETON = 3.0
MOTIF_PASSAGE_PIETON = [0.2, 0.2]
DISTANCE_FLECHE = 22.0
LONGUEUR_FLECHE = 3.5
LARGEUR_FLECHE = 1.6
COULEUR_FLECHE = QColor(255, 255, 255, 170)
POINTS_NEZ_TERRE_PLEIN = 12

# ---------- Usagers ----------

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
# (longueur, largeur) : les petits usagers sont un peu agrandis pour rester visibles
# quand la vue montre tout le rond-point.
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
COULEUR_HALO_VP = QColor(209, 73, 91, 70)
RAYON_HALO_VP = 5.5
COULEUR_GYROPHARE = QColor("#e8f1ff")
GABARIT_GYROPHARE = (0.7, 1.7)

# ---------- Consignes et messages ----------

COULEURS_CONSIGNE = {
    "ATTENDEZ": QColor("#f28c28"),
    "DEGAGEZ": QColor("#f6c90e"),
    "CHANGEZ_VOIE": QColor("#00b4d8"),
}
COULEURS_MESSAGE = COULEURS_CONSIGNE | {"OK_PASSER": QColor("#3f8f5b")}
COULEUR_EVENEMENT = QColor("#7f8c8d")
# Fond assez transparent pour que le texte du message reste lisible.
OPACITE_FOND_MESSAGE = 60
EPAISSEUR_CONTOUR_CONSIGNE = 0.6

# ---------- Marques de régulation ----------

COULEUR_RESERVE = QColor(242, 140, 40, 120)
PART_VOIE_RESERVEE = 0.85
COULEUR_FEU_ENTREE = QColor("#d1495b")
EPAISSEUR_BARRE_ENTREE = 0.8
COTE_FEU_ENTREE = 2.5
ECART_FEU_ENTREE = 0.8
ECART_BARRIERE_PASSAGE = 0.8

COULEURS_DENSITE = {
    NiveauDensite.FAIBLE: QColor("#57a773"),
    NiveauDensite.MOYENNE: QColor("#e0a43a"),
    NiveauDensite.FORTE: QColor("#d1495b"),
}
LARGEUR_BANDE_DENSITE = 1.5

# ---------- Ordre d'empilement, du dessous vers le dessus ----------

PLAN_MARQUAGE = 1
PLAN_MARQUE = 2
PLAN_USAGER = 3
PLAN_VP = 4

# ---------- Scène et étiquettes ----------

MARGE_SCENE = 4.0
RECUL_ETIQUETTE = 16.0
ECART_ETIQUETTE = 1.5
TAILLE_TEXTE = 10

# ---------- Statistiques ----------

COULEUR_FOND_GRAPHIQUE = QColor("#ffffff")
# Bleu, orange, turquoise, jaune : un ordre distinguable par les daltoniens. La couleur
# suit la branche, pas son rang, pour qu'une série la garde d'un affichage à l'autre.
COULEURS_SERIES = [QColor("#2a78d6"), QColor("#eb6834"), QColor("#1baf7a"), QColor("#eda100")]

# ---------- Panneau « Serveur » ----------

COULEUR_INDICATEUR_ACTIF = QColor("#3f8f5b")
COULEUR_INDICATEUR_INACTIF = QColor("#7f8c8d")

LIBELLES_CONNEXION = {
    EtatConnexion.CONNEXION: "connexion en cours",
    EtatConnexion.CONNECTE: "connecté",
    EtatConnexion.DECONNECTE: "déconnecté",
    EtatConnexion.TERMINE: "terminé",
}
