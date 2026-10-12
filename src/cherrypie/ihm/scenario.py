"""Scénario de démonstration : une suite de lancements d'usagers, avec leurs délais, enregistrable en JSON."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from cherrypie.commun.erreurs import ScenarioInvalideError
from cherrypie.modele.usager import CLASSES_PAR_CATEGORIE, Pieton

VERSION_FORMAT = 1
CHAMPS_LIGNE = ("categorie", "entree", "sortie", "nombre", "delai")


@dataclass(frozen=True)
class LigneScenario:
    """Une ligne du scénario : des usagers d'un même trajet, lancés ensemble.

    Attributes:
        categorie (str): catégorie des usagers (ex. "voiture").
        entree (str): identifiant de la branche d'entrée.
        sortie (str): identifiant de la branche de sortie, la même que l'entrée pour un piéton.
        nombre (int): nombre d'usagers lancés, au moins 1.
        delai (float): attente avant ce lancement, depuis celui de la ligne précédente, en secondes.
    """

    categorie: str
    entree: str
    sortie: str
    nombre: int
    delai: float

    def __post_init__(self) -> None:
        """Refuse une ligne incohérente.

        Raises:
            ScenarioInvalideError: si la catégorie est inconnue, si le nombre ou le délai
                n'a pas de sens, ou si un piéton n'a pas la même entrée et la même sortie.
        """
        if self.categorie not in CLASSES_PAR_CATEGORIE:
            raise ScenarioInvalideError(f"catégorie d'usager inconnue : {self.categorie!r}")
        if isinstance(self.nombre, bool) or not isinstance(self.nombre, int) or self.nombre < 1:
            raise ScenarioInvalideError(f"le nombre d'usagers doit être un entier positif (reçu : {self.nombre!r})")
        if isinstance(self.delai, bool) or not isinstance(self.delai, (int, float)) or not math.isfinite(self.delai):
            raise ScenarioInvalideError(f"le délai doit être un nombre (reçu : {self.delai!r})")
        if self.delai < 0:
            raise ScenarioInvalideError(f"le délai ne peut pas être négatif (reçu : {self.delai})")
        if self.categorie == Pieton.CATEGORIE and self.entree != self.sortie:
            raise ScenarioInvalideError("un piéton traverse une seule branche : l'entrée et la sortie sont la même")

    def vers_dict(self) -> dict:
        """Convertit la ligne en dictionnaire prêt pour json.dumps.

        Returns:
            dict: catégorie, entrée, sortie, nombre et délai.
        """
        return {
            "categorie": self.categorie,
            "entree": self.entree,
            "sortie": self.sortie,
            "nombre": self.nombre,
            "delai": self.delai,
        }

    @classmethod
    def depuis_dict(cls, contenu: dict) -> LigneScenario:
        """Recrée une ligne à partir d'un dictionnaire.

        Args:
            contenu (dict): dictionnaire au format de vers_dict().

        Returns:
            LigneScenario: la ligne décrite.

        Raises:
            ScenarioInvalideError: si un champ manque ou si la ligne est incohérente.
        """
        if not isinstance(contenu, dict):
            raise ScenarioInvalideError("une ligne de scénario se décrit par un objet JSON")
        manquants = [champ for champ in CHAMPS_LIGNE if champ not in contenu]
        if manquants:
            raise ScenarioInvalideError(f"ligne de scénario incomplète, il manque : {', '.join(manquants)}")
        return cls(*(contenu[champ] for champ in CHAMPS_LIGNE))


class Scenario:
    """Suite ordonnée de lignes, lancées l'une après l'autre."""

    def __init__(self, lignes: list[LigneScenario]) -> None:
        """Crée un scénario.

        Args:
            lignes (list[LigneScenario]): lignes dans l'ordre de lancement.
        """
        self.__lignes = list(lignes)

    @property
    def lignes(self) -> list[LigneScenario]:
        """list[LigneScenario]: lignes dans l'ordre de lancement (copie)."""
        return list(self.__lignes)

    @property
    def nombre_d_usagers(self) -> int:
        """int: nombre total d'usagers lancés par le scénario."""
        return sum(ligne.nombre for ligne in self.__lignes)

    def instants_de_depart(self) -> list[float]:
        """Calcule l'instant de lancement de chaque ligne, depuis le début du scénario.

        Returns:
            list[float]: instants en secondes ; chaque délai compte depuis la ligne précédente.
        """
        instants = []
        instant = 0.0
        for ligne in self.__lignes:
            instant += ligne.delai
            instants.append(instant)
        return instants

    def vers_json(self) -> str:
        """Convertit le scénario en texte JSON, lisible et versionné.

        Returns:
            str: le scénario au format JSON.
        """
        contenu = {"version": VERSION_FORMAT, "lignes": [ligne.vers_dict() for ligne in self.__lignes]}
        return json.dumps(contenu, ensure_ascii=False, indent=2)

    @classmethod
    def depuis_json(cls, texte: str, branches: set[str]) -> Scenario:
        """Relit un scénario enregistré, en vérifiant qu'il convient à ce rond-point.

        Args:
            texte (str): scénario au format JSON.
            branches (set[str]): identifiants des branches du rond-point.

        Returns:
            Scenario: le scénario relu.

        Raises:
            ScenarioInvalideError: si le texte n'est pas un scénario valide, ou s'il nomme une
                branche que ce rond-point n'a pas.
        """
        try:
            contenu = json.loads(texte)
        except json.JSONDecodeError as erreur:
            raise ScenarioInvalideError(f"le fichier n'est pas du JSON valide (ligne {erreur.lineno})") from None
        if not isinstance(contenu, dict) or contenu.get("version") != VERSION_FORMAT:
            raise ScenarioInvalideError(f"format de scénario inconnu (version {VERSION_FORMAT} attendue)")
        if not isinstance(contenu.get("lignes"), list):
            raise ScenarioInvalideError("le scénario doit contenir une liste de lignes")
        lignes = [LigneScenario.depuis_dict(ligne) for ligne in contenu["lignes"]]
        for ligne in lignes:
            inconnues = {ligne.entree, ligne.sortie} - branches
            if inconnues:
                raise ScenarioInvalideError(f"branche inconnue de ce rond-point : {', '.join(sorted(inconnues))}")
        return cls(lignes)
