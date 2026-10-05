"""Tests du relais entre un client usager et l'IHM : les rappels arrivent en signaux dans le thread principal."""

import threading
from collections.abc import Callable

from outils import attendre_qt
from PyQt6.QtWidgets import QApplication

from cherrypie.client.client_usager import ClientUsager, EtatConnexion
from cherrypie.commun.protocole import CodeNotification
from cherrypie.ihm.relais_client import RelaisClient
from cherrypie.modele.usager import Voiture
from cherrypie.serveur.serveur import Serveur


class Recepteur:
    """Note les signaux reçus et le thread où chacun arrive."""

    def __init__(self, relais: RelaisClient) -> None:
        self.__recus: list[tuple] = []
        self.__threads: set[threading.Thread] = set()
        relais.position_changee.connect(self.__noter)
        relais.notification_recue.connect(self.__noter)
        relais.connexion_changee.connect(self.__noter)

    @property
    def recus(self) -> list[tuple]:
        return list(self.__recus)

    @property
    def threads(self) -> set[threading.Thread]:
        return set(self.__threads)

    def __noter(self, *arguments: object) -> None:
        self.__threads.add(threading.current_thread())
        self.__recus.append(arguments)


def depuis_un_thread(appel: Callable[[], None]) -> None:
    """Fait un appel depuis un thread de travail, comme le ferait un client."""
    fil = threading.Thread(target=appel)
    fil.start()
    fil.join()


# ---------- Rappels ----------


def test_position_relayee_dans_le_thread_principal(qapp: QApplication) -> None:
    relais = RelaisClient("voiture_12")
    recepteur = Recepteur(relais)
    depuis_un_thread(lambda: relais.sur_position({"id": "voiture_12", "x": 1.0}))
    attendre_qt(lambda: bool(recepteur.recus))
    assert recepteur.recus == [("voiture_12", {"id": "voiture_12", "x": 1.0})]
    assert recepteur.threads == {threading.main_thread()}


def test_notification_relayee_avec_son_code(qapp: QApplication) -> None:
    relais = RelaisClient("voiture_12")
    recepteur = Recepteur(relais)
    depuis_un_thread(lambda: relais.sur_notification(CodeNotification.ATTENDEZ, "attendez", True))
    attendre_qt(lambda: bool(recepteur.recus))
    assert recepteur.recus == [("voiture_12", "ATTENDEZ", "attendez", True)]


def test_connexion_relayee_avec_son_etat(qapp: QApplication) -> None:
    relais = RelaisClient("voiture_12")
    recepteur = Recepteur(relais)
    depuis_un_thread(lambda: relais.sur_connexion(EtatConnexion.CONNECTE, "inscrit"))
    attendre_qt(lambda: bool(recepteur.recus))
    assert recepteur.recus == [("voiture_12", "connecte", "inscrit")]


# ---------- Avec un vrai client ----------


def test_client_relie_au_relais(
    qapp: QApplication, lancer_serveur: Callable[..., Serveur], preparer_client: Callable[..., ClientUsager]
) -> None:
    serveur = lancer_serveur()
    relais = RelaisClient("voiture_12")
    recepteur = Recepteur(relais)
    client = preparer_client(
        serveur.config,
        Voiture("voiture_12", "S", "N"),
        sur_position=relais.sur_position,
        sur_notification=relais.sur_notification,
        sur_connexion=relais.sur_connexion,
    )
    client.start()
    attendre_qt(lambda: any(isinstance(recu[1], dict) for recu in recepteur.recus))
    assert ("voiture_12", "connecte", "inscrit auprès du serveur") in recepteur.recus
    assert recepteur.threads == {threading.main_thread()}
