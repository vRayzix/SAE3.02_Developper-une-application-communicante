"""Lecture et validation du fichier de configuration (config.ini)."""

from __future__ import annotations

import configparser
import math
import re
from dataclasses import dataclass
from pathlib import Path

from cherrypie.commun.erreurs import ConfigurationInvalideError

PORT_MIN = 1
PORT_MAX = 65535
NOMBRE_MIN_BRANCHES = 3
TOUR_COMPLET = 360.0
# Identifiant de branche : minuscules sans accents, chiffres et « _ ». Le tiret est exclu,
# car il sépare les deux branches dans le nom d'un segment (ex. "nations_nord-albert_camus").
MOTIF_IDENTIFIANT_BRANCHE = re.compile(r"[a-z0-9_]+")
PREFIXE_SECTION_BRANCHE = "branche."


@dataclass(frozen=True)
class ParametresBranche:
    """Description d'une branche, lue dans sa section [branche.<identifiant>].

    Attributes:
        nom (str): identifiant de la branche, utilisé dans le protocole (ex. "nations_nord").
        libelle (str): nom de rue affiché par l'IHM.
        cap (float): direction de la branche vue du centre, en degrés depuis le nord,
            dans le sens des aiguilles d'une montre, entre 0 et 360.
        terre_plein (float): largeur du terre-plein entre les deux chaussées, en mètres.
        passage_pieton (float): distance entre le bord de l'anneau et le passage piéton, en mètres.
    """

    nom: str
    libelle: str
    cap: float
    terre_plein: float
    passage_pieton: float


class Configuration:
    """Paramètres de l'application, lus et validés une seule fois au démarrage.

    Une fois construite, la configuration ne change plus : le reste du code peut
    utiliser ses valeurs sans les revérifier.
    """

    def __init__(self, parseur: configparser.ConfigParser) -> None:
        """Extrait et valide toutes les valeurs d'un fichier déjà analysé.

        Args:
            parseur (configparser.ConfigParser): contenu de config.ini.

        Raises:
            ConfigurationInvalideError: si une clé manque ou si une valeur est incohérente.
        """
        self.__hote = self.__lire_texte(parseur, "reseau", "hote")
        self.__port_tcp = self.__lire_entier(parseur, "reseau", "port_tcp", PORT_MIN, PORT_MAX)
        self.__port_udp = self.__lire_entier(parseur, "reseau", "port_udp", PORT_MIN, PORT_MAX)
        self.__cle_hmac = self.__lire_texte(parseur, "securite", "cle_hmac").encode("utf-8")
        self.__fenetre_anti_rejeu = self.__lire_reel_positif(parseur, "securite", "fenetre_anti_rejeu")
        self.__intervalle_ping = self.__lire_reel_positif(parseur, "delais", "intervalle_ping")
        self.__timeout_client = self.__lire_reel_positif(parseur, "delais", "timeout_client")
        self.__intervalle_position = self.__lire_reel_positif(parseur, "delais", "intervalle_position")
        self.__intervalle_etat = self.__lire_reel_positif(parseur, "delais", "intervalle_etat")
        self.__backoff_initial = self.__lire_reel_positif(parseur, "delais", "backoff_initial")
        self.__backoff_max = self.__lire_reel_positif(parseur, "delais", "backoff_max")
        self.__branches = self.__lire_branches(parseur)
        self.__rayon = self.__lire_reel_positif(parseur, "rond_point", "rayon")
        self.__largeur_voie_anneau = self.__lire_reel_positif(parseur, "rond_point", "largeur_voie_anneau")
        self.__largeur_chaussee = self.__lire_reel_positif(parseur, "rond_point", "largeur_chaussee")
        self.__longueur_branche = self.__lire_reel_positif(parseur, "rond_point", "longueur_branche")
        self.__capacite_par_branche = self.__lire_entier(parseur, "rond_point", "capacite_par_branche", 1)
        self.__parametres_bdd = {
            "hote": self.__lire_texte(parseur, "bdd", "hote"),
            "port": self.__lire_entier(parseur, "bdd", "port", PORT_MIN, PORT_MAX),
            "utilisateur": self.__lire_texte(parseur, "bdd", "utilisateur"),
            "mot_de_passe": self.__lire_texte(parseur, "bdd", "mot_de_passe"),
            "base": self.__lire_texte(parseur, "bdd", "base"),
        }
        self.__delai_connexion_bdd = self.__lire_reel_positif(parseur, "bdd", "delai_connexion")
        self.__delai_reessai_bdd = self.__lire_reel_positif(parseur, "bdd", "delai_reessai")
        self.__intervalle_releves = self.__lire_reel_positif(parseur, "bdd", "intervalle_releves")
        self.__verifier_coherence()

    @classmethod
    def depuis_fichier(cls, chemin: str | Path) -> Configuration:
        """Lit un fichier config.ini et construit la configuration.

        Args:
            chemin (str | Path): chemin du fichier à lire.

        Returns:
            Configuration: la configuration validée.

        Raises:
            ConfigurationInvalideError: si le fichier est introuvable, mal formé
                ou contient une valeur incohérente.
        """
        # Sans interpolation, un « % » dans un mot de passe ou dans la clé est lu
        # tel quel au lieu de provoquer une erreur de configparser.
        parseur = configparser.ConfigParser(interpolation=None)
        try:
            fichiers_lus = parseur.read(chemin, encoding="utf-8")
        except UnicodeDecodeError as erreur:
            raise ConfigurationInvalideError(f"{chemin} n'est pas encodé en UTF-8") from erreur
        # Les messages de configparser recopient la ligne fautive, qui peut contenir la
        # clé HMAC ou le mot de passe : on n'en garde que le numéro. « from None » évite
        # que l'erreur d'origine réapparaisse dans une trace journalisée.
        except configparser.MissingSectionHeaderError as erreur:
            raise ConfigurationInvalideError(
                f"{chemin}, ligne {erreur.lineno} : valeur placée avant toute section"
            ) from None
        except configparser.ParsingError as erreur:
            lignes = ", ".join(str(numero) for numero, _ in erreur.errors)
            raise ConfigurationInvalideError(f"{chemin}, ligne {lignes} : format « cle = valeur » attendu") from None
        except configparser.Error as erreur:
            # Restent les sections ou clés en double, dont le message ne cite que des noms.
            raise ConfigurationInvalideError(f"{chemin} est mal formé : {erreur}") from None
        if not fichiers_lus:
            raise ConfigurationInvalideError(f"fichier de configuration introuvable ou illisible : {chemin}")
        return cls(parseur)

    @property
    def hote(self) -> str:
        """str: adresse du serveur, pour l'écoute comme pour la connexion des clients."""
        return self.__hote

    @property
    def port_tcp(self) -> int:
        """int: port TCP des messages qui doivent arriver (HELLO, NOTIF, STATE...)."""
        return self.__port_tcp

    @property
    def port_udp(self) -> int:
        """int: port UDP des positions."""
        return self.__port_udp

    @property
    def cle_hmac(self) -> bytes:
        """bytes: clé partagée qui signe toutes les trames."""
        return self.__cle_hmac

    @property
    def fenetre_anti_rejeu(self) -> float:
        """float: écart maximal accepté entre l'horodatage d'une trame et l'heure locale, en secondes."""
        return self.__fenetre_anti_rejeu

    @property
    def intervalle_ping(self) -> float:
        """float: délai entre deux PING envoyés par un client, en secondes."""
        return self.__intervalle_ping

    @property
    def timeout_client(self) -> float:
        """float: silence au-delà duquel le serveur retire un client, en secondes."""
        return self.__timeout_client

    @property
    def intervalle_position(self) -> float:
        """float: délai entre deux POS envoyés par un client, en secondes."""
        return self.__intervalle_position

    @property
    def intervalle_etat(self) -> float:
        """float: délai entre deux STATE envoyés aux supervisions, en secondes.

        Le serveur s'en sert aussi comme cadence pour contrôler les heartbeats.
        """
        return self.__intervalle_etat

    @property
    def backoff_initial(self) -> float:
        """float: premier délai d'attente avant une tentative de reconnexion, en secondes."""
        return self.__backoff_initial

    @property
    def backoff_max(self) -> float:
        """float: plafond du délai de reconnexion, en secondes."""
        return self.__backoff_max

    @property
    def branches(self) -> list[ParametresBranche]:
        """list[ParametresBranche]: branches du rond-point, dans l'ordre de [rond_point] branches (copie)."""
        return list(self.__branches)

    @property
    def rayon(self) -> float:
        """float: rayon de l'axe de l'anneau, entre ses deux voies, en mètres."""
        return self.__rayon

    @property
    def largeur_voie_anneau(self) -> float:
        """float: largeur de chacune des deux voies de l'anneau, en mètres."""
        return self.__largeur_voie_anneau

    @property
    def largeur_chaussee(self) -> float:
        """float: largeur de la chaussée de chaque sens d'une branche, en mètres."""
        return self.__largeur_chaussee

    @property
    def longueur_branche(self) -> float:
        """float: longueur modélisée de chaque branche, depuis le bord de l'anneau, en mètres."""
        return self.__longueur_branche

    @property
    def capacite_par_branche(self) -> int:
        """int: nombre d'usagers à partir duquel une branche est considérée pleine."""
        return self.__capacite_par_branche

    @property
    def parametres_bdd(self) -> dict[str, str | int]:
        """dict[str, str | int]: hote, port, utilisateur, mot_de_passe et base de MariaDB (copie)."""
        return dict(self.__parametres_bdd)

    @property
    def delai_connexion_bdd(self) -> float:
        """float: attente maximale d'une connexion à MariaDB, en secondes."""
        return self.__delai_connexion_bdd

    @property
    def delai_reessai_bdd(self) -> float:
        """float: attente entre deux tentatives de connexion à une base injoignable, en secondes."""
        return self.__delai_reessai_bdd

    @property
    def intervalle_releves(self) -> float:
        """float: intervalle entre deux relevés de densité écrits en base, en secondes."""
        return self.__intervalle_releves

    def __verifier_coherence(self) -> None:
        """Vérifie les contraintes qui portent sur plusieurs valeurs à la fois."""
        if self.__timeout_client <= self.__intervalle_ping:
            raise ConfigurationInvalideError(
                "[delais] timeout_client doit être supérieur à intervalle_ping, "
                "sinon un client actif serait retiré entre deux PING"
            )
        if self.__backoff_initial > self.__backoff_max:
            raise ConfigurationInvalideError("[delais] backoff_initial ne peut pas dépasser backoff_max")
        if self.__largeur_voie_anneau >= self.__rayon:
            raise ConfigurationInvalideError(
                "[rond_point] largeur_voie_anneau doit être inférieure à rayon, sinon il n'y a plus d'îlot"
            )

    @staticmethod
    def __lire_texte(parseur: configparser.ConfigParser, section: str, cle: str) -> str:
        """Lit une valeur obligatoire et non vide."""
        try:
            texte = parseur.get(section, cle)
        except configparser.NoSectionError as erreur:
            raise ConfigurationInvalideError(f"section [{section}] absente de la configuration") from erreur
        except configparser.NoOptionError as erreur:
            raise ConfigurationInvalideError(f"[{section}] {cle} absent de la configuration") from erreur
        if not texte:
            raise ConfigurationInvalideError(f"[{section}] {cle} est vide")
        return texte

    @staticmethod
    def __lire_entier(
        parseur: configparser.ConfigParser, section: str, cle: str, minimum: int, maximum: int | None = None
    ) -> int:
        """Lit un entier compris entre minimum et maximum (sans maximum si None)."""
        texte = Configuration.__lire_texte(parseur, section, cle)
        try:
            valeur = int(texte)
        except ValueError as erreur:
            raise ConfigurationInvalideError(f"[{section}] {cle} doit être un entier (lu : {texte!r})") from erreur
        if valeur < minimum:
            raise ConfigurationInvalideError(f"[{section}] {cle} doit valoir au moins {minimum} (lu : {valeur})")
        if maximum is not None and valeur > maximum:
            raise ConfigurationInvalideError(f"[{section}] {cle} doit valoir au plus {maximum} (lu : {valeur})")
        return valeur

    @staticmethod
    def __lire_reel_positif(parseur: configparser.ConfigParser, section: str, cle: str) -> float:
        """Lit un nombre fini strictement positif (délai, distance...)."""
        texte = Configuration.__lire_texte(parseur, section, cle)
        try:
            valeur = float(texte)
        except ValueError as erreur:
            raise ConfigurationInvalideError(f"[{section}] {cle} doit être un nombre (lu : {texte!r})") from erreur
        # float() accepte « nan » et « inf », qui fausseraient ensuite tous les calculs de délais.
        if not math.isfinite(valeur) or valeur <= 0:
            raise ConfigurationInvalideError(
                f"[{section}] {cle} doit être un nombre fini strictement positif (lu : {texte!r})"
            )
        return valeur

    @staticmethod
    def __lire_branches(parseur: configparser.ConfigParser) -> list[ParametresBranche]:
        """Lit la liste des branches, puis la section qui décrit chacune d'elles."""
        texte = Configuration.__lire_texte(parseur, "rond_point", "branches")
        noms = [nom.strip() for nom in texte.split(",")]
        if "" in noms:
            raise ConfigurationInvalideError("[rond_point] branches contient un nom vide")
        for nom in noms:
            if not MOTIF_IDENTIFIANT_BRANCHE.fullmatch(nom):
                raise ConfigurationInvalideError(
                    f"[rond_point] identifiant de branche invalide : {nom!r} (minuscules sans accents, chiffres et _)"
                )
        if len(noms) < NOMBRE_MIN_BRANCHES:
            raise ConfigurationInvalideError(
                f"[rond_point] il faut au moins {NOMBRE_MIN_BRANCHES} branches (lu : {len(noms)})"
            )
        if len(set(noms)) != len(noms):
            raise ConfigurationInvalideError("[rond_point] branches contient des noms en double")
        sections_en_trop = {
            section for section in parseur.sections() if section.startswith(PREFIXE_SECTION_BRANCHE)
        } - {PREFIXE_SECTION_BRANCHE + nom for nom in noms}
        if sections_en_trop:
            raise ConfigurationInvalideError(
                f"section [{min(sections_en_trop)}] sans branche correspondante dans [rond_point] branches"
            )
        branches = [Configuration.__lire_branche(parseur, nom) for nom in noms]
        caps = [branche.cap for branche in branches]
        if len(set(caps)) != len(caps):
            raise ConfigurationInvalideError("[rond_point] deux branches ont le même cap")
        return branches

    @staticmethod
    def __lire_branche(parseur: configparser.ConfigParser, nom: str) -> ParametresBranche:
        """Lit la section [branche.<nom>] : libellé, cap, terre-plein et passage piéton."""
        section = PREFIXE_SECTION_BRANCHE + nom
        texte_cap = Configuration.__lire_texte(parseur, section, "cap")
        try:
            cap = float(texte_cap)
        except ValueError as erreur:
            raise ConfigurationInvalideError(f"[{section}] cap doit être un nombre (lu : {texte_cap!r})") from erreur
        if not 0 <= cap < TOUR_COMPLET:
            raise ConfigurationInvalideError(f"[{section}] cap doit être compris entre 0 et 360 (lu : {texte_cap!r})")
        return ParametresBranche(
            nom,
            Configuration.__lire_texte(parseur, section, "libelle"),
            cap,
            Configuration.__lire_reel_positif(parseur, section, "terre_plein"),
            Configuration.__lire_reel_positif(parseur, section, "passage_pieton"),
        )
