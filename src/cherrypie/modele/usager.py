"""Usagers du rond-point : la classe mère Usager et ses cinq sous-classes."""

from __future__ import annotations

from cherrypie.commun.protocole import CodeNotification
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import Trajectoire

# 1 km/h en m/s : les vitesses se lisent en km/h, les calculs se font en m/s.
KMH = 1 / 3.6
# Part de sa vitesse maximale que garde un usager qui dégage la voie.
FACTEUR_RALENTISSEMENT = 0.5
# Écart pris sur la droite de sa voie pour laisser passer un véhicule prioritaire, en mètres.
DECALAGE_DEGAGEMENT = 2.0
CHAMPS_OBLIGATOIRES = {"id", "categorie", "entree", "sortie"}


class Usager:
    """Usager connecté au rond-point.

    Classe mère, jamais instanciée directement. Chaque sous-classe redéfinit sa
    catégorie, sa vitesse maximale et, si besoin, les consignes qu'elle suit.
    Le client fait avancer son usager ; le serveur met à jour le sien à chaque POS.
    """

    CATEGORIE = ""
    VITESSE_MAX = 0.0
    CONSIGNES_SUIVIES = frozenset(CodeNotification)

    def __init__(self, identifiant: str, branche_entree: str, branche_sortie: str) -> None:
        """Crée un usager à l'arrêt, dont la position n'est pas encore connue.

        Args:
            identifiant (str): identifiant unique sur le réseau (ex. "voiture_12").
            branche_entree (str): branche par laquelle il arrive.
            branche_sortie (str): branche par laquelle il repart.

        Raises:
            TypeError: si l'on instancie directement Usager.
            ValueError: si l'identifiant ou l'une des branches est vide.
        """
        if type(self) is Usager:
            raise TypeError("Usager est une classe mère : il faut instancier l'une de ses sous-classes")
        for description, valeur in (
            ("l'identifiant", identifiant),
            ("la branche d'entrée", branche_entree),
            ("la branche de sortie", branche_sortie),
        ):
            if not isinstance(valeur, str) or not valeur:
                raise ValueError(f"{description} doit être un texte non vide (reçu : {valeur!r})")
        self.__identifiant = identifiant
        self.__branche_entree = branche_entree
        self.__branche_sortie = branche_sortie
        self.__position: Position | None = None
        self.__vitesse = 0.0
        self.__segment: str | None = None
        self.__consigne: CodeNotification | None = None

    @classmethod
    def depuis_dict(cls, contenu: dict) -> Usager:
        """Recrée un usager de la bonne sous-classe à partir d'un dictionnaire.

        Seuls « id », « categorie », « entree » et « sortie » sont obligatoires :
        c'est ce que le serveur apprend au HELLO. Les autres champs de vers_dict()
        sont repris quand ils sont présents.

        Args:
            contenu (dict): dictionnaire au format de vers_dict().

        Returns:
            Usager: une instance de la sous-classe qui correspond à la catégorie.

        Raises:
            TypeError: si le contenu n'est pas un dictionnaire ou si une valeur n'a pas le bon type.
            ValueError: si un champ obligatoire manque, si la catégorie est inconnue
                ou si une valeur est invalide.
        """
        if not isinstance(contenu, dict):
            raise TypeError("un usager se décrit par un dictionnaire")
        manquants = CHAMPS_OBLIGATOIRES - contenu.keys()
        if manquants:
            raise ValueError(f"champs manquants pour créer un usager : {', '.join(sorted(manquants))}")
        classe = CLASSES_PAR_CATEGORIE.get(contenu["categorie"])
        if classe is None:
            raise ValueError(f"catégorie d'usager inconnue : {contenu['categorie']!r}")
        usager = classe(contenu["id"], contenu["entree"], contenu["sortie"])
        if contenu.get("x") is not None and contenu.get("y") is not None:
            usager.position = Position(contenu["x"], contenu["y"])
        usager.vitesse = contenu.get("vitesse", 0.0)
        usager.segment = contenu.get("segment")
        if contenu.get("consigne") is not None:
            usager.reagir(CodeNotification(contenu["consigne"]))
        return usager

    @property
    def identifiant(self) -> str:
        """str: identifiant unique sur le réseau."""
        return self.__identifiant

    @property
    def branche_entree(self) -> str:
        """str: branche par laquelle l'usager arrive."""
        return self.__branche_entree

    @property
    def branche_sortie(self) -> str:
        """str: branche par laquelle l'usager repart."""
        return self.__branche_sortie

    @property
    def position(self) -> Position | None:
        """Position | None: dernière position connue, None tant que l'usager n'a pas bougé."""
        return self.__position

    @position.setter
    def position(self, valeur: Position) -> None:
        """Enregistre une nouvelle position.

        Raises:
            TypeError: si la valeur n'est pas une Position.
        """
        if not isinstance(valeur, Position):
            raise TypeError(f"position invalide : {valeur!r}")
        self.__position = valeur

    @property
    def vitesse(self) -> float:
        """float: vitesse actuelle, en m/s."""
        return self.__vitesse

    @vitesse.setter
    def vitesse(self, valeur: float) -> None:
        """Enregistre une nouvelle vitesse.

        Raises:
            TypeError: si la valeur n'est pas un nombre.
            ValueError: si elle est négative ou dépasse la vitesse maximale de la catégorie.
        """
        if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
            raise TypeError(f"vitesse invalide : {valeur!r}")
        # Écrit ainsi, le test refuse aussi NaN, pour lequel toute comparaison est fausse.
        if not 0 <= valeur <= self.VITESSE_MAX:
            raise ValueError(
                f"vitesse de {valeur} m/s hors limites pour la catégorie {self.CATEGORIE} "
                f"(maximum {self.VITESSE_MAX:.1f} m/s)"
            )
        self.__vitesse = float(valeur)

    @property
    def segment(self) -> str | None:
        """str | None: segment de l'anneau occupé (ex. "N-O"), None hors de l'anneau."""
        return self.__segment

    @segment.setter
    def segment(self, valeur: str | None) -> None:
        """Enregistre le segment occupé, ou None quand l'usager n'est pas sur l'anneau.

        Raises:
            ValueError: si le nom de segment est vide ou n'est pas un texte.
        """
        if valeur is not None and (not isinstance(valeur, str) or not valeur):
            raise ValueError(f"segment invalide : {valeur!r}")
        self.__segment = valeur

    @property
    def consigne(self) -> CodeNotification | None:
        """CodeNotification | None: consigne en cours, None si l'usager circule librement."""
        return self.__consigne

    def reagir(self, code: CodeNotification) -> bool:
        """Applique une consigne du serveur, si la catégorie de l'usager la suit.

        Args:
            code (CodeNotification): consigne reçue dans un message NOTIF.

        Returns:
            bool: True si la consigne est appliquée, False si elle ne concerne pas cet usager.
        """
        if code not in self.CONSIGNES_SUIVIES:
            return False
        # OK_PASSER lève la consigne précédente : l'usager reprend sa marche normale.
        self.__consigne = None if code is CodeNotification.OK_PASSER else code
        return True

    def vitesse_autorisee(self) -> float:
        """Donne la vitesse maximale permise par la consigne en cours.

        ATTENDEZ ne ralentit pas l'usager : il avance jusqu'à la ligne d'entrée et
        s'y arrête, ce qui dépend de sa trajectoire et non de sa vitesse.

        Returns:
            float: vitesse en m/s, réduite pendant un DEGAGEZ.
        """
        if self.__consigne is CodeNotification.DEGAGEZ:
            return self.VITESSE_MAX * FACTEUR_RALENTISSEMENT
        return self.VITESSE_MAX

    def decalage_lateral(self) -> float:
        """Donne l'écart à prendre sur la droite de sa voie.

        Returns:
            float: écart en mètres, non nul pendant un DEGAGEZ ou un CHANGEZ_VOIE.
        """
        if self.__consigne in (CodeNotification.DEGAGEZ, CodeNotification.CHANGEZ_VOIE):
            return DECALAGE_DEGAGEMENT
        return 0.0

    def calculer_trajectoire(self, rond_point: RondPoint) -> Trajectoire:
        """Calcule le chemin de l'usager : approche, anneau, puis sortie.

        Args:
            rond_point (RondPoint): rond-point traversé.

        Returns:
            Trajectoire: la trajectoire de l'usager.

        Raises:
            BrancheInconnueError: si sa branche d'entrée ou de sortie n'existe pas.
        """
        return Trajectoire.pour_vehicule(rond_point, self.__branche_entree, self.__branche_sortie)

    def vers_dict(self) -> dict:
        """Convertit l'usager en dictionnaire prêt pour json.dumps.

        Returns:
            dict: identité, trajet, position (x et y à None si elle est inconnue),
                vitesse, segment et consigne.
        """
        return {
            "id": self.__identifiant,
            "categorie": self.CATEGORIE,
            "entree": self.__branche_entree,
            "sortie": self.__branche_sortie,
            "x": None if self.__position is None else self.__position.x,
            "y": None if self.__position is None else self.__position.y,
            "vitesse": self.__vitesse,
            "segment": self.__segment,
            "consigne": None if self.__consigne is None else self.__consigne.value,
        }


class Voiture(Usager):
    """Voiture : suit toutes les consignes."""

    CATEGORIE = "voiture"
    VITESSE_MAX = 30 * KMH


class Moto(Usager):
    """Moto : mêmes règles qu'une voiture dans le rond-point."""

    CATEGORIE = "moto"
    VITESSE_MAX = 30 * KMH


class Trottinette(Usager):
    """Trottinette électrique, bridée à 20 km/h."""

    CATEGORIE = "trottinette"
    VITESSE_MAX = 20 * KMH


class Pieton(Usager):
    """Piéton : il ne prend pas l'anneau, il traverse une branche sur le passage piéton.

    Seules les consignes d'attente le concernent : on lui demande d'attendre pour
    traverser, puis on l'autorise à repartir.
    """

    CATEGORIE = "pieton"
    VITESSE_MAX = 5 * KMH
    CONSIGNES_SUIVIES = frozenset({CodeNotification.ATTENDEZ, CodeNotification.OK_PASSER})

    def __init__(self, identifiant: str, branche_entree: str, branche_sortie: str) -> None:
        """Crée un piéton.

        Args:
            identifiant (str): identifiant unique sur le réseau (ex. "pieton_4").
            branche_entree (str): branche qu'il traverse.
            branche_sortie (str): même branche que l'entrée.

        Raises:
            ValueError: si une valeur est vide, ou si l'entrée et la sortie diffèrent.
        """
        super().__init__(identifiant, branche_entree, branche_sortie)
        if branche_sortie != branche_entree:
            raise ValueError(
                "un piéton traverse une seule branche : l'entrée et la sortie doivent être identiques "
                f"(reçu : {branche_entree} et {branche_sortie})"
            )

    def calculer_trajectoire(self, rond_point: RondPoint) -> Trajectoire:
        """Calcule la traversée de sa branche sur le passage piéton.

        Args:
            rond_point (RondPoint): rond-point traversé.

        Returns:
            Trajectoire: la trajectoire du piéton.

        Raises:
            BrancheInconnueError: si sa branche n'existe pas.
        """
        return Trajectoire.pour_pieton(rond_point, self.branche_entree)


class VehiculePrioritaire(Usager):
    """Véhicule prioritaire (pompiers, SAMU, police) : c'est lui qu'on laisse passer.

    Il ignore donc toutes les consignes.
    """

    CATEGORIE = "vp"
    VITESSE_MAX = 40 * KMH
    CONSIGNES_SUIVIES = frozenset()


CLASSES_PAR_CATEGORIE = {
    classe.CATEGORIE: classe for classe in (Voiture, Moto, Trottinette, Pieton, VehiculePrioritaire)
}
