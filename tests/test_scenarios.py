"""Scénarios de circulation simulés sans réseau, pas à pas."""

import math
import random

import pytest
from geometrie import rond_point_bel_air
from simulation import Simulation

from cherrypie.client.deplacement import DISTANCE_SECURITE
from cherrypie.commun.protocole import CodeNotification
from cherrypie.modele.trajectoire import Etape
from cherrypie.modele.usager import Moto, Pieton, Trottinette, VehiculePrioritaire, Voiture
from cherrypie.serveur.passages import PassageVp

BRANCHES = ["nations_nord", "jean_de_la_bruyere", "nations_sud", "albert_camus"]
LONGUEUR_BRANCHE = rond_point_bel_air().longueur_branche
# Écart minimal entre deux véhicules sur l'anneau : en dessous, ils se chevaucheraient.
ECART_SANS_CHEVAUCHEMENT = 3.0


@pytest.fixture
def simulation() -> Simulation:
    return Simulation(rond_point_bel_air())


# ---------- File d'attente ----------

def test_usagers_arretes_font_la_file_sans_s_empiler(simulation: Simulation) -> None:
    voitures = [Voiture(f"voiture_{numero}", "nations_nord", "nations_sud") for numero in range(4)]
    deplacements = [simulation.ajouter(voiture) for voiture in voitures]
    for voiture in voitures:
        voiture.reagir(CodeNotification.ATTENDEZ)
    simulation.avancer_jusqu_a(lambda: False, duree_max=20.0)
    avancements = [deplacement.avancement for deplacement in deplacements]
    assert avancements[0] == pytest.approx(deplacements[0].trajectoire.longueur_approche)
    for devant, derriere in zip(avancements, avancements[1:]):
        assert devant - derriere >= DISTANCE_SECURITE - 1e-6
    assert all(voiture.vitesse == 0.0 for voiture in voitures)


def test_la_file_repart_quand_l_attente_est_levee(simulation: Simulation) -> None:
    voitures = [Voiture(f"voiture_{numero}", "nations_nord", "nations_sud") for numero in range(3)]
    for voiture in voitures:
        simulation.ajouter(voiture)
        voiture.reagir(CodeNotification.ATTENDEZ)
    simulation.avancer_jusqu_a(lambda: False, duree_max=15.0)
    for voiture in voitures:
        voiture.reagir(CodeNotification.OK_PASSER)
    assert simulation.avancer_jusqu_a(lambda: not simulation.en_route, duree_max=60.0)


# ---------- Anneau chargé ----------

def ecarts_sur_l_anneau(simulation: Simulation) -> list[float]:
    """Écarts, le long de chaque voie de l'anneau, entre véhicules consécutifs de cette voie.

    Deux véhicules côte à côte sur des voies différentes ne se chevauchent pas : on
    compare chaque véhicule à ceux de sa voie, d'après sa distance au centre.
    """
    rayon_axe = simulation.rond_point.rayon
    ecarts = []
    for interieure in (True, False):
        positions = [
            deplacement.usager.position
            for deplacement in simulation.en_route
            if deplacement.usager.etape is Etape.ANNEAU
            and (math.hypot(deplacement.usager.position.x, deplacement.usager.position.y) < rayon_axe) is interieure
        ]
        if len(positions) < 2:
            continue
        angles = sorted(math.atan2(position.y, position.x) % math.tau for position in positions)
        rayon = min(math.hypot(position.x, position.y) for position in positions)
        ecarts += [rayon * ((suivant - angle) % math.tau) for angle, suivant in zip(angles, angles[1:] + angles[:1])]
    return ecarts


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


# ---------- Régulation ----------

def traversee_du_vp(graine: int, regulation: bool) -> PassageVp:
    """Fait traverser un VP du sud au nord dans un trafic tiré au hasard, toujours le même pour une graine."""
    simulation = Simulation(rond_point_bel_air())
    simulation.regler(regulation)
    hasard = random.Random(graine)
    for rang in range(3):
        sortie = hasard.choice(["jean_de_la_bruyere", "nations_nord", "albert_camus"])
        simulation.ajouter(Voiture(f"voiture_S{rang}", "nations_sud", sortie), avancement=40.0 - rang * 12.0)
    for entree in ["jean_de_la_bruyere", "albert_camus", "nations_nord"]:
        for rang in range(3):
            categorie = hasard.choice([Voiture, Moto, Trottinette])
            sortie = hasard.choice([branche for branche in BRANCHES if branche != entree])
            usager = categorie(f"{categorie.CATEGORIE}_{entree}{rang}", entree, sortie)
            simulation.ajouter(usager, avancement=45.0 - rang * 10.0)
    for branche in ["nations_sud", "nations_nord"]:
        simulation.ajouter(Pieton(f"pieton_{branche}", branche, branche), avancement=hasard.uniform(0.0, 3.0))
    simulation.ajouter(VehiculePrioritaire("vp_1", "nations_sud", "nations_nord"))
    assert simulation.avancer_jusqu_a(lambda: bool(simulation.logique.passages), duree_max=120.0)
    return simulation.logique.passages[0]


@pytest.mark.parametrize("graine", [1, 2, 3])
def test_vp_plus_rapide_avec_regulation(graine: int) -> None:
    avec = traversee_du_vp(graine, regulation=True)
    sans = traversee_du_vp(graine, regulation=False)
    assert (avec.regulation, sans.regulation) == (True, False)
    assert avec.duree < sans.duree


def test_meme_scenario_meme_resultat() -> None:
    assert traversee_du_vp(1, regulation=False).duree == traversee_du_vp(1, regulation=False).duree
