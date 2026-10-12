"""Scène 2D du rond-point : la chaussée d'après la configuration, puis l'état reçu du serveur."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QFontDatabase,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QResizeEvent,
    QTextOption,
    QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QWidget,
)

from cherrypie.ihm.style import (
    ARRONDI_USAGER,
    COTE_FEU_ENTREE,
    COULEUR_BORDURE,
    COULEUR_CHAUSSEE,
    COULEUR_CONTOUR_USAGER,
    COULEUR_FEU_ENTREE,
    COULEUR_FLECHE,
    COULEUR_FOND,
    COULEUR_GYROPHARE,
    COULEUR_HALO_VP,
    COULEUR_ILOT,
    COULEUR_MARQUAGE,
    COULEUR_REFUGE,
    COULEUR_RESERVE,
    COULEUR_TERRE_PLEIN,
    COULEUR_TEXTE,
    COULEURS_CATEGORIE,
    COULEURS_CONSIGNE,
    COULEURS_DENSITE,
    DISTANCE_FLECHE,
    ECART_BARRIERE_PASSAGE,
    ECART_ETIQUETTE,
    ECART_FEU_ENTREE,
    EPAISSEUR_BARRE_ENTREE,
    EPAISSEUR_BORDURE,
    EPAISSEUR_CEDEZ_LE_PASSAGE,
    EPAISSEUR_CONTOUR_CONSIGNE,
    EPAISSEUR_CONTOUR_USAGER,
    EPAISSEUR_LIGNE_DE_RIVE,
    EPAISSEUR_SEPARATION_VOIES,
    GABARIT_GYROPHARE,
    GABARITS_CATEGORIE,
    LARGEUR_BANDE_DENSITE,
    LARGEUR_FLECHE,
    LARGEUR_PASSAGE_PIETON,
    LONGUEUR_FLECHE,
    MARGE_SCENE,
    MOTIF_CEDEZ_LE_PASSAGE,
    MOTIF_PASSAGE_PIETON,
    MOTIF_SEPARATION_VOIES,
    NOMS_CATEGORIE,
    PART_VOIE_RESERVEE,
    PLAN_MARQUAGE,
    PLAN_MARQUE,
    PLAN_USAGER,
    PLAN_VP,
    POINTS_NEZ_TERRE_PLEIN,
    RAYON_HALO_VP,
    RECUL_ETIQUETTE,
    TAILLE_TEXTE,
)
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import Branche, RondPoint, Segment
from cherrypie.modele.usager import KMH, Pieton, VehiculePrioritaire
from cherrypie.serveur.densite import CalculateurDensite, NiveauDensite

POURCENT = 100
# Un cap compté depuis le nord devient une rotation Qt, comptée depuis l'est dans le sens
# des aiguilles d'une montre : on retire ce quart de tour.
QUART_DE_TOUR = 90.0
# Côté minimal de la vue, en pixels, pour que les usagers restent visibles.
TAILLE_MIN_VUE = 400


class MarqueurUsager(QGraphicsPathItem):
    """Silhouette d'un usager, à l'échelle de son gabarit, tournée dans son sens de marche.

    Un véhicule est un rectangle arrondi dont l'avant est sur sa position : arrêté sur la
    ligne d'entrée, son pare-chocs touche la ligne. Un piéton est un disque. Le contour
    prend la couleur de la consigne suivie. Le VP a en plus un halo et une rampe lumineuse,
    et passe au-dessus des autres usagers.
    """

    def __init__(self, categorie: str) -> None:
        """Crée la silhouette d'un usager.

        Args:
            categorie (str): catégorie de l'usager (ex. "voiture").
        """
        super().__init__()
        self.__categorie = categorie
        longueur, largeur = GABARITS_CATEGORIE[categorie]
        silhouette = QPainterPath()
        if categorie == Pieton.CATEGORIE:
            silhouette.addEllipse(QPointF(0.0, 0.0), longueur / 2, largeur / 2)
        else:
            carrosserie = QRectF(-longueur, -largeur / 2, longueur, largeur)
            silhouette.addRoundedRect(carrosserie, ARRONDI_USAGER, ARRONDI_USAGER)
        self.setPath(silhouette)
        self.setBrush(QBrush(COULEURS_CATEGORIE[categorie]))
        self.__halo: QGraphicsEllipseItem | None = None
        if categorie == VehiculePrioritaire.CATEGORIE:
            self.__halo = QGraphicsEllipseItem(
                -longueur / 2 - RAYON_HALO_VP, -RAYON_HALO_VP, 2 * RAYON_HALO_VP, 2 * RAYON_HALO_VP, self
            )
            self.__halo.setPen(QPen(Qt.PenStyle.NoPen))
            self.__halo.setBrush(QBrush(COULEUR_HALO_VP))
            self.__halo.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent)
            profondeur, travers = GABARIT_GYROPHARE
            gyrophare = QGraphicsRectItem(-longueur / 2 - profondeur / 2, -travers / 2, profondeur, travers, self)
            gyrophare.setPen(QPen(Qt.PenStyle.NoPen))
            gyrophare.setBrush(QBrush(COULEUR_GYROPHARE))
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

    def afficher(self, usager: dict, libelles: dict[str, str]) -> None:
        """Oriente la silhouette, affiche la consigne par le contour et le détail dans l'infobulle.

        Args:
            usager (dict): description de l'usager, telle que le STATE la transmet.
            libelles (dict[str, str]): nom de rue de chaque branche, pour l'infobulle.
        """
        if usager["cap"] is not None:
            self.setRotation(usager["cap"] - QUART_DE_TOUR)
        consigne = usager["consigne"]
        if consigne in COULEURS_CONSIGNE:
            self.setPen(QPen(COULEURS_CONSIGNE[consigne], EPAISSEUR_CONTOUR_CONSIGNE))
        else:
            self.setPen(QPen(COULEUR_CONTOUR_USAGER, EPAISSEUR_CONTOUR_USAGER))
        entree = libelles.get(usager["entree"], usager["entree"])
        sortie = libelles.get(usager["sortie"], usager["sortie"])
        detail = (
            f"{usager['id']} ({NOMS_CATEGORIE[self.__categorie]}) : de {entree} vers {sortie}, "
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
        """Dessine la chaussée, les marquages et les étiquettes des branches.

        Les marques de régulation (voie réservée, entrées temporisées) sont posées tout
        de suite, cachées, et n'apparaissent que quand un STATE les signale.

        Args:
            rond_point (RondPoint): rond-point décrit par la configuration.
        """
        super().__init__()
        self.__rond_point = rond_point
        self.__libelles = {branche.nom: branche.libelle for branche in rond_point.branches}
        self.__bandes_densite: dict[str, QGraphicsLineItem] = {}
        self.__textes_densite: dict[str, QGraphicsTextItem] = {}
        self.__arcs_reserves: dict[str, QGraphicsPathItem] = {}
        self.__entrees_temporisees: dict[str, QGraphicsItemGroup] = {}
        self.__passages_fermes: dict[tuple[str, str], QGraphicsLineItem] = {}
        self.__marqueurs: dict[str, MarqueurUsager] = {}
        self.setBackgroundBrush(QBrush(COULEUR_FOND))
        for branche in rond_point.branches:
            self.__dessiner_chaussee(branche)
        self.__dessiner_anneau()
        for branche in rond_point.branches:
            self.__dessiner_terre_plein(branche)
            self.__dessiner_marquages(branche)
            self.__dessiner_densite(branche)
            self.__poser_entree_temporisee(branche)
            self.__poser_barrieres_du_passage(branche)
        for segment in rond_point.segments:
            self.__poser_voie_reservee(segment)
        # Le cadre se calcule avant les étiquettes : leur taille est en pixels, pas en mètres.
        self.setSceneRect(self.itemsBoundingRect().adjusted(-MARGE_SCENE, -MARGE_SCENE, MARGE_SCENE, MARGE_SCENE))
        for branche in rond_point.branches:
            self.__poser_etiquette(branche)

    @property
    def rond_point(self) -> RondPoint:
        """RondPoint: rond-point dessiné."""
        return self.__rond_point

    @property
    def bandes_densite(self) -> dict[str, QGraphicsLineItem]:
        """dict[str, QGraphicsLineItem]: bande le long de chaque chaussée d'entrée, selon la densité (copie)."""
        return dict(self.__bandes_densite)

    @property
    def textes_densite(self) -> dict[str, QGraphicsTextItem]:
        """dict[str, QGraphicsTextItem]: nom de rue et densité affichés le long de chaque branche (copie)."""
        return dict(self.__textes_densite)

    @property
    def arcs_reserves(self) -> dict[str, QGraphicsPathItem]:
        """dict[str, QGraphicsPathItem]: voie intérieure de chaque segment, surlignée s'il est réservé (copie)."""
        return dict(self.__arcs_reserves)

    @property
    def entrees_temporisees(self) -> dict[str, QGraphicsItemGroup]:
        """dict[str, QGraphicsItemGroup]: barre et feu de chaque entrée, visibles si elle est temporisée (copie)."""
        return dict(self.__entrees_temporisees)

    @property
    def passages_fermes(self) -> dict[tuple[str, str], QGraphicsLineItem]:
        """dict[tuple[str, str], QGraphicsLineItem]: barrière de chaque chaussée, visible si un piéton la traverse (copie).

        Les clés sont (branche, "entree") et (branche, "sortie").
        """
        return dict(self.__passages_fermes)

    @property
    def marqueurs(self) -> dict[str, MarqueurUsager]:
        """dict[str, MarqueurUsager]: silhouette de chaque usager affiché, par identifiant (copie)."""
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
        for nom, marque in self.__entrees_temporisees.items():
            marque.setVisible(nom in etat["entrees_bloquees"])
        fermes = {(ferme["branche"], ferme["chaussee"]) for ferme in etat["passages_fermes"]}
        for cle, barriere in self.__passages_fermes.items():
            barriere.setVisible(cle in fermes)
        for nom, densite in etat["densite"].items():
            if nom in self.__bandes_densite:
                self.__afficher_densite(nom, densite)

    def __afficher_usagers(self, usagers: list[dict]) -> None:
        """Place une silhouette par usager dont la position est connue, et retire celles des usagers partis."""
        places = {usager["id"]: usager for usager in usagers if usager["x"] is not None}
        for identifiant in self.__marqueurs.keys() - places.keys():
            self.removeItem(self.__marqueurs.pop(identifiant))
        for identifiant, usager in places.items():
            if identifiant not in self.__marqueurs:
                self.__marqueurs[identifiant] = MarqueurUsager(usager["categorie"])
                self.addItem(self.__marqueurs[identifiant])
            marqueur = self.__marqueurs[identifiant]
            marqueur.setPos(self.vers_scene(Position(usager["x"], usager["y"])))
            marqueur.afficher(usager, self.__libelles)

    def __afficher_densite(self, nom: str, densite: float) -> None:
        """Colore la bande de la chaussée d'entrée selon son niveau et écrit la densité sous le nom de rue."""
        niveau = CalculateurDensite.niveau(densite)
        bande = self.__bandes_densite[nom]
        crayon = bande.pen()
        crayon.setColor(COULEURS_DENSITE[niveau])
        bande.setPen(crayon)
        branche = self.__rond_point.branche(nom)
        self.__ecrire(self.__textes_densite[nom], branche, f"{round(densite * POURCENT)} % ({niveau.value})")

    def __dessiner_chaussee(self, branche: Branche) -> None:
        """Dessine la chaussée d'une branche, ses deux sens compris, à partir de l'anneau qui la recouvre."""
        debut = self.__rond_point.rayon_ilot
        fin = self.__rond_point.rayon_bord + self.__rond_point.longueur_branche
        largeur = branche.demi_largeur
        coins = [(debut, largeur), (fin, largeur), (fin, -largeur), (debut, -largeur)]
        self.__ajouter_polygone(branche, coins, QBrush(COULEUR_CHAUSSEE), QPen(Qt.PenStyle.NoPen))

    def __dessiner_anneau(self) -> None:
        """Dessine l'anneau, l'îlot central bordé, et la séparation entre les deux voies."""
        bord = self.__rond_point.rayon_bord
        ilot = self.__rond_point.rayon_ilot
        axe = self.__rond_point.rayon
        self.addEllipse(-bord, -bord, 2 * bord, 2 * bord, QPen(Qt.PenStyle.NoPen), QBrush(COULEUR_CHAUSSEE))
        bordure = QPen(COULEUR_BORDURE, EPAISSEUR_BORDURE)
        self.addEllipse(-ilot, -ilot, 2 * ilot, 2 * ilot, bordure, QBrush(COULEUR_ILOT))
        separation = QPen(COULEUR_MARQUAGE, EPAISSEUR_SEPARATION_VOIES)
        separation.setDashPattern(MOTIF_SEPARATION_VOIES)
        voies = self.addEllipse(-axe, -axe, 2 * axe, 2 * axe, separation, QBrush(Qt.BrushStyle.NoBrush))
        voies.setZValue(PLAN_MARQUAGE)

    def __dessiner_terre_plein(self, branche: Branche) -> None:
        """Dessine le terre-plein entre les deux chaussées, avec un nez arrondi au bord de l'anneau."""
        demi = branche.terre_plein / 2
        centre_du_nez = self.__rond_point.rayon_bord + demi
        fin = self.__rond_point.rayon_bord + self.__rond_point.longueur_branche
        nez = []
        for rang in range(POINTS_NEZ_TERRE_PLEIN + 1):
            angle = math.radians(-QUART_DE_TOUR + 2 * QUART_DE_TOUR * rang / POINTS_NEZ_TERRE_PLEIN)
            nez.append((centre_du_nez - demi * math.cos(angle), demi * math.sin(angle)))
        coins = [*nez, (fin, demi), (fin, -demi)]
        self.__ajouter_polygone(branche, coins, QBrush(COULEUR_TERRE_PLEIN), QPen(COULEUR_BORDURE, EPAISSEUR_BORDURE))

    def __dessiner_marquages(self, branche: Branche) -> None:
        """Peint les lignes de rive, la ligne de cédez-le-passage, le passage piéton et les flèches."""
        bord = self.__rond_point.rayon_bord
        fin = bord + self.__rond_point.longueur_branche
        exterieur = branche.demi_largeur
        interieur = branche.terre_plein / 2
        # Les lignes de rive partent de l'endroit où le bord de la chaussée rencontre l'anneau.
        depart_rive = math.sqrt(max(0.0, bord * bord - exterieur * exterieur))
        rive = QPen(COULEUR_MARQUAGE, EPAISSEUR_LIGNE_DE_RIVE)
        for cote in (1, -1):
            self.__ajouter_ligne(branche, (depart_rive, cote * exterieur), (fin, cote * exterieur), rive)
        cedez = QPen(COULEUR_MARQUAGE, EPAISSEUR_CEDEZ_LE_PASSAGE)
        cedez.setDashPattern(MOTIF_CEDEZ_LE_PASSAGE)
        cedez.setCapStyle(Qt.PenCapStyle.FlatCap)
        self.__ajouter_ligne(branche, (bord, interieur), (bord, exterieur), cedez)
        passage = bord + branche.passage_pieton
        zebra = QPen(COULEUR_MARQUAGE, LARGEUR_PASSAGE_PIETON)
        zebra.setDashPattern(MOTIF_PASSAGE_PIETON)
        zebra.setCapStyle(Qt.PenCapStyle.FlatCap)
        for cote in (1, -1):
            self.__ajouter_ligne(branche, (passage, cote * interieur), (passage, cote * exterieur), zebra)
        refuge = QPen(COULEUR_REFUGE, LARGEUR_PASSAGE_PIETON)
        refuge.setCapStyle(Qt.PenCapStyle.FlatCap)
        self.__ajouter_ligne(branche, (passage, interieur), (passage, -interieur), refuge)
        self.__peindre_fleche(branche, bord + DISTANCE_FLECHE, branche.decalage_voie, vers_le_centre=True)
        self.__peindre_fleche(branche, bord + DISTANCE_FLECHE, -branche.decalage_voie, vers_le_centre=False)

    def __peindre_fleche(self, branche: Branche, distance: float, decalage: float, vers_le_centre: bool) -> None:
        """Peint une flèche au milieu d'une chaussée, dans son sens de circulation."""
        sens = -1.0 if vers_le_centre else 1.0
        pointe = distance + sens * LONGUEUR_FLECHE / 2
        talon = distance - sens * LONGUEUR_FLECHE / 2
        coins = [(pointe, decalage), (talon, decalage + LARGEUR_FLECHE / 2), (talon, decalage - LARGEUR_FLECHE / 2)]
        fleche = self.__ajouter_polygone(branche, coins, QBrush(COULEUR_FLECHE), QPen(Qt.PenStyle.NoPen))
        fleche.setZValue(PLAN_MARQUAGE)

    def __dessiner_densite(self, branche: Branche) -> None:
        """Pose la bande de densité le long du bord de la chaussée d'entrée."""
        bord = self.__rond_point.rayon_bord
        decalage = branche.demi_largeur + LARGEUR_BANDE_DENSITE / 2
        crayon = QPen(COULEURS_DENSITE[NiveauDensite.FAIBLE], LARGEUR_BANDE_DENSITE)
        crayon.setCapStyle(Qt.PenCapStyle.FlatCap)
        fin = bord + self.__rond_point.longueur_branche
        self.__bandes_densite[branche.nom] = self.__ajouter_ligne(branche, (bord, decalage), (fin, decalage), crayon)

    def __poser_entree_temporisee(self, branche: Branche) -> None:
        """Pose, cachés, la barre en travers de la chaussée d'entrée et le feu à côté, sur la ligne."""
        ligne = self.__rond_point.rayon_bord
        crayon = QPen(COULEUR_FEU_ENTREE, EPAISSEUR_BARRE_ENTREE)
        crayon.setCapStyle(Qt.PenCapStyle.FlatCap)
        barre = self.__ajouter_ligne(branche, (ligne, branche.terre_plein / 2), (ligne, branche.demi_largeur), crayon)
        decalage = branche.demi_largeur + LARGEUR_BANDE_DENSITE + ECART_FEU_ENTREE + COTE_FEU_ENTREE / 2
        feu = self.addRect(
            -COTE_FEU_ENTREE / 2, -COTE_FEU_ENTREE / 2, COTE_FEU_ENTREE, COTE_FEU_ENTREE,
            QPen(COULEUR_CONTOUR_USAGER, EPAISSEUR_CONTOUR_USAGER), QBrush(COULEUR_FEU_ENTREE),
        )
        feu.setPos(self.vers_scene(branche.point(ligne, decalage)))
        groupe = self.createItemGroup([barre, feu])
        groupe.setZValue(PLAN_MARQUE)
        groupe.setVisible(False)
        self.__entrees_temporisees[branche.nom] = groupe

    def __poser_barrieres_du_passage(self, branche: Branche) -> None:
        """Pose, cachées, les barrières des deux chaussées, du côté où arrivent les véhicules."""
        passage = self.__rond_point.rayon_bord + branche.passage_pieton
        recul = LARGEUR_PASSAGE_PIETON / 2 + ECART_BARRIERE_PASSAGE
        crayon = QPen(COULEUR_FEU_ENTREE, EPAISSEUR_BARRE_ENTREE)
        crayon.setCapStyle(Qt.PenCapStyle.FlatCap)
        interieur, exterieur = branche.terre_plein / 2, branche.demi_largeur
        # On arrive sur la chaussée d'entrée par le bout de la branche, sur celle de sortie par l'anneau.
        for chaussee, distance, cote in (("entree", passage + recul, 1), ("sortie", passage - recul, -1)):
            barriere = self.__ajouter_ligne(branche, (distance, cote * interieur), (distance, cote * exterieur), crayon)
            barriere.setZValue(PLAN_MARQUE)
            barriere.setVisible(False)
            self.__passages_fermes[(branche.nom, chaussee)] = barriere

    def __poser_voie_reservee(self, segment: Segment) -> None:
        """Pose, caché, le surlignage de la voie intérieure d'un segment, celle que suit le VP."""
        rayon = self.__rond_point.rayon_voie_interieure
        cadre = QRectF(-rayon, -rayon, 2 * rayon, 2 * rayon)
        # Les angles de Qt tournent comme ceux du rond-point, dans le sens de circulation.
        chemin = QPainterPath()
        chemin.arcMoveTo(cadre, segment.depart.angle)
        chemin.arcTo(cadre, segment.depart.angle, segment.ouverture)
        crayon = QPen(COULEUR_RESERVE, self.__rond_point.largeur_voie_anneau * PART_VOIE_RESERVEE)
        crayon.setCapStyle(Qt.PenCapStyle.FlatCap)
        arc = self.addPath(chemin, crayon)
        arc.setZValue(PLAN_MARQUE)
        arc.setVisible(False)
        self.__arcs_reserves[segment.nom] = arc

    def __poser_etiquette(self, branche: Branche) -> None:
        """Pose l'étiquette de la branche, côté sortie, près de son extrémité."""
        texte = self.addText("")
        police = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        police.setPointSize(TAILLE_TEXTE)
        texte.setFont(police)
        texte.setDefaultTextColor(COULEUR_TEXTE)
        texte.document().setDefaultTextOption(QTextOption(Qt.AlignmentFlag.AlignHCenter))
        # L'étiquette garde la même taille à l'écran, quel que soit le zoom de la vue.
        texte.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        extremite = self.__rond_point.rayon_bord + self.__rond_point.longueur_branche
        ancrage = branche.point(extremite - RECUL_ETIQUETTE, -(branche.demi_largeur + ECART_ETIQUETTE))
        texte.setPos(self.vers_scene(ancrage))
        self.__textes_densite[branche.nom] = texte
        self.__ecrire(texte, branche, "")

    def __ajouter_polygone(
        self, branche: Branche, coins: list[tuple[float, float]], pinceau: QBrush, crayon: QPen
    ) -> QGraphicsItem:
        """Ajoute un polygone décrit dans le repère de la branche : (distance au centre, écart à l'axe)."""
        polygone = QPolygonF([self.vers_scene(branche.point(distance, ecart)) for distance, ecart in coins])
        return self.addPolygon(polygone, crayon, pinceau)

    def __ajouter_ligne(
        self, branche: Branche, debut: tuple[float, float], fin: tuple[float, float], crayon: QPen
    ) -> QGraphicsLineItem:
        """Trace un trait décrit dans le repère de la branche : (distance au centre, écart à l'axe)."""
        point_debut = self.vers_scene(branche.point(*debut))
        point_fin = self.vers_scene(branche.point(*fin))
        ligne = self.addLine(point_debut.x(), point_debut.y(), point_fin.x(), point_fin.y(), crayon)
        ligne.setZValue(PLAN_MARQUAGE)
        return ligne

    @staticmethod
    def __ecrire(texte: QGraphicsTextItem, branche: Branche, densite: str) -> None:
        """Écrit le nom de rue et la densité, et place l'étiquette à côté de la chaussée.

        L'étiquette a une taille fixe à l'écran : elle est décalée, en pixels, pour
        s'étendre du côté opposé à la chaussée, quelle que soit l'orientation de la branche.
        """
        texte.setPlainText(f"{branche.libelle}\n{densite}" if densite else branche.libelle)
        # Sans largeur imposée, Qt ne centre pas les lignes : on prend la largeur du texte.
        texte.setTextWidth(-1)
        texte.setTextWidth(texte.document().idealWidth())
        cadre = texte.boundingRect()
        angle = math.radians(branche.angle)
        # Côté sortie, vu dans la scène où y pointe vers le bas : vecteur (sin, cos).
        decalage_x = (math.sin(angle) - 1) * cadre.width() / 2
        decalage_y = (math.cos(angle) - 1) * cadre.height() / 2
        texte.setTransform(QTransform.fromTranslate(decalage_x, decalage_y))


class VueRondPoint(QGraphicsView):
    """Vue de la scène, qui montre tout le rond-point quelle que soit la taille de la fenêtre."""

    def __init__(self, scene: SceneRondPoint, parent: QWidget | None = None) -> None:
        """Crée la vue, lissée et sans barres de défilement.

        Args:
            scene (SceneRondPoint): scène affichée.
            parent (QWidget | None): widget parent.
        """
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setBackgroundBrush(QBrush(COULEUR_FOND))
        self.setMinimumSize(TAILLE_MIN_VUE, TAILLE_MIN_VUE)

    def resizeEvent(self, evenement: QResizeEvent) -> None:
        """Recadre la scène entière à chaque changement de taille de la vue.

        Args:
            evenement (QResizeEvent): changement de taille reçu de Qt.
        """
        super().resizeEvent(evenement)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
