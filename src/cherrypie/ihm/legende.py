"""Légende de la scène, dessinée avec les couleurs et les gabarits mêmes de la scène."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QGridLayout, QGroupBox, QHBoxLayout, QLabel, QWidget

from cherrypie.ihm.style import (
    COULEUR_CHAUSSEE,
    COULEUR_CONTOUR_USAGER,
    COULEUR_FEU_ENTREE,
    COULEUR_HALO_VP,
    COULEUR_RESERVE,
    COULEURS_CATEGORIE,
    COULEURS_CONSIGNE,
    COULEURS_DENSITE,
    GABARITS_CATEGORIE,
    NOMS_CATEGORIE,
)
from cherrypie.modele.usager import Pieton, VehiculePrioritaire, Voiture

# Taille d'une icône de légende, en pixels, et proportions des motifs dessinés dedans.
LARGEUR_ICONE = 26
HAUTEUR_ICONE = 18
PROPORTION_SILHOUETTE_LONGUEUR = 0.85
PROPORTION_SILHOUETTE_LARGEUR = 0.6
PROPORTION_BANDE = 0.35
PROPORTION_BARRE = 0.2
ARRONDI_ICONE = 2.0
EPAISSEUR_CONTOUR_FIN = 1
EPAISSEUR_CONTOUR_CONSIGNE = 3

Dessin = Callable[[QPainter, QRectF], None]


class Legende(QGroupBox):
    """Légende de la scène : usagers, consignes, marques de régulation et niveaux de densité.

    Chaque entrée associe une petite icône, peinte avec les constantes de style de la
    scène, à un libellé. Les entrées sont rangées en grille, ligne par ligne.
    """

    def __init__(self, colonnes: int, parent: QWidget | None = None) -> None:
        """Construit la légende.

        Args:
            colonnes (int): nombre d'entrées par ligne.
            parent (QWidget | None): widget parent.
        """
        super().__init__("Légende", parent)
        self.__libelles: list[str] = []
        grille = QGridLayout(self)
        for rang, (dessin, libelle) in enumerate(self.__entrees()):
            grille.addWidget(self.__entree(dessin, libelle), rang // colonnes, rang % colonnes)
            self.__libelles.append(libelle)

    @property
    def libelles(self) -> list[str]:
        """list[str]: libellés des entrées, dans l'ordre d'affichage (copie)."""
        return list(self.__libelles)

    def __entrees(self) -> list[tuple[Dessin, str]]:
        """Liste les entrées de la légende : de quoi peindre l'icône, et son libellé."""
        entrees: list[tuple[Dessin, str]] = []
        for categorie in COULEURS_CATEGORIE:
            dessin = self.__silhouette(categorie, COULEUR_CONTOUR_USAGER, EPAISSEUR_CONTOUR_FIN)
            entrees.append((dessin, NOMS_CATEGORIE[categorie]))
        for code, couleur in COULEURS_CONSIGNE.items():
            dessin = self.__silhouette(Voiture.CATEGORIE, couleur, EPAISSEUR_CONTOUR_CONSIGNE)
            entrees.append((dessin, f"Consigne {code}"))
        entrees.append((self.__bande(COULEUR_RESERVE, PROPORTION_BANDE * 2), "Voie réservée au VP"))
        entrees.append((self.__bande(COULEUR_FEU_ENTREE, PROPORTION_BARRE), "Barrière : entrée temporisée ou piéton"))
        for niveau, couleur in COULEURS_DENSITE.items():
            entrees.append((self.__bande(couleur, PROPORTION_BANDE), f"Densité {niveau.value}"))
        return entrees

    @staticmethod
    def __entree(dessin: Dessin, libelle: str) -> QWidget:
        """Construit une entrée : l'icône peinte, puis le libellé."""
        icone = QPixmap(LARGEUR_ICONE, HAUTEUR_ICONE)
        icone.fill(Qt.GlobalColor.transparent)
        pinceau = QPainter(icone)
        pinceau.setRenderHint(QPainter.RenderHint.Antialiasing)
        dessin(pinceau, QRectF(0, 0, LARGEUR_ICONE, HAUTEUR_ICONE))
        pinceau.end()
        image = QLabel()
        image.setPixmap(icone)
        entree = QWidget()
        disposition = QHBoxLayout(entree)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.addWidget(image)
        disposition.addWidget(QLabel(libelle), 1)
        return entree

    @staticmethod
    def __silhouette(categorie: str, contour: QColor, epaisseur: int) -> Dessin:
        """Silhouette d'usager vue de dessus, dans les proportions de son gabarit, avec son contour."""

        def dessiner(pinceau: QPainter, cadre: QRectF) -> None:
            longueur, largeur = GABARITS_CATEGORIE[categorie]
            # Chaque silhouette remplit l'icône dans ses propres proportions : la légende
            # montre des formes reconnaissables, pas des tailles relatives.
            echelle = min(
                cadre.width() * PROPORTION_SILHOUETTE_LONGUEUR / longueur,
                cadre.height() * PROPORTION_SILHOUETTE_LARGEUR / largeur,
            )
            silhouette = QRectF(0, 0, longueur * echelle, largeur * echelle)
            silhouette.moveCenter(cadre.center())
            if categorie == VehiculePrioritaire.CATEGORIE:
                pinceau.setPen(Qt.PenStyle.NoPen)
                pinceau.setBrush(QBrush(COULEUR_HALO_VP))
                pinceau.drawEllipse(cadre.center(), cadre.height() / 2, cadre.height() / 2)
            pinceau.setPen(QPen(contour, epaisseur))
            pinceau.setBrush(QBrush(COULEURS_CATEGORIE[categorie]))
            if categorie == Pieton.CATEGORIE:
                pinceau.drawEllipse(silhouette)
            else:
                pinceau.drawRoundedRect(silhouette, ARRONDI_ICONE, ARRONDI_ICONE)

        return dessiner

    @staticmethod
    def __bande(couleur: QColor, proportion: float) -> Dessin:
        """Bande horizontale sur fond de chaussée : voie réservée, entrée temporisée ou niveau de densité."""

        def dessiner(pinceau: QPainter, cadre: QRectF) -> None:
            pinceau.setPen(Qt.PenStyle.NoPen)
            pinceau.setBrush(QBrush(COULEUR_CHAUSSEE))
            pinceau.drawRect(cadre)
            hauteur = cadre.height() * proportion
            pinceau.setBrush(QBrush(couleur))
            pinceau.drawRect(QRectF(cadre.left(), cadre.center().y() - hauteur / 2, cadre.width(), hauteur))

        return dessiner
