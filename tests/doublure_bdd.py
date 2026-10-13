"""Doublures de la base pour les tests, sans MariaDB.

FausseConnexion remplace une connexion mysql.connector, pour vérifier les requêtes
d'AccesBdd. DoublureBdd remplace AccesBdd tout entier, pour le serveur et l'historique.
"""

import threading

import mysql.connector
from mysql.connector import errorcode

from cherrypie.bdd.acces_bdd import AccesBdd
from cherrypie.bdd.enregistrements import EvenementConnexion, ReleveDensite
from cherrypie.commun.erreurs import BddInjoignableError
from cherrypie.serveur.passages import PassageVp

class FauxCurseur:
    """Curseur qui note les requêtes et renvoie des lignes préparées."""

    def __init__(self, connexion: "FausseConnexion") -> None:
        self.connexion = connexion
        self.resultats: list[tuple] = []

    def execute(self, requete: str, parametres: tuple | None = None) -> None:
        self.connexion.verifier_panne()
        self.connexion.requetes.append((requete, parametres))
        self.resultats = self.connexion.lignes.pop(0) if self.connexion.lignes else []

    def executemany(self, requete: str, lignes: list[tuple]) -> None:
        self.connexion.verifier_panne()
        self.connexion.requetes.append((requete, lignes))

    def fetchall(self) -> list[tuple]:
        return self.resultats

    def close(self) -> None:
        self.connexion.curseurs_fermes += 1


class FausseConnexion:
    """Connexion qui note les requêtes, les commits et sa fermeture."""

    def __init__(self, **parametres: object) -> None:
        self.parametres = parametres
        self.requetes: list[tuple] = []
        self.lignes: list[list[tuple]] = []
        self.commits = 0
        self.curseurs_fermes = 0
        self.fermee = False
        self.panne = False

    def verifier_panne(self) -> None:
        if self.panne:
            raise mysql.connector.Error(msg="Lost connection", errno=errorcode.CR_SERVER_LOST)

    def cursor(self) -> FauxCurseur:
        return FauxCurseur(self)

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.fermee = True


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
