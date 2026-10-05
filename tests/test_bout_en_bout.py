"""Test de bout en bout : un VP traverse avec puis sans régulation, vrai serveur et vrais clients."""

import random
import socket
from collections.abc import Callable

from outils import DELAI, attendre

from cherrypie.client.client_usager import ClientUsager
from cherrypie.commun.config import Configuration
from cherrypie.commun.protocole import Message, TypeMessage
from cherrypie.commun.securite import Signataire
from cherrypie.commun.trame import DecoupeurTrames
from cherrypie.modele.usager import Moto, Pieton, Trottinette, Usager, VehiculePrioritaire, Voiture
from cherrypie.serveur.passages import PassageVp
from cherrypie.serveur.serveur import Serveur

GRAINE = 1
# Délais courts et petit anneau, pour que chaque traversée tienne en quelques secondes.
REGLAGES = {
    "intervalle_position": "0.05",
    "intervalle_ping": "0.1",
    "timeout_client": "0.5",
    "backoff_initial": "0.1",
    "backoff_max": "0.4",
    "rayon": "10",
}
DUREE_MAX_TRAVERSEE = 60.0


def regler(serveur: Serveur, regulation: bool) -> None:
    """Active ou coupe la régulation comme le fait la supervision : ABONNEMENT puis REGLAGE."""
    config = serveur.config
    signataire = Signataire(config.cle_hmac)
    with socket.create_connection((config.hote, config.port_tcp), timeout=DELAI) as prise:
        for message in (
            Message(TypeMessage.ABONNEMENT, "supervision"),
            Message(TypeMessage.REGLAGE, "supervision", {"regulation": regulation}),
        ):
            prise.sendall(DecoupeurTrames.encoder(signataire.signer(message).vers_octets()))
        attendre(lambda: serveur.logique.regulation_active is regulation)


def trafic(hasard: random.Random) -> list[tuple[Usager, float]]:
    """Usagers du scénario et leur avancement de départ, tirés au hasard avec une graine fixe.

    Trois voitures sont en file devant le VP sur sa branche d'entrée, quatre véhicules
    arrivent par l'est et l'ouest, et deux piétons s'apprêtent à traverser sur les branches
    d'entrée et de sortie du VP. Le VP part en dernier, du bout de la branche sud.
    """
    usagers: list[tuple[Usager, float]] = []
    for rang in range(3):
        usagers.append((Voiture(f"voiture_S{rang}", "S", hasard.choice(["E", "N", "O"])), 40.0 - rang * 12.0))
    for entree in ["E", "O"]:
        for rang in range(2):
            categorie = hasard.choice([Voiture, Moto, Trottinette])
            sortie = hasard.choice([branche for branche in "NESO" if branche != entree])
            usagers.append((categorie(f"{categorie.CATEGORIE}_{entree}{rang}", entree, sortie), 45.0 - rang * 10.0))
    for branche in ["S", "N"]:
        usagers.append((Pieton(f"pieton_{branche}", branche, branche), hasard.uniform(0.0, 3.0)))
    usagers.append((VehiculePrioritaire("vp_1", "S", "N"), 0.0))
    return usagers


def traversee(
    lancer_serveur: Callable[..., Serveur], preparer_client: Callable[..., ClientUsager], regulation: bool
) -> PassageVp:
    """Joue le scénario sur un serveur neuf et renvoie la mesure de la traversée du VP."""
    serveur = lancer_serveur(**REGLAGES)
    regler(serveur, regulation)
    clients = []
    for usager, avancement in trafic(random.Random(GRAINE)):
        client = preparer_client(serveur.config, usager)
        client.deplacement.avancer(avancement / usager.VITESSE_MAX)
        clients.append(client)
    for client in clients:
        client.start()
    attendre(lambda: bool(serveur.logique.passages), delai=DUREE_MAX_TRAVERSEE)
    for client in clients:
        client.arreter()
    return serveur.logique.passages[0]


def test_vp_traverse_plus_vite_avec_la_regulation(
    lancer_serveur: Callable[..., Serveur], preparer_client: Callable[..., ClientUsager]
) -> None:
    avec = traversee(lancer_serveur, preparer_client, regulation=True)
    sans = traversee(lancer_serveur, preparer_client, regulation=False)
    assert (avec.regulation, sans.regulation) == (True, False)
    assert avec.duree < sans.duree
