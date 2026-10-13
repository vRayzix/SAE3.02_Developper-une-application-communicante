"""Doublure de l'accès à la base : AccesBdd sans MariaDB, qui garde en mémoire ce qu'on lui écrit."""

import threading

from cherrypie.bdd.acces_bdd import AccesBdd
from cherrypie.bdd.enregistrements import EvenementConnexion, ReleveDensite
from cherrypie.commun.erreurs import BddInjoignableError
from cherrypie.serveur.passages import PassageVp

PARAMETRES_DOUBLURE = {"hote": "doublure", "port": 3306, "utilisateur": "test", "mot_de_passe": "test", "base": "test"}
DELAI_CONNEXION_DOUBLURE = 0.1


class DoublureBdd(AccesBdd):
    """Remplace MariaDB dans les tests ; on peut la rendre injoignable pour simuler une panne.

    Elle répond comme AccesBdd : mêmes méthodes, mêmes erreurs, mêmes statistiques. Le
    thread de l'historique l'appelle pendant que le test la lit : un verrou protège ses listes.
    """

    def __init__(self) -> None:
        super().__init__(PARAMETRES_DOUBLURE, DELAI_CONNEXION_DOUBLURE)
        self.__verrou = threading.Lock()
        self.__joignable = True
        self.__connectee = False
        self.__tentatives = 0
        self.__passages: list[PassageVp] = []
        self.__releves: list[ReleveDensite] = []
        self.__connexions: list[EvenementConnexion] = []

    @property
    def joignable(self) -> bool:
        """bool: False pour simuler une base injoignable."""
        return self.__joignable

    @joignable.setter
    def joignable(self, valeur: bool) -> None:
        self.__joignable = valeur
        if not valeur:
            self.__connectee = False

    @property
    def connectee(self) -> bool:
        return self.__connectee

    @property
    def tentatives(self) -> int:
        """int: nombre d'appels à connecter()."""
        return self.__tentatives

    @property
    def passages(self) -> list[PassageVp]:
        with self.__verrou:
            return list(self.__passages)

    @property
    def releves(self) -> list[ReleveDensite]:
        with self.__verrou:
            return list(self.__releves)

    @property
    def connexions(self) -> list[EvenementConnexion]:
        with self.__verrou:
            return list(self.__connexions)

    def connecter(self) -> None:
        self.__tentatives += 1
        self.__verifier()
        self.__connectee = True

    def fermer(self) -> None:
        self.__connectee = False

    def enregistrer_passages(self, passages: list[PassageVp]) -> None:
        self.__verifier()
        with self.__verrou:
            self.__passages.extend(passages)

    def enregistrer_densites(self, releves: list[ReleveDensite]) -> None:
        self.__verifier()
        with self.__verrou:
            self.__releves.extend(releves)

    def enregistrer_connexions(self, evenements: list[EvenementConnexion]) -> None:
        self.__verifier()
        with self.__verrou:
            self.__connexions.extend(evenements)

    def lire_statistiques(self, nombre_passages: int, nombre_releves: int) -> dict:
        self.__verifier()
        with self.__verrou:
            passages = self.__passages[-nombre_passages:]
            releves = self.__releves[-nombre_releves:]
        return {
            "passages": [
                {
                    "vp": passage.identifiant, "entree": passage.entree, "sortie": passage.sortie,
                    "debut": passage.debut.isoformat(), "duree": passage.duree, "duree_anneau": passage.duree_anneau,
                    "regulation": passage.regulation, "densite_moyenne": passage.densite_moyenne,
                }
                for passage in passages
            ],
            "densites": [
                {"instant": releve.instant.isoformat(), "branche": releve.branche, "densite": releve.densite}
                for releve in releves
            ],
        }

    def __verifier(self) -> None:
        if not self.__joignable:
            self.__connectee = False
            raise BddInjoignableError("serveur MariaDB injoignable (doublure)")
