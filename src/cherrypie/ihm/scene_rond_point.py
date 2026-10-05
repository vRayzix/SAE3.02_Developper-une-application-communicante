"""Scène 2D du rond-point : la chaussée d'après la configuration, puis l'état reçu du serveur."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QFontDatabase, QPen, QTransform
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsLineItem, QGraphicsScene, QGraphicsSimpleTextItem

from cherrypie.ihm.style import (
    COULEUR_CHAUSSEE,
    COULEUR_FOND,
    COULEUR_ILOT,
    COULEUR_PASSAGE_PIETON,
    COULEUR_TEXTE,
    COULEURS_DENSITE,
    ECART_NOM_BRANCHE,
    EPAISSEUR_PASSAGE_PIETON,
    LARGEUR_BANDE_DENSITE,
    MARGE_SCENE,
    MOTIF_PASSAGE_PIETON,
    TAILLE_TEXTE,
)
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import Branche, RondPoint
from cherrypie.modele.trajectoire import DISTANCE_PASSAGE_PIETON, LARGEUR_CHAUSSEE, LONGUEUR_BRANCHE
from cherrypie.serveur.densite import NiveauDensite


class SceneRondPoint(QGraphicsScene):
    """Dessin du rond-point, en mètres, avec l'origine au centre de l'anneau.

    Qt compte les ordonnées vers le bas : un point (x, y) du rond-point est placé en
    (x, -y) dans la scène, pour que le nord reste en haut.
    """

    def __init__(self, rond_point: RondPoint) -> None:
        """Dessine la chaussée : anneau, îlot central, branches, passages piétons et noms.

        Args:
            rond_point (RondPoint): rond-point décrit par la configuration.
        """
        super().__init__()
        self.__rond_point = rond_point
        self.__bandes_densite: dict[str, QGraphicsLineItem] = {}
        self.__textes_densite: dict[str, QGraphicsSimpleTextItem] = {}
        demi_cote = rond_point.rayon + LONGUEUR_BRANCHE + MARGE_SCENE
        self.setSceneRect(-demi_cote, -demi_cote, 2 * demi_cote, 2 * demi_cote)
        self.setBackgroundBrush(QBrush(COULEUR_FOND))
        for branche in rond_point.branches:
            self.__dessiner_branche(branche)
        self.__dessiner_anneau()
        for branche in rond_point.branches:
            self.__dessiner_passage_pieton(branche)
            self.__dessiner_densite(branche)

    @property
    def rond_point(self) -> RondPoint:
        """RondPoint: rond-point dessiné."""
        return self.__rond_point

    @property
    def bandes_densite(self) -> dict[str, QGraphicsLineItem]:
        """dict[str, QGraphicsLineItem]: bande colorée le long de chaque branche, selon sa densité (copie)."""
        return dict(self.__bandes_densite)

    @property
    def textes_densite(self) -> dict[str, QGraphicsSimpleTextItem]:
        """dict[str, QGraphicsSimpleTextItem]: nom et densité affichés au bout de chaque branche (copie)."""
        return dict(self.__textes_densite)

    @staticmethod
    def vers_scene(position: Position) -> QPointF:
        """Convertit une position du rond-point en point de la scène.

        Args:
            position (Position): point du rond-point, en mètres, y vers le nord.

        Returns:
            QPointF: point de la scène, y vers le bas.
        """
        return QPointF(position.x, -position.y)

    def __dessiner_branche(self, branche: Branche) -> None:
        """Dessine la chaussée d'une branche, du centre de l'anneau jusqu'à son extrémité."""
        rayon = self.__rond_point.rayon
        crayon = QPen(COULEUR_CHAUSSEE, LARGEUR_CHAUSSEE)
        crayon.setCapStyle(Qt.PenCapStyle.FlatCap)
        debut = self.vers_scene(branche.point(rayon))
        fin = self.vers_scene(branche.point(rayon + LONGUEUR_BRANCHE))
        self.addLine(debut.x(), debut.y(), fin.x(), fin.y(), crayon)

    def __dessiner_anneau(self) -> None:
        """Dessine l'anneau, large d'une chaussée, et l'îlot central."""
        exterieur = self.__rond_point.rayon + LARGEUR_CHAUSSEE / 2
        interieur = self.__rond_point.rayon - LARGEUR_CHAUSSEE / 2
        sans_contour = QPen(Qt.PenStyle.NoPen)
        self.addEllipse(-exterieur, -exterieur, 2 * exterieur, 2 * exterieur, sans_contour, QBrush(COULEUR_CHAUSSEE))
        self.addEllipse(-interieur, -interieur, 2 * interieur, 2 * interieur, sans_contour, QBrush(COULEUR_ILOT))

    def __dessiner_passage_pieton(self, branche: Branche) -> None:
        """Dessine les bandes du passage piéton, en travers de la branche."""
        distance = self.__rond_point.rayon + DISTANCE_PASSAGE_PIETON
        crayon = QPen(COULEUR_PASSAGE_PIETON, EPAISSEUR_PASSAGE_PIETON)
        crayon.setDashPattern(MOTIF_PASSAGE_PIETON)
        crayon.setCapStyle(Qt.PenCapStyle.FlatCap)
        debut = self.vers_scene(branche.point(distance, LARGEUR_CHAUSSEE / 2))
        fin = self.vers_scene(branche.point(distance, -LARGEUR_CHAUSSEE / 2))
        self.addLine(debut.x(), debut.y(), fin.x(), fin.y(), crayon)

    def __dessiner_densite(self, branche: Branche) -> None:
        """Pose la bande de densité, côté entrée, et le texte au bout de la branche."""
        rayon = self.__rond_point.rayon
        decalage = (LARGEUR_CHAUSSEE + LARGEUR_BANDE_DENSITE) / 2
        debut = self.vers_scene(branche.point(rayon + LARGEUR_CHAUSSEE / 2, decalage))
        fin = self.vers_scene(branche.point(rayon + LONGUEUR_BRANCHE, decalage))
        crayon = QPen(COULEURS_DENSITE[NiveauDensite.FAIBLE], LARGEUR_BANDE_DENSITE)
        crayon.setCapStyle(Qt.PenCapStyle.FlatCap)
        self.__bandes_densite[branche.nom] = self.addLine(debut.x(), debut.y(), fin.x(), fin.y(), crayon)
        texte = self.addSimpleText(branche.nom)
        police = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        police.setPointSize(TAILLE_TEXTE)
        texte.setFont(police)
        texte.setBrush(QBrush(COULEUR_TEXTE))
        # Le texte garde la même taille à l'écran, quel que soit le zoom de la vue.
        texte.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        texte.setPos(self.vers_scene(branche.point(rayon + LONGUEUR_BRANCHE + ECART_NOM_BRANCHE)))
        self.__centrer(texte)
        self.__textes_densite[branche.nom] = texte

    @staticmethod
    def __centrer(texte: QGraphicsSimpleTextItem) -> None:
        """Centre un texte sur sa position, quelle que soit sa longueur."""
        cadre = texte.boundingRect()
        texte.setTransform(QTransform.fromTranslate(-cadre.width() / 2, -cadre.height() / 2))
