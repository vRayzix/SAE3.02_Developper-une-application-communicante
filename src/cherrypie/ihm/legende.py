"""Légende de la scène, dessinée avec les couleurs mêmes de la scène."""

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
    NOMS_CATEGORIE,
)
from cherrypie.modele.usager import VehiculePrioritaire, Voiture

# Côté d'une icône de légende, en pixels, et proportions des motifs dessinés dedans.
TAILLE_ICONE = 18
PROPORTION_DISQUE = 0.6
PROPORTION_BANDE = 0.35
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
        for categorie, couleur in COULEURS_CATEGORIE.items():
            halo = categorie == VehiculePrioritaire.CATEGORIE
            dessin = self.__disque(couleur, COULEUR_CONTOUR_USAGER, EPAISSEUR_CONTOUR_FIN, halo)
            entrees.append((dessin, NOMS_CATEGORIE[categorie]))
        for code, couleur in COULEURS_CONSIGNE.items():
            dessin = self.__disque(COULEURS_CATEGORIE[Voiture.CATEGORIE], couleur, EPAISSEUR_CONTOUR_CONSIGNE, False)
            entrees.append((dessin, f"Consigne {code}"))
        entrees.append((self.__bande(COULEUR_RESERVE), "Segment réservé au VP"))
        entrees.append((self.__carre(COULEUR_FEU_ENTREE), "Entrée temporisée"))
        for niveau, couleur in COULEURS_DENSITE.items():
            entrees.append((self.__bande(couleur), f"Densité {niveau.value}"))
        return entrees

    @staticmethod
    def __entree(dessin: Dessin, libelle: str) -> QWidget:
        """Construit une entrée : l'icône peinte, puis le libellé."""
        icone = QPixmap(TAILLE_ICONE, TAILLE_ICONE)
        icone.fill(Qt.GlobalColor.transparent)
        pinceau = QPainter(icone)
        pinceau.setRenderHint(QPainter.RenderHint.Antialiasing)
        dessin(pinceau, QRectF(0, 0, TAILLE_ICONE, TAILLE_ICONE))
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
    def __disque(remplissage: QColor, contour: QColor, epaisseur: int, halo: bool) -> Dessin:
        """Disque d'usager, avec son contour et, pour le VP, son halo."""

        def dessiner(pinceau: QPainter, cadre: QRectF) -> None:
            if halo:
                pinceau.setPen(Qt.PenStyle.NoPen)
                pinceau.setBrush(QBrush(COULEUR_HALO_VP))
                pinceau.drawEllipse(cadre)
            cote = cadre.width() * PROPORTION_DISQUE
            disque = QRectF(0, 0, cote, cote)
            disque.moveCenter(cadre.center())
            pinceau.setPen(QPen(contour, epaisseur))
            pinceau.setBrush(QBrush(remplissage))
            pinceau.drawEllipse(disque)

        return dessiner

    @staticmethod
    def __bande(couleur: QColor) -> Dessin:
        """Bande horizontale, sur fond de chaussée : segment réservé ou niveau de densité."""

        def dessiner(pinceau: QPainter, cadre: QRectF) -> None:
            pinceau.setPen(Qt.PenStyle.NoPen)
            pinceau.setBrush(QBrush(COULEUR_CHAUSSEE))
            pinceau.drawRect(cadre)
            hauteur = cadre.height() * PROPORTION_BANDE
            pinceau.setBrush(QBrush(couleur))
            pinceau.drawRect(QRectF(cadre.left(), cadre.center().y() - hauteur / 2, cadre.width(), hauteur))

        return dessiner

    @staticmethod
    def __carre(couleur: QColor) -> Dessin:
        """Carré plein, comme le feu d'une entrée temporisée."""

        def dessiner(pinceau: QPainter, cadre: QRectF) -> None:
            cote = cadre.width() * PROPORTION_DISQUE
            carre = QRectF(0, 0, cote, cote)
            carre.moveCenter(cadre.center())
            pinceau.setPen(QPen(COULEUR_CONTOUR_USAGER, EPAISSEUR_CONTOUR_FIN))
            pinceau.setBrush(QBrush(couleur))
            pinceau.drawRect(carre)

        return dessiner
