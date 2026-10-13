"""Accès à la base MariaDB : connexion, écriture de l'historique et lecture des statistiques."""

from __future__ import annotations

import logging

import mysql.connector
from mysql.connector import errorcode
from mysql.connector.abstracts import MySQLConnectionAbstract

from cherrypie.bdd.enregistrements import EvenementConnexion, ReleveDensite
from cherrypie.commun.erreurs import AccesBddRefuseError, BaseAbsenteError, BddError, BddInjoignableError
from cherrypie.serveur.passages import PassageVp

# Codes d'erreur de mysql.connector qui disent que le serveur MariaDB ne répond pas.
ERREURS_INJOIGNABLE = frozenset(
    {
        errorcode.CR_CONN_HOST_ERROR,
        errorcode.CR_CONNECTION_ERROR,
        errorcode.CR_UNKNOWN_HOST,
        errorcode.CR_SERVER_LOST,
        errorcode.CR_SERVER_GONE_ERROR,
    }
)

REQUETE_PASSAGE = (
    "INSERT INTO passage_vp (vp, entree, sortie, debut, fin, duree, duree_anneau, regulation, densite_moyenne) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
)
REQUETE_DENSITE = "INSERT INTO releve_densite (instant, branche, densite) VALUES (%s, %s, %s)"
REQUETE_CONNEXION = (
    "INSERT INTO evenement_connexion (instant, usager, categorie, evenement, detail) VALUES (%s, %s, %s, %s, %s)"
)
REQUETE_LIRE_PASSAGES = (
    "SELECT vp, entree, sortie, debut, duree, duree_anneau, regulation, densite_moyenne "
    "FROM passage_vp ORDER BY debut DESC LIMIT %s"
)
REQUETE_LIRE_DENSITES = "SELECT instant, branche, densite FROM releve_densite ORDER BY instant DESC LIMIT %s"

journal = logging.getLogger(__name__)


class AccesBdd:
    """Toutes les requêtes du projet, sur une connexion MariaDB.

    La connexion s'ouvre avec connecter() et reste ouverte. Chaque écriture se fait par lot
    (executemany) et se termine par un commit explicite. Les requêtes sont paramétrées.
    Une erreur de mysql.connector devient une erreur métier, que l'appelant peut traiter
    sans connaître la librairie.
    """

    def __init__(self, parametres: dict[str, str | int], delai_connexion: float) -> None:
        """Prépare l'accès, sans se connecter.

        Args:
            parametres (dict[str, str | int]): section [bdd] de config.ini (hote, port,
                utilisateur, mot_de_passe, base).
            delai_connexion (float): attente maximale d'une connexion, en secondes.
        """
        self.__parametres = dict(parametres)
        self.__delai_connexion = delai_connexion
        self.__connexion: MySQLConnectionAbstract | None = None

    @property
    def adresse(self) -> str:
        """str: hôte et port du serveur MariaDB, pour les messages."""
        return f"{self.__parametres['hote']}:{self.__parametres['port']}"

    @property
    def connectee(self) -> bool:
        """bool: True si une connexion est ouverte."""
        return self.__connexion is not None

    def connecter(self) -> None:
        """Ouvre la connexion à la base, si elle ne l'est pas déjà.

        Raises:
            BddInjoignableError: si le serveur MariaDB ne répond pas.
            AccesBddRefuseError: si l'utilisateur ou le mot de passe est refusé.
            BaseAbsenteError: si la base n'existe pas.
            BddError: pour toute autre erreur de connexion.
        """
        if self.__connexion is not None:
            return
        try:
            self.__connexion = mysql.connector.connect(
                host=self.__parametres["hote"],
                port=self.__parametres["port"],
                user=self.__parametres["utilisateur"],
                password=self.__parametres["mot_de_passe"],
                database=self.__parametres["base"],
                connection_timeout=self.__delai_connexion,
            )
        except mysql.connector.Error as erreur:
            raise self.__traduire(erreur) from None

    def fermer(self) -> None:
        """Ferme la connexion ; sans effet si elle l'est déjà."""
        connexion, self.__connexion = self.__connexion, None
        if connexion is None:
            return
        try:
            connexion.close()
        except mysql.connector.Error as erreur:
            # La connexion est peut-être déjà coupée : il n'y a plus rien à libérer.
            journal.info("fermeture de la connexion à la base : %s", erreur)

    def executer_script(self, script: str) -> None:
        """Exécute un script SQL, instruction par instruction, puis valide.

        Args:
            script (str): instructions séparées par des points-virgules, comme dans schema.sql.

        Raises:
            BddError: si une instruction échoue.
        """
        instructions = [instruction.strip() for instruction in script.split(";")]
        self.__ecrire([(instruction, None) for instruction in instructions if self.__est_utile(instruction)])

    def enregistrer_passages(self, passages: list[PassageVp]) -> None:
        """Enregistre des traversées de VP.

        Args:
            passages (list[PassageVp]): traversées mesurées.

        Raises:
            BddError: si l'écriture échoue ; rien n'est alors enregistré.
        """
        lignes = [
            (
                passage.identifiant, passage.entree, passage.sortie, passage.debut, passage.fin, passage.duree,
                passage.duree_anneau, passage.regulation, passage.densite_moyenne,
            )
            for passage in passages
        ]
        self.__ecrire_lot(REQUETE_PASSAGE, lignes)

    def enregistrer_densites(self, releves: list[ReleveDensite]) -> None:
        """Enregistre des relevés de densité.

        Args:
            releves (list[ReleveDensite]): un relevé par branche et par instant.

        Raises:
            BddError: si l'écriture échoue ; rien n'est alors enregistré.
        """
        self.__ecrire_lot(REQUETE_DENSITE, [(releve.instant, releve.branche, releve.densite) for releve in releves])

    def enregistrer_connexions(self, evenements: list[EvenementConnexion]) -> None:
        """Enregistre des connexions et des déconnexions d'usagers.

        Args:
            evenements (list[EvenementConnexion]): événements de connexion.

        Raises:
            BddError: si l'écriture échoue ; rien n'est alors enregistré.
        """
        lignes = [
            (evenement.instant, evenement.usager, evenement.categorie, evenement.evenement.value, evenement.detail)
            for evenement in evenements
        ]
        self.__ecrire_lot(REQUETE_CONNEXION, lignes)

    def lire_statistiques(self, nombre_passages: int, nombre_releves: int) -> dict:
        """Lit les dernières traversées de VP et les derniers relevés de densité.

        Args:
            nombre_passages (int): nombre maximal de traversées lues.
            nombre_releves (int): nombre maximal de relevés de densité lus.

        Returns:
            dict: {"passages": [...], "densites": [...]}, du plus ancien au plus récent, dates en ISO 8601.

        Raises:
            BddError: si la lecture échoue.
        """
        passages = self.__lire(REQUETE_LIRE_PASSAGES, nombre_passages)
        releves = self.__lire(REQUETE_LIRE_DENSITES, nombre_releves)
        return {
            "passages": [
                {
                    "vp": vp, "entree": entree, "sortie": sortie, "debut": debut.isoformat(), "duree": duree,
                    "duree_anneau": duree_anneau, "regulation": bool(regulation), "densite_moyenne": densite,
                }
                for vp, entree, sortie, debut, duree, duree_anneau, regulation, densite in reversed(passages)
            ],
            "densites": [
                {"instant": instant.isoformat(), "branche": branche, "densite": densite}
                for instant, branche, densite in reversed(releves)
            ],
        }

    def __ecrire_lot(self, requete: str, lignes: list[tuple]) -> None:
        """Insère des lignes en une fois, puis valide."""
        if lignes:
            self.__ecrire([(requete, lignes)])

    def __ecrire(self, requetes: list[tuple[str, list[tuple] | None]]) -> None:
        """Exécute des requêtes (une seule fois, ou en lot si elles ont des lignes), puis valide ensemble."""
        connexion = self.__connexion_ouverte()
        try:
            curseur = connexion.cursor()
            try:
                for requete, lignes in requetes:
                    if lignes is None:
                        curseur.execute(requete)
                    else:
                        curseur.executemany(requete, lignes)
            finally:
                curseur.close()
            connexion.commit()
        except mysql.connector.Error as erreur:
            raise self.__traduire(erreur) from None

    def __lire(self, requete: str, limite: int) -> list[tuple]:
        """Exécute une requête de lecture et renvoie ses lignes."""
        connexion = self.__connexion_ouverte()
        try:
            curseur = connexion.cursor()
            try:
                curseur.execute(requete, (limite,))
                return curseur.fetchall()
            finally:
                curseur.close()
        except mysql.connector.Error as erreur:
            raise self.__traduire(erreur) from None

    def __connexion_ouverte(self) -> MySQLConnectionAbstract:
        """Renvoie la connexion ouverte, ou lève BddInjoignableError s'il n'y en a pas."""
        if self.__connexion is None:
            raise BddInjoignableError(f"aucune connexion ouverte à la base ({self.adresse})")
        return self.__connexion

    def __traduire(self, erreur: mysql.connector.Error) -> BddError:
        """Traduit une erreur de mysql.connector en erreur métier, avec un message clair."""
        if erreur.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            return AccesBddRefuseError(f"accès refusé à {self.__parametres['utilisateur']} sur {self.adresse}")
        if erreur.errno == errorcode.ER_BAD_DB_ERROR:
            return BaseAbsenteError(f"la base {self.__parametres['base']} n'existe pas sur {self.adresse}")
        if erreur.errno in ERREURS_INJOIGNABLE:
            return BddInjoignableError(f"serveur MariaDB injoignable ({self.adresse}) : {erreur.msg}")
        return BddError(f"erreur de la base ({self.adresse}) : {erreur}")

    @staticmethod
    def __est_utile(instruction: str) -> bool:
        """Indique si un morceau de script contient une instruction, et pas seulement des commentaires."""
        lignes = [ligne.strip() for ligne in instruction.splitlines()]
        return any(ligne and not ligne.startswith("--") for ligne in lignes)
