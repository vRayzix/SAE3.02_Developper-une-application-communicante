"""Tests du client usager face à un vrai serveur, sur 127.0.0.1."""

import math
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from outils import DELAI, attendre

from cherrypie.client.client_usager import ClientUsager, EtatConnexion
from cherrypie.client.deplacement import DISTANCE_SECURITE
from cherrypie.commun.config import Configuration
from cherrypie.commun.protocole import CodeNotification, Enveloppe, Message, TypeMessage
from cherrypie.commun.securite import Signataire
from cherrypie.commun.trame import DecoupeurTrames
from cherrypie.modele.trajectoire import LONGUEUR_BRANCHE
from cherrypie.modele.usager import FACTEUR_RALENTISSEMENT, Usager, VehiculePrioritaire, Voiture
from cherrypie.serveur.serveur import Serveur

# Délais courts, pour que les tests de heartbeat et de reconnexion restent rapides.
DELAIS_RAPIDES = {
    "intervalle_position": "0.05",
    "intervalle_ping": "0.1",
    "timeout_client": "0.5",
    "backoff_initial": "0.1",
    "backoff_max": "0.4",
}


class FauxServeur:
    """Serveur minimal qui accepte un client et lui envoie les messages choisis par le test.

    Le vrai serveur n'enverra de NOTIF qu'avec la régulation ; celui-ci parle déjà le même
    protocole (trames signées sur TCP) pour tester la réaction du client aux consignes.
    """

    def __init__(self, config: Configuration) -> None:
        self.__config = config
        self.__signataire = Signataire(config.cle_hmac)
        self.__decoupeur = DecoupeurTrames()
        self.__ecoute = socket.create_server((config.hote, config.port_tcp))
        self.__ecoute.settimeout(DELAI)
        self.__connexion: socket.socket | None = None

    @property
    def config(self) -> Configuration:
        return self.__config

    @property
    def signataire(self) -> Signataire:
        return self.__signataire

    @property
    def decoupeur(self) -> DecoupeurTrames:
        return self.__decoupeur

    @property
    def ecoute(self) -> socket.socket:
        return self.__ecoute

    @property
    def connexion(self) -> socket.socket | None:
        return self.__connexion

    def accepter(self) -> Message:
        """Accepte la connexion du client et renvoie son HELLO, sans y répondre."""
        self.__connexion, _ = self.__ecoute.accept()
        self.__connexion.settimeout(DELAI)
        return self.recevoir(TypeMessage.HELLO)

    def recevoir(self, type_attendu: TypeMessage) -> Message:
        """Renvoie le prochain message du client du type attendu, en sautant les autres (PING...)."""
        while True:
            octets = self.__connexion.recv(65536)
            if not octets:
                raise ConnectionError("le client a fermé la connexion")
            for trame in self.__decoupeur.ajouter(octets):
                message = Enveloppe.depuis_octets(trame).message
                if message.type is type_attendu:
                    return message

    def envoyer(self, *messages: Message) -> None:
        """Signe les messages et les envoie d'un seul bloc, qui peut arriver en une seule lecture."""
        trames = [DecoupeurTrames.encoder(self.__signataire.signer(message).vers_octets()) for message in messages]
        self.__connexion.sendall(b"".join(trames))

    def fermer(self) -> None:
        if self.__connexion is not None:
            self.__connexion.close()
        self.__ecoute.close()


def accuse_d_inscription() -> Message:
    return Message(TypeMessage.HELLO_ACK, "serveur", {"accepte": True})


def consigne(code: CodeNotification, texte: str = "") -> Message:
    return Message(TypeMessage.NOTIF, "serveur", {"code": code.value, "message": texte})


@pytest.fixture
def faux_serveur(fabrique_config: Callable[..., Configuration]) -> Iterator[FauxServeur]:
    # Le faux serveur ne répond pas aux PING : un timeout long évite que le client le croie tombé.
    serveur = FauxServeur(fabrique_config(**{**DELAIS_RAPIDES, "timeout_client": "5"}))
    yield serveur
    serveur.fermer()


@pytest.fixture
def preparer_client() -> Iterator[Callable[..., ClientUsager]]:
    """Prépare des clients, à démarrer avec start(), puis les arrête à la fin du test."""
    prepares: list[ClientUsager] = []

    def preparer(config: Configuration, usager: Usager | None = None, **rappels: Callable) -> ClientUsager:
        client = ClientUsager(config, usager or Voiture("voiture_12", "S", "N"), **rappels)
        prepares.append(client)
        return client

    yield preparer
    for client in prepares:
        client.arreter()
        if client.is_alive():
            client.join(timeout=DELAI)


@pytest.fixture
def serveur(lancer_serveur: Callable[..., Serveur]) -> Serveur:
    return lancer_serveur(**DELAIS_RAPIDES)


# ---------- Connexion et heartbeat ----------

def test_client_inscrit_aupres_du_serveur(serveur: Serveur, preparer_client: Callable[..., ClientUsager]) -> None:
    etats: list[EtatConnexion] = []
    client = preparer_client(serveur.config, sur_connexion=lambda etat, detail: etats.append(etat))
    client.start()
    attendre(lambda: serveur.logique.registre.contient("voiture_12"))
    attendre(lambda: client.etat is EtatConnexion.CONNECTE)
    assert etats[:2] == [EtatConnexion.CONNEXION, EtatConnexion.CONNECTE]


def test_ping_garde_le_client_inscrit_au_dela_du_timeout(
    serveur: Serveur, preparer_client: Callable[..., ClientUsager]
) -> None:
    client = preparer_client(serveur.config)
    client.start()
    attendre(lambda: client.etat is EtatConnexion.CONNECTE)
    time.sleep(3 * serveur.config.timeout_client)
    assert serveur.logique.registre.contient("voiture_12")
    assert client.etat is EtatConnexion.CONNECTE


def test_client_ne_depend_pas_de_qt() -> None:
    racine = Path(__file__).resolve().parent.parent
    environnement = {**os.environ, "PYTHONPATH": str(racine / "src")}
    resultat = subprocess.run(
        [sys.executable, "-c", "import sys, cherrypie.client.client_usager; print('PyQt6' in sys.modules)"],
        capture_output=True, text=True, env=environnement, check=True,
    )
    assert resultat.stdout.strip() == "False"


# ---------- Arrêt ----------

def test_arret_propre_avec_au_revoir(serveur: Serveur, preparer_client: Callable[..., ClientUsager]) -> None:
    client = preparer_client(serveur.config)
    client.start()
    attendre(lambda: serveur.logique.registre.contient("voiture_12"))
    debut = time.monotonic()
    client.arreter()
    client.join(timeout=DELAI)
    assert not client.is_alive()
    assert client.etat is EtatConnexion.TERMINE
    attendre(lambda: not serveur.logique.registre.contient("voiture_12"))
    # Le BYE fait retirer l'usager tout de suite, sans attendre le timeout du serveur.
    assert time.monotonic() - debut < serveur.config.timeout_client


def test_arret_pendant_l_attente_entre_deux_essais(
    fabrique_config: Callable[..., Configuration], preparer_client: Callable[..., ClientUsager]
) -> None:
    config = fabrique_config(**{**DELAIS_RAPIDES, "backoff_initial": "5", "backoff_max": "10"})
    client = preparer_client(config)
    client.start()
    attendre(lambda: client.etat is EtatConnexion.DECONNECTE)
    debut = time.monotonic()
    client.arreter()
    client.join(timeout=DELAI)
    assert not client.is_alive()
    assert time.monotonic() - debut < 1.0


# ---------- Reconnexion ----------

def test_reconnexion_apres_coupure_du_serveur(
    lancer_serveur: Callable[..., Serveur], preparer_client: Callable[..., ClientUsager]
) -> None:
    premier = lancer_serveur(**DELAIS_RAPIDES)
    etats: list[EtatConnexion] = []
    client = preparer_client(premier.config, sur_connexion=lambda etat, detail: etats.append(etat))
    client.start()
    attendre(lambda: premier.logique.registre.contient("voiture_12"))
    premier.arreter()
    attendre(lambda: EtatConnexion.DECONNECTE in etats)
    attendre(lambda: premier.ecoute_tcp.fileno() == -1 and premier.socket_udp.fileno() == -1)
    second = lancer_serveur(premier.config)
    attendre(lambda: second.logique.registre.contient("voiture_12"))
    # Le serveur inscrit l'usager juste avant que le client reçoive le HELLO_ACK : on
    # attend le second CONNECTE au lieu de le supposer déjà signalé.
    attendre(lambda: etats.count(EtatConnexion.CONNECTE) == 2)


def test_essais_espaces_par_un_delai_qui_double(
    fabrique_config: Callable[..., Configuration], preparer_client: Callable[..., ClientUsager]
) -> None:
    instants: list[float] = []

    def noter_les_essais(etat: EtatConnexion, detail: str) -> None:
        if etat is EtatConnexion.CONNEXION:
            instants.append(time.monotonic())

    client = preparer_client(fabrique_config(**DELAIS_RAPIDES), sur_connexion=noter_les_essais)
    client.start()
    attendre(lambda: len(instants) >= 5)
    ecarts = [suivant - precedent for precedent, suivant in zip(instants, instants[1:])]
    assert ecarts[:4] == pytest.approx([0.1, 0.2, 0.4, 0.4], abs=0.08)


def test_identifiant_deja_connecte_refuse_puis_inscrit(
    serveur: Serveur, preparer_client: Callable[..., ClientUsager]
) -> None:
    premier = preparer_client(serveur.config)
    premier.start()
    attendre(lambda: premier.etat is EtatConnexion.CONNECTE)
    details: list[str] = []
    second = preparer_client(serveur.config, sur_connexion=lambda etat, detail: details.append(detail))
    second.start()
    attendre(lambda: any("déjà connecté" in detail for detail in details))
    premier.arreter()
    premier.join(timeout=DELAI)
    attendre(lambda: second.etat is EtatConnexion.CONNECTE)


def test_refus_definitif_arrete_le_client(
    lancer_serveur: Callable[..., Serveur],
    fabrique_config: Callable[..., Configuration],
    preparer_client: Callable[..., ClientUsager],
) -> None:
    serveur = lancer_serveur(**DELAIS_RAPIDES, branches="A, B, C")
    # Le client croit à un rond-point N, E, S, O : le serveur ne connaît pas ses branches.
    ports = {"port_tcp": str(serveur.config.port_tcp), "port_udp": str(serveur.config.port_udp)}
    details: list[str] = []
    client = preparer_client(
        fabrique_config(**DELAIS_RAPIDES, **ports), sur_connexion=lambda etat, detail: details.append(detail)
    )
    client.start()
    client.join(timeout=DELAI)
    assert not client.is_alive()
    assert client.etat is EtatConnexion.TERMINE
    assert "branche inconnue" in details[-1]


# ---------- Déplacement et positions ----------

def test_positions_recues_par_le_registre(serveur: Serveur, preparer_client: Callable[..., ClientUsager]) -> None:
    client = preparer_client(serveur.config)
    client.start()
    attendre(lambda: serveur.logique.registre.contient("voiture_12"))
    vue_du_serveur = serveur.logique.registre.obtenir("voiture_12")
    attendre(lambda: vue_du_serveur.position is not None)
    premiere = vue_du_serveur.position
    attendre(lambda: vue_du_serveur.position != premiere)
    assert vue_du_serveur.vitesse == pytest.approx(Voiture.VITESSE_MAX)


def test_position_signalee_a_chaque_pas(serveur: Serveur, preparer_client: Callable[..., ClientUsager]) -> None:
    positions: list[dict] = []
    client = preparer_client(serveur.config, sur_position=positions.append)
    client.start()
    attendre(lambda: len(positions) >= 5)
    assert {etat["id"] for etat in positions} == {"voiture_12"}
    # Venue du sud, la voiture remonte sa branche vers le nord : y augmente à chaque pas.
    ordonnees = [etat["y"] for etat in positions[:5]]
    assert ordonnees == sorted(ordonnees)
    assert len(set(ordonnees)) == 5


def test_fin_de_trajet_au_revoir_puis_arret(serveur: Serveur, preparer_client: Callable[..., ClientUsager]) -> None:
    etats: list[tuple[EtatConnexion, str]] = []
    client = preparer_client(serveur.config, sur_connexion=lambda etat, detail: etats.append((etat, detail)))
    # Placé à deux mètres du bout de sa trajectoire, l'usager finit son trajet en quelques pas.
    client.deplacement.avancer((client.deplacement.trajectoire.longueur - 2.0) / Voiture.VITESSE_MAX)
    client.start()
    client.join(timeout=DELAI)
    assert not client.is_alive()
    assert client.deplacement.termine
    assert (EtatConnexion.CONNECTE, "inscrit auprès du serveur") in etats
    assert etats[-1] == (EtatConnexion.TERMINE, "trajet terminé")
    attendre(lambda: not serveur.logique.registre.contient("voiture_12"))


# ---------- Réaction aux consignes ----------

def test_consigne_arrivee_avec_l_accuse_d_inscription_appliquee(
    faux_serveur: FauxServeur, preparer_client: Callable[..., ClientUsager]
) -> None:
    consignes: list[CodeNotification] = []
    client = preparer_client(
        faux_serveur.config, sur_notification=lambda code, texte, appliquee: consignes.append(code)
    )
    client.start()
    faux_serveur.accepter()
    faux_serveur.envoyer(accuse_d_inscription(), consigne(CodeNotification.CHANGEZ_VOIE))
    attendre(lambda: consignes == [CodeNotification.CHANGEZ_VOIE])
    assert client.usager.consigne is CodeNotification.CHANGEZ_VOIE


def test_attendez_arrete_sur_la_ligne_jusqu_a_ok_passer(
    faux_serveur: FauxServeur, preparer_client: Callable[..., ClientUsager]
) -> None:
    client = preparer_client(faux_serveur.config)
    ligne = client.deplacement.trajectoire.longueur_approche
    # Placé à deux mètres de la ligne d'entrée, l'usager l'atteint en quelques pas.
    client.deplacement.avancer((ligne - 2.0) / Voiture.VITESSE_MAX)
    client.start()
    faux_serveur.accepter()
    faux_serveur.envoyer(accuse_d_inscription(), consigne(CodeNotification.ATTENDEZ, "véhicule prioritaire en approche"))
    attendre(lambda: client.deplacement.avancement == pytest.approx(ligne))
    time.sleep(5 * float(DELAIS_RAPIDES["intervalle_position"]))
    assert client.deplacement.avancement == pytest.approx(ligne)
    assert client.usager.vitesse == 0.0
    faux_serveur.envoyer(consigne(CodeNotification.OK_PASSER))
    attendre(lambda: client.deplacement.avancement > ligne + 1.0)


def test_consigne_signalee_par_rappel(faux_serveur: FauxServeur, preparer_client: Callable[..., ClientUsager]) -> None:
    recues: list[tuple[CodeNotification, str, bool]] = []
    client = preparer_client(
        faux_serveur.config, sur_notification=lambda code, texte, appliquee: recues.append((code, texte, appliquee))
    )
    client.start()
    faux_serveur.accepter()
    faux_serveur.envoyer(accuse_d_inscription())
    faux_serveur.envoyer(consigne(CodeNotification.DEGAGEZ, "véhicule prioritaire derrière vous"))
    attendre(lambda: recues == [(CodeNotification.DEGAGEZ, "véhicule prioritaire derrière vous", True)])


def test_degagez_ralentit_l_usager(faux_serveur: FauxServeur, preparer_client: Callable[..., ClientUsager]) -> None:
    positions: list[dict] = []
    client = preparer_client(faux_serveur.config, sur_position=positions.append)
    client.start()
    faux_serveur.accepter()
    faux_serveur.envoyer(accuse_d_inscription(), consigne(CodeNotification.DEGAGEZ))
    attendre(lambda: positions and positions[-1]["consigne"] == "DEGAGEZ")
    attendre(lambda: positions[-1]["vitesse"] == pytest.approx(Voiture.VITESSE_MAX * FACTEUR_RALENTISSEMENT))


def test_vehicule_prioritaire_ignore_les_consignes(
    faux_serveur: FauxServeur, preparer_client: Callable[..., ClientUsager]
) -> None:
    recues: list[tuple[CodeNotification, str, bool]] = []
    client = preparer_client(
        faux_serveur.config,
        VehiculePrioritaire("vp_1", "S", "N"),
        sur_notification=lambda code, texte, appliquee: recues.append((code, texte, appliquee)),
    )
    client.start()
    faux_serveur.accepter()
    faux_serveur.envoyer(accuse_d_inscription(), consigne(CodeNotification.ATTENDEZ))
    attendre(lambda: recues == [(CodeNotification.ATTENDEZ, "", False)])
    assert client.usager.consigne is None


def test_consigne_inconnue_ignoree(
    faux_serveur: FauxServeur, preparer_client: Callable[..., ClientUsager], caplog: pytest.LogCaptureFixture
) -> None:
    client = preparer_client(faux_serveur.config)
    client.start()
    faux_serveur.accepter()
    inconnue = Message(TypeMessage.NOTIF, "serveur", {"code": "DECOLLEZ", "message": ""})
    faux_serveur.envoyer(accuse_d_inscription(), inconnue, consigne(CodeNotification.ATTENDEZ))
    attendre(lambda: client.usager.consigne is CodeNotification.ATTENDEZ)
    assert "consigne inconnue" in caplog.text
    assert client.etat is EtatConnexion.CONNECTE


# ---------- Véhicule prioritaire ----------

def test_vp_s_annonce_des_son_inscription(faux_serveur: FauxServeur, preparer_client: Callable[..., ClientUsager]) -> None:
    client = preparer_client(faux_serveur.config, VehiculePrioritaire("vp_1", "S", "N"))
    client.start()
    faux_serveur.accepter()
    faux_serveur.envoyer(accuse_d_inscription())
    annonce = faux_serveur.recevoir(TypeMessage.VP_ALERT)
    eta = LONGUEUR_BRANCHE / VehiculePrioritaire.VITESSE_MAX
    assert annonce.donnees == {"entree": "S", "sortie": "N", "eta": pytest.approx(eta)}


def test_traversee_d_un_vp_mesuree_par_le_serveur(
    lancer_serveur: Callable[..., Serveur], preparer_client: Callable[..., ClientUsager]
) -> None:
    # Petit anneau et VP placé juste avant la ligne : la traversée dure moins d'une seconde.
    serveur = lancer_serveur(**DELAIS_RAPIDES, rayon="5")
    client = preparer_client(serveur.config, VehiculePrioritaire("vp_1", "S", "E"))
    ligne = client.deplacement.trajectoire.longueur_approche
    client.deplacement.avancer((ligne - 1.0) / VehiculePrioritaire.VITESSE_MAX)
    client.start()
    attendre(lambda: serveur.logique.vp_actif)
    attendre(lambda: len(serveur.logique.passages) == 1)
    (mesure,) = serveur.logique.passages
    quart_d_anneau = 2 * math.pi * 5 / 4
    assert mesure.duree == pytest.approx(quart_d_anneau / VehiculePrioritaire.VITESSE_MAX, abs=0.15)
    assert (mesure.identifiant, mesure.entree, mesure.sortie, mesure.regulation) == ("vp_1", "S", "E", True)
    assert not serveur.logique.vp_actif


# ---------- Ce que voit le conducteur ----------

def devant(distance: float | None, ceder: bool = False) -> Message:
    return Message(TypeMessage.DEVANT, "serveur", {"distance": distance, "ceder": ceder})


def test_distance_de_securite_gardee_puis_voie_libre(
    faux_serveur: FauxServeur, preparer_client: Callable[..., ClientUsager]
) -> None:
    client = preparer_client(faux_serveur.config)
    client.start()
    faux_serveur.accepter()
    faux_serveur.envoyer(accuse_d_inscription(), devant(10.0))
    attendre(lambda: client.deplacement.limite is not None)
    limite = client.deplacement.limite
    time.sleep(10 * float(DELAIS_RAPIDES["intervalle_position"]))
    assert client.deplacement.avancement == pytest.approx(limite)
    faux_serveur.envoyer(devant(None))
    attendre(lambda: client.deplacement.avancement > limite + 1.0)


def test_cedez_le_passage_arrete_sur_la_ligne(
    faux_serveur: FauxServeur, preparer_client: Callable[..., ClientUsager]
) -> None:
    client = preparer_client(faux_serveur.config)
    ligne = client.deplacement.trajectoire.longueur_approche
    client.deplacement.avancer((ligne - 2.0) / Voiture.VITESSE_MAX)
    client.start()
    faux_serveur.accepter()
    faux_serveur.envoyer(accuse_d_inscription(), devant(None, ceder=True))
    attendre(lambda: client.deplacement.avancement == pytest.approx(ligne))
    faux_serveur.envoyer(devant(None, ceder=False))
    attendre(lambda: client.deplacement.avancement > ligne + 1.0)


def test_devant_malforme_ignore(
    faux_serveur: FauxServeur, preparer_client: Callable[..., ClientUsager], caplog: pytest.LogCaptureFixture
) -> None:
    client = preparer_client(faux_serveur.config)
    client.start()
    faux_serveur.accepter()
    malforme = Message(TypeMessage.DEVANT, "serveur", {"distance": "proche", "ceder": False})
    faux_serveur.envoyer(accuse_d_inscription(), malforme, consigne(CodeNotification.ATTENDEZ))
    attendre(lambda: client.usager.consigne is CodeNotification.ATTENDEZ)
    assert "DEVANT invalide" in caplog.text
    assert client.deplacement.limite is None


def test_deux_voitures_sur_la_meme_branche_gardent_leurs_distances(
    serveur: Serveur, preparer_client: Callable[..., ClientUsager]
) -> None:
    devant_client = preparer_client(serveur.config, Voiture("voiture_1", "N", "S"))
    derriere_client = preparer_client(serveur.config, Voiture("voiture_2", "N", "S"))
    # Elles partent à 3 m l'une de l'autre : celle de derrière doit se laisser distancer.
    devant_client.deplacement.avancer(3.0 / Voiture.VITESSE_MAX)
    devant_client.start()
    derriere_client.start()
    attendre(lambda: devant_client.deplacement.avancement > 15.0)
    ecart = devant_client.deplacement.avancement - derriere_client.deplacement.avancement
    pas_maximal = Voiture.VITESSE_MAX * float(DELAIS_RAPIDES["intervalle_position"])
    assert ecart >= DISTANCE_SECURITE - pas_maximal
