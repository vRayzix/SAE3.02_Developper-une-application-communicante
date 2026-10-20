"""Lanceur des clients usagers locaux, partagé par les sections « Scénario » et « Suivi »."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, pyqtSignal

from cherrypie.client.client_usager import ClientUsager
from cherrypie.commun.config import Configuration
from cherrypie.ihm.relais_client import RelaisClient
from cherrypie.modele.usager import CLASSES_PAR_CATEGORIE, Pieton

journal = logging.getLogger(__name__)


class LanceurClients(QObject):
    """Crée des usagers, lance un client par usager et relaie ce qui leur arrive.

    Chaque client tourne dans son thread et signale ce qui lui arrive par un RelaisClient ;
    le lanceur réémet ces signaux, que la section « Suivi » affiche. Les identifiants sont
    numérotés par catégorie (voiture_1, voiture_2...), sans jamais resservir.

    Signals:
        client_lance (str, str): identifiant de l'usager lancé et son trajet, avec les noms de rues.
        position_changee (str, dict): identifiant et état de l'usager après un pas.
        connexion_changee (str, str, str): identifiant, état de la connexion et détail.
        notification_recue (str, str, str, bool): identifiant, code, texte, True si la consigne est appliquée.
    """

    client_lance = pyqtSignal(str, str)
    position_changee = pyqtSignal(str, dict)
    connexion_changee = pyqtSignal(str, str, str)
    notification_recue = pyqtSignal(str, str, str, bool)

    def __init__(self, config: Configuration) -> None:
        """Prépare le lanceur.

        Args:
            config (Configuration): configuration donnée aux clients lancés (serveur, branches).
        """
        super().__init__()
        self.__config = config
        self.__libelles = {branche.nom: branche.libelle for branche in config.branches}
        self.__compteurs = {categorie: 0 for categorie in CLASSES_PAR_CATEGORIE}
        self.__clients: list[ClientUsager] = []

    @property
    def libelles(self) -> dict[str, str]:
        """dict[str, str]: nom de rue de chaque branche, par identifiant (copie)."""
        return dict(self.__libelles)

    @property
    def compteurs(self) -> dict[str, int]:
        """dict[str, int]: nombre d'usagers déjà lancés par catégorie (copie)."""
        return dict(self.__compteurs)

    @property
    def config(self) -> Configuration:
        """Configuration: configuration donnée aux clients lancés."""
        return self.__config

    @property
    def clients(self) -> list[ClientUsager]:
        """list[ClientUsager]: clients lancés dont le thread n'a pas encore été oublié (copie)."""
        return list(self.__clients)

    def trajet(self, categorie: str, entree: str, sortie: str) -> str:
        """Décrit un trajet avec les noms de rues.

        Args:
            categorie (str): catégorie de l'usager.
            entree (str): identifiant de la branche d'entrée.
            sortie (str): identifiant de la branche de sortie.

        Returns:
            str: par exemple « Bd des Nations (sud) vers Rue Albert Camus », ou « traverse ... » pour un piéton.
        """
        if categorie == Pieton.CATEGORIE:
            return f"traverse {self.__libelles[entree]}"
        return f"{self.__libelles[entree]} vers {self.__libelles[sortie]}"

    def lancer(self, categorie: str, entree: str, sortie: str, nombre: int) -> list[ClientUsager]:
        """Crée des usagers d'un même trajet et lance un client pour chacun.

        Args:
            categorie (str): catégorie des usagers (ex. "voiture").
            entree (str): identifiant de la branche d'entrée.
            sortie (str): identifiant de la branche de sortie.
            nombre (int): nombre d'usagers à lancer.

        Returns:
            list[ClientUsager]: les clients lancés, déjà démarrés.
        """
        # Les clients arrivés au bout ont fini leur thread : inutile de les garder.
        self.__clients = [client for client in self.__clients if client.is_alive()]
        lances = [self.__lancer_un(categorie, entree, sortie) for _ in range(nombre)]
        journal.info("%d %s lancé(s) de %s vers %s", len(lances), categorie, entree, sortie)
        return lances

    def arreter_tous(self, delai: float) -> None:
        """Arrête tous les clients lancés et attend la fin de leurs threads.

        Args:
            delai (float): attente maximale pour chaque thread, en secondes.
        """
        for client in self.__clients:
            client.arreter()
        for client in self.__clients:
            client.join(timeout=delai)
            if client.is_alive():
                journal.warning("le client %s ne s'est pas arrêté à temps", client.usager.identifiant)

    def __lancer_un(self, categorie: str, entree: str, sortie: str) -> ClientUsager:
        """Crée un usager, son relais et son client, puis démarre le client."""
        self.__compteurs[categorie] += 1
        identifiant = f"{categorie}_{self.__compteurs[categorie]}"
        usager = CLASSES_PAR_CATEGORIE[categorie](identifiant, entree, sortie)
        relais = RelaisClient(identifiant)
        relais.position_changee.connect(self.position_changee)
        relais.connexion_changee.connect(self.connexion_changee)
        relais.notification_recue.connect(self.notification_recue)
        # Le client garde ses rappels, donc le relais : il vit aussi longtemps que lui.
        client = ClientUsager(
            self.__config,
            usager,
            sur_position=relais.sur_position,
            sur_notification=relais.sur_notification,
            sur_connexion=relais.sur_connexion,
        )
        self.__clients.append(client)
        self.client_lance.emit(identifiant, self.trajet(categorie, entree, sortie))
        client.start()
        return client
