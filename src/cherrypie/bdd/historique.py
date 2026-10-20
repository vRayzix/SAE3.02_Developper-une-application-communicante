"""Écriture de l'historique en base, dans un thread à part de la boucle du serveur."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass

from cherrypie.bdd.acces_bdd import AccesBdd
from cherrypie.bdd.enregistrements import EvenementConnexion, ReleveDensite
from cherrypie.commun.erreurs import BddError
from cherrypie.serveur.passages import PassageVp

# Au-delà de ce nombre d'enregistrements d'un même type en attente, les plus anciens sont
# oubliés : une base injoignable pendant des heures ne doit pas remplir la mémoire du serveur.
MAX_EN_ATTENTE = 10_000
# Une demande de statistiques renvoie au plus ces nombres de traversées et de relevés.
NOMBRE_PASSAGES_LUS = 200
NOMBRE_RELEVES_LUS = 2_000

journal = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemandeStatistiques:
    """Demande de statistiques d'une session de supervision.

    Attributes:
        numero (int): numéro de la session qui attend la réponse.
    """

    numero: int


class Historique(threading.Thread):
    """Écrit l'historique du serveur en base et répond aux demandes de statistiques.

    La boucle select du serveur ne doit jamais attendre MariaDB : elle dépose ce qu'il faut
    écrire dans une file, que ce thread vide. Si la base est injoignable, les
    enregistrements attendent et le thread réessaie tous les `delai_reessai` secondes ;
    l'échec est journalisé une fois, puis le retour de la base. Les réponses aux demandes
    de statistiques attendent dans une autre file, que le serveur relève à chaque cadence.
    """

    def __init__(self, acces: AccesBdd, delai_reessai: float) -> None:
        """Prépare le thread, sans le démarrer.

        Args:
            acces (AccesBdd): accès à la base.
            delai_reessai (float): attente entre deux tentatives de connexion, en secondes.
        """
        super().__init__(name="historique", daemon=True)
        self.__acces = acces
        self.__delai_reessai = delai_reessai
        self.__taches: queue.SimpleQueue = queue.SimpleQueue()
        self.__reponses: queue.SimpleQueue[tuple[int, dict]] = queue.SimpleQueue()
        self.__arret = threading.Event()
        self.__passages: deque[PassageVp] = deque(maxlen=MAX_EN_ATTENTE)
        self.__releves: deque[ReleveDensite] = deque(maxlen=MAX_EN_ATTENTE)
        self.__connexions: deque[EvenementConnexion] = deque(maxlen=MAX_EN_ATTENTE)
        self.__prochain_essai = 0.0
        self.__en_panne = False

    @property
    def delai_reessai(self) -> float:
        """float: attente entre deux tentatives de connexion, en secondes."""
        return self.__delai_reessai

    @property
    def arret_demande(self) -> bool:
        """bool: True une fois l'arrêt demandé."""
        return self.__arret.is_set()

    @property
    def en_panne(self) -> bool:
        """bool: True depuis l'échec d'une connexion ou d'une écriture, jusqu'au retour de la base."""
        return self.__en_panne

    @property
    def prochain_essai(self) -> float:
        """float: instant (horloge monotone) avant lequel le thread ne retente pas de se connecter."""
        return self.__prochain_essai

    @property
    def taches_en_attente(self) -> int:
        """int: nombre de tâches déposées que le thread n'a pas encore prises."""
        return self.__taches.qsize()

    @property
    def reponses_en_attente(self) -> int:
        """int: nombre de réponses de statistiques que le serveur n'a pas encore relevées."""
        return self.__reponses.qsize()

    @property
    def acces(self) -> AccesBdd:
        """AccesBdd: accès à la base."""
        return self.__acces

    @property
    def en_attente(self) -> int:
        """int: nombre d'enregistrements pas encore écrits en base."""
        return len(self.__passages) + len(self.__releves) + len(self.__connexions)

    def noter_passage(self, passage: PassageVp) -> None:
        """Confie une traversée de VP à écrire. Appelable depuis n'importe quel thread.

        Args:
            passage (PassageVp): traversée mesurée.
        """
        self.__taches.put(passage)

    def noter_densites(self, releves: list[ReleveDensite]) -> None:
        """Confie des relevés de densité à écrire. Appelable depuis n'importe quel thread.

        Args:
            releves (list[ReleveDensite]): un relevé par branche.
        """
        for releve in releves:
            self.__taches.put(releve)

    def noter_connexion(self, evenement: EvenementConnexion) -> None:
        """Confie une connexion ou une déconnexion à écrire. Appelable depuis n'importe quel thread.

        Args:
            evenement (EvenementConnexion): événement de connexion.
        """
        self.__taches.put(evenement)

    def demander_statistiques(self, numero: int) -> None:
        """Demande les statistiques pour une session ; la réponse arrive par reponses_pretes().

        Args:
            numero (int): numéro de la session qui attend la réponse.
        """
        self.__taches.put(DemandeStatistiques(numero))

    def reponses_pretes(self) -> list[tuple[int, dict]]:
        """Relève les réponses aux demandes de statistiques, sans attendre.

        Returns:
            list[tuple[int, dict]]: numéro de session et données de chaque réponse.
        """
        reponses = []
        while True:
            try:
                reponses.append(self.__reponses.get_nowait())
            except queue.Empty:
                return reponses

    def arreter(self, delai: float) -> None:
        """Demande l'arrêt du thread et l'attend ; il tente une dernière écriture avant de finir.

        Args:
            delai (float): attente maximale, en secondes.
        """
        self.__arret.set()
        self.__taches.put(None)
        self.join(timeout=delai)
        if self.is_alive():
            journal.warning("l'historique ne s'est pas arrêté à temps")

    def run(self) -> None:
        """Vide la file des tâches et écrit en base, jusqu'à l'arrêt."""
        try:
            while not self.__arret.is_set():
                self.__traiter(self.__attendre_une_tache())
                # Tout ce qui est arrivé entre-temps part dans le même lot.
                self.__traiter_les_taches_arrivees()
                self.__ecrire()
            self.__ecrire()
        except Exception:
            # Frontière : un bug d'écriture ne doit pas laisser croire que l'historique tourne.
            journal.exception("erreur inattendue dans l'historique")
        finally:
            perdus = self.en_attente
            if perdus:
                journal.warning("%d enregistrement(s) non écrit(s) en base à l'arrêt", perdus)
            self.__acces.fermer()

    def __attendre_une_tache(self) -> object:
        """Attend la prochaine tâche ; sans nouvelle, revient au bout du délai de nouvel essai."""
        try:
            return self.__taches.get(timeout=self.__delai_reessai)
        except queue.Empty:
            return None

    def __traiter_les_taches_arrivees(self) -> None:
        """Traite, sans attendre, les tâches déjà dans la file."""
        while True:
            try:
                tache = self.__taches.get_nowait()
            except queue.Empty:
                return
            self.__traiter(tache)

    def __traiter(self, tache: object) -> None:
        """Range un enregistrement dans sa file d'attente, ou répond à une demande de statistiques."""
        if isinstance(tache, PassageVp):
            self.__passages.append(tache)
        elif isinstance(tache, ReleveDensite):
            self.__releves.append(tache)
        elif isinstance(tache, EvenementConnexion):
            self.__connexions.append(tache)
        elif isinstance(tache, DemandeStatistiques):
            self.__repondre(tache.numero)

    def __ecrire(self) -> None:
        """Écrit ce qui attend, par lot et par table ; en cas d'échec, garde le reste pour plus tard."""
        if not self.en_attente or not self.__connecter():
            return
        try:
            for attente, enregistrer in (
                (self.__passages, self.__acces.enregistrer_passages),
                (self.__releves, self.__acces.enregistrer_densites),
                (self.__connexions, self.__acces.enregistrer_connexions),
            ):
                lot = list(attente)
                enregistrer(lot)
                # Retirés seulement une fois validés : un lot refusé sera réessayé tel quel.
                for _ in lot:
                    attente.popleft()
        except BddError as erreur:
            self.__signaler_panne(erreur)

    def __repondre(self, numero: int) -> None:
        """Lit les statistiques et dépose la réponse ; base injoignable, la réponse le dit."""
        # Ce qui attend est écrit d'abord, pour que les statistiques le comptent.
        self.__ecrire()
        if not self.__connecter(forcer=True):
            self.__reponses.put((numero, {"disponible": False, "raison": f"base injoignable ({self.__acces.adresse})"}))
            return
        try:
            statistiques = self.__acces.lire_statistiques(NOMBRE_PASSAGES_LUS, NOMBRE_RELEVES_LUS)
        except BddError as erreur:
            self.__signaler_panne(erreur)
            self.__reponses.put((numero, {"disponible": False, "raison": str(erreur)}))
            return
        self.__reponses.put((numero, {"disponible": True, **statistiques}))

    def __connecter(self, forcer: bool = False) -> bool:
        """Ouvre la connexion si besoin ; entre deux échecs, attend le délai de nouvel essai.

        Une demande de statistiques force une tentative : la supervision attend une réponse.
        """
        if self.__acces.connectee:
            return True
        if not forcer and time.monotonic() < self.__prochain_essai:
            return False
        try:
            self.__acces.connecter()
        except BddError as erreur:
            self.__signaler_panne(erreur)
            return False
        if self.__en_panne:
            journal.info(
                "base de nouveau joignable (%s) : écriture de %d enregistrement(s)",
                self.__acces.adresse,
                self.en_attente,
            )
            self.__en_panne = False
        return True

    def __signaler_panne(self, erreur: BddError) -> None:
        """Ferme la connexion, programme un nouvel essai et journalise la panne une seule fois."""
        self.__acces.fermer()
        self.__prochain_essai = time.monotonic() + self.__delai_reessai
        if not self.__en_panne:
            journal.warning("historique non écrit : %s ; nouvel essai toutes les %g s", erreur, self.__delai_reessai)
            self.__en_panne = True
