"""Scénarios de circulation simulés sans réseau, pas à pas."""

import math
import random

import pytest
from simulation import Simulation

from cherrypie.client.deplacement import DISTANCE_SECURITE
from cherrypie.commun.protocole import CodeNotification
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import LONGUEUR_BRANCHE, Etape
from cherrypie.modele.usager import Moto, Trottinette, Voiture

BRANCHES = ["N", "E", "S", "O"]
RAYON = 20.0
# Écart minimal entre deux véhicules sur l'anneau : en dessous, ils se chevaucheraient.
ECART_SANS_CHEVAUCHEMENT = 3.0


@pytest.fixture
def simulation() -> Simulation:
    return Simulation(RondPoint(BRANCHES, RAYON, 8))


# ---------- File d'attente ----------

def test_usagers_arretes_font_la_file_sans_s_empiler(simulation: Simulation) -> None:
    voitures = [Voiture(f"voiture_{numero}", "N", "S") for numero in range(4)]
    deplacements = [simulation.ajouter(voiture) for voiture in voitures]
    for voiture in voitures:
        voiture.reagir(CodeNotification.ATTENDEZ)
    simulation.avancer_jusqu_a(lambda: False, duree_max=20.0)
    avancements = [deplacement.avancement for deplacement in deplacements]
    assert avancements[0] == pytest.approx(LONGUEUR_BRANCHE)
    for devant, derriere in zip(avancements, avancements[1:]):
        assert devant - derriere >= DISTANCE_SECURITE - 1e-6
    assert all(voiture.vitesse == 0.0 for voiture in voitures)


def test_la_file_repart_quand_l_attente_est_levee(simulation: Simulation) -> None:
    voitures = [Voiture(f"voiture_{numero}", "N", "S") for numero in range(3)]
    for voiture in voitures:
        simulation.ajouter(voiture)
        voiture.reagir(CodeNotification.ATTENDEZ)
    simulation.avancer_jusqu_a(lambda: False, duree_max=15.0)
    for voiture in voitures:
        voiture.reagir(CodeNotification.OK_PASSER)
    assert simulation.avancer_jusqu_a(lambda: not simulation.en_route, duree_max=60.0)


# ---------- Anneau chargé ----------

def ecarts_sur_l_anneau(simulation: Simulation) -> list[float]:
    """Écarts, le long de l'anneau, entre véhicules consécutifs qui roulent au milieu de la voie."""
    angles = sorted(
        math.atan2(deplacement.usager.position.y, deplacement.usager.position.x) % math.tau
        for deplacement in simulation.en_route
        if deplacement.usager.etape is Etape.ANNEAU
    )
    if len(angles) < 2:
        return []
    return [RAYON * ((suivant - angle) % math.tau) for angle, suivant in zip(angles, angles[1:] + angles[:1])]


def test_anneau_charge_ne_se_bloque_pas(simulation: Simulation) -> None:
    hasard = random.Random(2024)
    categories = [Voiture, Moto, Trottinette]
    for entree in BRANCHES:
        for rang in range(6):
            categorie = hasard.choice(categories)
            sortie = hasard.choice([branche for branche in BRANCHES if branche != entree])
            usager = categorie(f"{categorie.CATEGORIE}_{entree}{rang}", entree, sortie)
            # Six véhicules à la file sur chaque branche, tous lancés ensemble.
            simulation.ajouter(usager, avancement=LONGUEUR_BRANCHE - 5.0 - rang * 7.0)
    ecart_minimal = math.inf

    def tous_sortis() -> bool:
        nonlocal ecart_minimal
        ecart_minimal = min([ecart_minimal, *ecarts_sur_l_anneau(simulation)])
        return not simulation.en_route

    assert simulation.avancer_jusqu_a(tous_sortis, duree_max=300.0), "l'anneau s'est bloqué"
    assert ecart_minimal >= ECART_SANS_CHEVAUCHEMENT
