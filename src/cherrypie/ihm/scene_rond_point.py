"""Scène 2D du rond-point : la chaussée d'après la configuration, puis l'état reçu du serveur."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QFontDatabase, QPainterPath, QPen, QTextOption, QTransform
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from cherrypie.ihm.style import (
    COULEUR_CHAUSSEE,
    COULEUR_CONTOUR_USAGER,
    COULEUR_FEU_ENTREE,
    COULEUR_FOND,
    COULEUR_HALO_VP,
    COULEUR_ILOT,
    COULEUR_PASSAGE_PIETON,
    COULEUR_RESERVE,
    COULEUR_TEXTE,
    COULEURS_CATEGORIE,
    COULEURS_CONSIGNE,
    COULEURS_DENSITE,
    COTE_FEU_ENTREE,
    ECART_ETIQUETTE,
    ECART_FEU_ENTREE,
    EPAISSEUR_CONTOUR_CONSIGNE,
    EPAISSEUR_CONTOUR_USAGER,
    EPAISSEUR_PASSAGE_PIETON,
    LARGEUR_BANDE_DENSITE,
    LARGEUR_RESERVE,
    MARGE_SCENE,
    MOTIF_PASSAGE_PIETON,
    NOMS_CATEGORIE,
    PLAN_MARQUE,
    PLAN_USAGER,
    PLAN_VP,
    RAYON_HALO_VP,
    RAYONS_CATEGORIE,
    RECUL_ETIQUETTE,
    TAILLE_TEXTE,
)
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import Branche, RondPoint, Segment
from cherrypie.modele.trajectoire import DISTANCE_PASSAGE_PIETON, LARGEUR_CHAUSSEE, LONGUEUR_BRANCHE
from cherrypie.modele.usager import KMH, VehiculePrioritaire
from cherrypie.serveur.densite import CalculateurDensite, NiveauDensite

TOUR_COMPLET = 360.0
POURCENT = 100


class MarqueurUsager(QGraphicsEllipseItem):
    """Disque qui représente un usager : couleur et taille selon sa catégorie, contour selon sa consigne.

    Le VP est entouré d'un halo et passe au-dessus des autres usagers.
    """

    def __init__(self, categorie: str) -> None:
        """Crée le marqueur d'un usager, centré sur sa position.

        Args:
            categorie (str): catégorie de l'usager (ex. "voiture").
        """
        super().__init__()
        self.__categorie = categorie
        rayon = RAYONS_CATEGORIE[categorie]
        self.setRect(-rayon, -rayon, 2 * rayon, 2 * rayon)
        self.setBrush(QBrush(COULEURS_CATEGORIE[categorie]))
        self.__halo: QGraphicsEllipseItem | None = None
        if categorie == VehiculePrioritaire.CATEGORIE:
            self.__halo = QGraphicsEllipseItem(-RAYON_HALO_VP, -RAYON_HALO_VP, 2 * RAYON_HALO_VP, 2 * RAYON_HALO_VP, self)
            self.__halo.setPen(QPen(Qt.PenStyle.NoPen))
            self.__halo.setBrush(QBrush(COULEUR_HALO_VP))
            self.__halo.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent)
            self.setZValue(PLAN_VP)
        else:
            self.setZValue(PLAN_USAGER)

    @property
    def categorie(self) -> str:
        """str: catégorie de l'usager représenté."""
        return self.__categorie

    @property
    def halo(self) -> QGraphicsEllipseItem | None:
        """QGraphicsEllipseItem | None: halo du VP, None pour les autres usagers."""
        return self.__halo

    def afficher(self, usager: dict) -> None:
        """Affiche la consigne de l'usager par le contour, et son détail dans l'infobulle.

        Args:
            usager (dict): description de l'usager, telle que le STATE la transmet.
        """
        consigne = usager["consigne"]
        if consigne in COULEURS_CONSIGNE:
            self.setPen(QPen(COULEURS_CONSIGNE[consigne], EPAISSEUR_CONTOUR_CONSIGNE))
        else:
            self.setPen(QPen(COULEUR_CONTOUR_USAGER, EPAISSEUR_CONTOUR_USAGER))
        detail = (
            f"{usager['id']} ({NOMS_CATEGORIE[self.__categorie]}) : de {usager['entree']} vers {usager['sortie']}, "
            f"{round(usager['vitesse'] / KMH)} km/h"
        )
        self.setToolTip(detail if consigne is None else f"{detail}, consigne {consigne}")


class SceneRondPoint(QGraphicsScene):
    """Dessin du rond-point, en mètres, avec l'origine au centre de l'anneau.

    Qt compte les ordonnées vers le bas : un point (x, y) du rond-point est placé en
    (x, -y) dans la scène, pour que le nord reste en haut. La scène n'interprète rien :
    elle montre l'état que le serveur diffuse.
    """

    def __init__(self, rond_point: RondPoint) -> None:
        """Dessine la chaussée : anneau, îlot central, branches, passages piétons et étiquettes.

        Les marques de régulation (segments réservés, entrées bloquées) sont posées tout
        de suite, cachées, et n'apparaissent que quand un STATE les signale.

        Args:
            rond_point (RondPoint): rond-point décrit par la configuration.
        """
        super().__init__()
        self.__rond_point = rond_point
        self.__bandes_densite: dict[str, QGraphicsLineItem] = {}
        self.__textes_densite: dict[str, QGraphicsTextItem] = {}
        self.__arcs_reserves: dict[str, QGraphicsPathItem] = {}
        self.__feux_entree: dict[str, QGraphicsRectItem] = {}
        self.__marqueurs: dict[str, MarqueurUsager] = {}
        demi_cote = rond_point.rayon + LONGUEUR_BRANCHE + MARGE_SCENE
        self.setSceneRect(-demi_cote, -demi_cote, 2 * demi_cote, 2 * demi_cote)
        self.setBackgroundBrush(QBrush(COULEUR_FOND))
        for branche in rond_point.branches:
            self.__dessiner_branche(branche)
        self.__dessiner_anneau()
        for branche in rond_point.branches:
            self.__dessiner_passage_pieton(branche)
            self.__dessiner_densite(branche)
            self.__dessiner_feu_entree(branche)
        for segment in rond_point.segments:
            self.__dessiner_arc_reserve(segment)

    @property
    def rond_point(self) -> RondPoint:
        """RondPoint: rond-point dessiné."""
        return self.__rond_point

    @property
    def bandes_densite(self) -> dict[str, QGraphicsLineItem]:
        """dict[str, QGraphicsLineItem]: bande colorée le long de chaque branche, selon sa densité (copie)."""
        return dict(self.__bandes_densite)

    @property
    def textes_densite(self) -> dict[str, QGraphicsTextItem]:
        """dict[str, QGraphicsTextItem]: nom et densité affichés le long de chaque branche (copie)."""
        return dict(self.__textes_densite)

    @property
    def arcs_reserves(self) -> dict[str, QGraphicsPathItem]:
        """dict[str, QGraphicsPathItem]: surlignage de chaque segment, visible quand il est réservé (copie)."""
        return dict(self.__arcs_reserves)

    @property
    def feux_entree(self) -> dict[str, QGraphicsRectItem]:
        """dict[str, QGraphicsRectItem]: feu au bord de chaque entrée, visible quand elle est bloquée (copie)."""
        return dict(self.__feux_entree)

    @property
    def marqueurs(self) -> dict[str, MarqueurUsager]:
        """dict[str, MarqueurUsager]: marqueur de chaque usager affiché, par identifiant (copie)."""
        return dict(self.__marqueurs)

    @staticmethod
    def vers_scene(position: Position) -> QPointF:
        """Convertit une position du rond-point en point de la scène.

        Args:
            position (Position): point du rond-point, en mètres, y vers le nord.

        Returns:
            QPointF: point de la scène, y vers le bas.
        """
        return QPointF(position.x, -position.y)

    def afficher_etat(self, etat: dict) -> None:
        """Met la scène à jour d'après les données d'un STATE.

        Les noms de branches ou de segments que la scène ne connaît pas sont ignorés :
        ils viendraient d'un serveur configuré avec un autre rond-point.

        Args:
            etat (dict): données du STATE (usagers, densite, segments_reserves, entrees_bloquees).
        """
        self.__afficher_usagers(etat["usagers"])
        for nom, arc in self.__arcs_reserves.items():
            arc.setVisible(nom in etat["segments_reserves"])
        for nom, feu in self.__feux_entree.items():
            feu.setVisible(nom in etat["entrees_bloquees"])
        for nom, densite in etat["densite"].items():
            if nom in self.__bandes_densite:
                self.__afficher_densite(nom, densite)

    def __afficher_usagers(self, usagers: list[dict]) -> None:
        """Place un marqueur par usager dont la position est connue, et retire ceux qui sont partis."""
        places = {usager["id"]: usager for usager in usagers if usager["x"] is not None}
        for identifiant in self.__marqueurs.keys() - places.keys():
            self.removeItem(self.__marqueurs.pop(identifiant))
        for identifiant, usager in places.items():
            if identifiant not in self.__marqueurs:
                self.__marqueurs[identifiant] = MarqueurUsager(usager["categorie"])
                self.addItem(self.__marqueurs[identifiant])
            marqueur = self.__marqueurs[identifiant]
            marqueur.setPos(self.vers_scene(Position(usager["x"], usager["y"])))
            marqueur.afficher(usager)

    def __afficher_densite(self, nom: str, densite: float) -> None:
        """Colore la bande d'une branche selon son niveau et écrit la densité sous son nom."""
        niveau = CalculateurDensite.niveau(densite)
        bande = self.__bandes_densite[nom]
        crayon = bande.pen()
        crayon.setColor(COULEURS_DENSITE[niveau])
        bande.setPen(crayon)
        texte = f"{nom}\n{round(densite * POURCENT)} % {niveau.value}"
        self.__ecrire(self.__textes_densite[nom], texte, self.__rond_point.branche(nom))

    def __dessiner_branche(self, branche: Branche) -> None:
        """Dessine la chaussée d'une branche, du centre de l'anneau jusqu'à son extrémité."""
        rayon = self.__rond_point.rayon
        crayon = QPen(COULEUR_CHAUSSEE, LARGEUR_CHAUSSEE)
        crayon.setCapStyle(Qt.PenCapStyle.FlatCap)
        self.__ajouter_ligne(branche.point(rayon), branche.point(rayon + LONGUEUR_BRANCHE), crayon)

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
        self.__ajouter_ligne(
            branche.point(distance, LARGEUR_CHAUSSEE / 2), branche.point(distance, -LARGEUR_CHAUSSEE / 2), crayon
        )

    def __dessiner_densite(self, branche: Branche) -> None:
        """Pose la bande de densité, côté entrée, et l'étiquette de la branche, côté sortie."""
        rayon = self.__rond_point.rayon
        decalage = (LARGEUR_CHAUSSEE + LARGEUR_BANDE_DENSITE) / 2
        crayon = QPen(COULEURS_DENSITE[NiveauDensite.FAIBLE], LARGEUR_BANDE_DENSITE)
        crayon.setCapStyle(Qt.PenCapStyle.FlatCap)
        self.__bandes_densite[branche.nom] = self.__ajouter_ligne(
            branche.point(rayon + LARGEUR_CHAUSSEE / 2, decalage), branche.point(rayon + LONGUEUR_BRANCHE, decalage), crayon
        )
        texte = self.addText("")
        police = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        police.setPointSize(TAILLE_TEXTE)
        texte.setFont(police)
        texte.setDefaultTextColor(COULEUR_TEXTE)
        texte.document().setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignHCenter))
        # L'étiquette garde la même taille à l'écran, quel que soit le zoom de la vue.
        texte.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        ancrage = branche.point(rayon + LONGUEUR_BRANCHE - RECUL_ETIQUETTE, -(LARGEUR_CHAUSSEE / 2 + ECART_ETIQUETTE))
        texte.setPos(self.vers_scene(ancrage))
        self.__textes_densite[branche.nom] = texte
        self.__ecrire(texte, branche.nom, branche)

    def __dessiner_feu_entree(self, branche: Branche) -> None:
        """Pose, caché, le feu de l'entrée : au bord de la voie d'entrée, à hauteur de la ligne."""
        ligne = self.__rond_point.rayon + LARGEUR_CHAUSSEE / 2
        decalage = LARGEUR_CHAUSSEE / 2 + LARGEUR_BANDE_DENSITE + ECART_FEU_ENTREE + COTE_FEU_ENTREE / 2
        feu = self.addRect(
            -COTE_FEU_ENTREE / 2, -COTE_FEU_ENTREE / 2, COTE_FEU_ENTREE, COTE_FEU_ENTREE,
            QPen(COULEUR_CONTOUR_USAGER, EPAISSEUR_CONTOUR_USAGER), QBrush(COULEUR_FEU_ENTREE),
        )
        feu.setPos(self.vers_scene(branche.point(ligne, decalage)))
        feu.setZValue(PLAN_MARQUE)
        feu.setVisible(False)
        self.__feux_entree[branche.nom] = feu

    def __dessiner_arc_reserve(self, segment: Segment) -> None:
        """Pose, caché, le surlignage d'un segment de l'anneau, de sa branche de départ à la suivante."""
        rayon = self.__rond_point.rayon
        cadre = QRectF(-rayon, -rayon, 2 * rayon, 2 * rayon)
        # Les angles de Qt tournent comme ceux du rond-point, dans le sens de circulation.
        ouverture = (segment.arrivee.angle - segment.depart.angle) % TOUR_COMPLET
        chemin = QPainterPath()
        chemin.arcMoveTo(cadre, segment.depart.angle)
        chemin.arcTo(cadre, segment.depart.angle, ouverture)
        crayon = QPen(COULEUR_RESERVE, LARGEUR_RESERVE)
        crayon.setCapStyle(Qt.PenCapStyle.FlatCap)
        arc = self.addPath(chemin, crayon)
        arc.setZValue(PLAN_MARQUE)
        arc.setVisible(False)
        self.__arcs_reserves[segment.nom] = arc

    def __ajouter_ligne(self, debut: Position, fin: Position, crayon: QPen) -> QGraphicsLineItem:
        """Trace un trait entre deux points du rond-point."""
        point_debut = self.vers_scene(debut)
        point_fin = self.vers_scene(fin)
        return self.addLine(point_debut.x(), point_debut.y(), point_fin.x(), point_fin.y(), crayon)

    @staticmethod
    def __ecrire(texte: QGraphicsTextItem, contenu: str, branche: Branche) -> None:
        """Change le contenu d'une étiquette et la place à côté de la chaussée.

        L'étiquette a une taille fixe à l'écran : elle est décalée, en pixels, pour
        s'étendre du côté opposé à la chaussée, quelle que soit l'orientation de la branche.
        """
        texte.setPlainText(contenu)
        # Sans largeur imposée, Qt ne centre pas les lignes : on prend la largeur du texte.
        texte.setTextWidth(-1)
        texte.setTextWidth(texte.document().idealWidth())
        cadre = texte.boundingRect()
        angle = math.radians(branche.angle)
        # Côté sortie, vu dans la scène où y pointe vers le bas : vecteur (sin, cos).
        decalage_x = (math.sin(angle) - 1) * cadre.width() / 2
        decalage_y = (math.cos(angle) - 1) * cadre.height() / 2
        texte.setTransform(QTransform.fromTranslate(decalage_x, decalage_y))
