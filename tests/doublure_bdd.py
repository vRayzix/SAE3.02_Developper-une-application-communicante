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
    """Curseur qui confie chaque requête à sa connexion et renvoie les lignes qu'elle a préparées."""

    def __init__(self, connexion: "FausseConnexion") -> None:
        """Ouvre un curseur sur une fausse connexion.

        Args:
            connexion (FausseConnexion): connexion qui note les requêtes.
        """
        self.__connexion = connexion
        self.__resultats: list[tuple] = []

    @property
    def resultats(self) -> list[tuple]:
        """list[tuple]: lignes de la dernière lecture (copie)."""
        return list(self.__resultats)

    @property
    def connexion(self) -> "FausseConnexion":
        """FausseConnexion: connexion qui a ouvert le curseur."""
        return self.__connexion

    def execute(self, requete: str, parametres: tuple | None = None) -> None:
        """Note une requête ; une lecture reçoit le prochain lot de lignes préparé."""
        self.__connexion.noter_requete(requete, parametres)
        self.__resultats = self.__connexion.prendre_lignes()

    def executemany(self, requete: str, lignes: list[tuple]) -> None:
        """Note une requête en lot avec ses lignes."""
        self.__connexion.noter_requete(requete, lignes)

    def fetchall(self) -> list[tuple]:
        """Renvoie les lignes de la dernière lecture."""
        return self.__resultats

    def close(self) -> None:
        """Signale la fermeture du curseur à sa connexion."""
        self.__connexion.noter_curseur_ferme()


class FausseConnexion:
    """Connexion mysql.connector factice : elle note les requêtes, les commits et sa fermeture.

    `lignes` prépare les résultats des lectures, un lot par requête ; `panne` simule une
    connexion perdue au milieu d'une écriture.
    """

    def __init__(self, **parametres: object) -> None:
        """Crée la connexion avec les paramètres passés à mysql.connector.connect."""
        self.__parametres = parametres
        self.__requetes: list[tuple] = []
        self.__lignes: list[list[tuple]] = []
        self.__commits = 0
        self.__curseurs_fermes = 0
        self.__fermee = False
        self.__panne = False

    @property
    def parametres(self) -> dict[str, object]:
        """dict[str, object]: paramètres reçus par mysql.connector.connect (copie)."""
        return dict(self.__parametres)

    @property
    def requetes(self) -> list[tuple]:
        """list[tuple]: requêtes reçues, avec leurs paramètres ou leurs lignes (copie)."""
        return list(self.__requetes)

    @property
    def lignes(self) -> list[list[tuple]]:
        """list[list[tuple]]: résultats préparés pour les prochaines lectures (copie)."""
        return list(self.__lignes)

    @lignes.setter
    def lignes(self, valeur: list[list[tuple]]) -> None:
        """Prépare les résultats des prochaines lectures, un lot par requête."""
        self.__lignes = list(valeur)

    @property
    def commits(self) -> int:
        """int: nombre de commits reçus."""
        return self.__commits

    @property
    def curseurs_fermes(self) -> int:
        """int: nombre de curseurs refermés."""
        return self.__curseurs_fermes

    @property
    def fermee(self) -> bool:
        """bool: True une fois la connexion fermée."""
        return self.__fermee

    @property
    def panne(self) -> bool:
        """bool: True pour que la prochaine requête échoue comme une connexion perdue."""
        return self.__panne

    @panne.setter
    def panne(self, valeur: bool) -> None:
        """Met la connexion en panne, ou la répare."""
        self.__panne = valeur

    def noter_requete(self, requete: str, valeurs: tuple | list[tuple] | None) -> None:
        """Note une requête, ou échoue comme mysql.connector si la connexion est en panne."""
        if self.__panne:
            raise mysql.connector.Error(msg="Lost connection", errno=errorcode.CR_SERVER_LOST)
        self.__requetes.append((requete, valeurs))

    def prendre_lignes(self) -> list[tuple]:
        """Renvoie le prochain lot de lignes préparé, ou aucune ligne."""
        return self.__lignes.pop(0) if self.__lignes else []

    def noter_curseur_ferme(self) -> None:
        """Compte un curseur refermé."""
        self.__curseurs_fermes += 1

    def cursor(self) -> FauxCurseur:
        """Ouvre un curseur."""
        return FauxCurseur(self)

    def commit(self) -> None:
        """Compte un commit."""
        self.__commits += 1

    def close(self) -> None:
        """Ferme la connexion."""
        self.__fermee = True


PARAMETRES_DOUBLURE = {"hote": "doublure", "port": 3306, "utilisateur": "test", "mot_de_passe": "test", "base": "test"}
DELAI_CONNEXION_DOUBLURE = 0.1


class DoublureBdd(AccesBdd):
    """Remplace MariaDB dans les tests ; on peut la rendre injoignable pour simuler une panne.

    Elle répond comme AccesBdd : mêmes méthodes, mêmes erreurs, mêmes statistiques. Le
    thread de l'historique l'appelle pendant que le test la lit : un verrou protège ses listes.
    """

    def __init__(self) -> None:
        """Crée une base vide et joignable."""
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
        """Rend la base joignable ou non ; injoignable, la connexion en cours tombe."""
        self.__joignable = valeur
        if not valeur:
            self.__connectee = False

    @property
    def connectee(self) -> bool:
        """bool: True entre connecter() et fermer(), tant que la base est joignable."""
        return self.__connectee

    @property
    def tentatives(self) -> int:
        """int: nombre d'appels à connecter()."""
        return self.__tentatives

    @property
    def passages(self) -> list[PassageVp]:
        """list[PassageVp]: traversées enregistrées (copie)."""
        with self.__verrou:
            return list(self.__passages)

    @property
    def releves(self) -> list[ReleveDensite]:
        """list[ReleveDensite]: relevés de densité enregistrés (copie)."""
        with self.__verrou:
            return list(self.__releves)

    @property
    def connexions(self) -> list[EvenementConnexion]:
        """list[EvenementConnexion]: connexions et déconnexions enregistrées (copie)."""
        with self.__verrou:
            return list(self.__connexions)

    def connecter(self) -> None:
        """Compte la tentative ; échoue comme MariaDB si la base est injoignable."""
        self.__tentatives += 1
        self.__verifier()
        self.__connectee = True

    def fermer(self) -> None:
        """Ferme la connexion simulée."""
        self.__connectee = False

    def enregistrer_passages(self, passages: list[PassageVp]) -> None:
        """Garde les traversées en mémoire, ou échoue si la base est injoignable."""
        self.__verifier()
        with self.__verrou:
            self.__passages.extend(passages)

    def enregistrer_densites(self, releves: list[ReleveDensite]) -> None:
        """Garde les relevés en mémoire, ou échoue si la base est injoignable."""
        self.__verifier()
        with self.__verrou:
            self.__releves.extend(releves)

    def enregistrer_connexions(self, evenements: list[EvenementConnexion]) -> None:
        """Garde les événements en mémoire, ou échoue si la base est injoignable."""
        self.__verifier()
        with self.__verrou:
            self.__connexions.extend(evenements)

    def lire_statistiques(self, nombre_passages: int, nombre_releves: int) -> dict:
        """Rend les dernières traversées et les derniers relevés, au format d'AccesBdd."""
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
        """Simule une base injoignable : la connexion tombe et l'appel échoue."""
        if not self.__joignable:
            self.__connectee = False
            raise BddInjoignableError("serveur MariaDB injoignable (doublure)")
