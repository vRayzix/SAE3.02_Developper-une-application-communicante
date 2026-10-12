"""Scénarios de circulation simulés sans réseau, pas à pas."""

import math
import random
from dataclasses import dataclass

import pytest
from geometrie import rond_point_bel_air
from simulation import Simulation

from cherrypie.client.deplacement import TOLERANCE_RANGEMENT, Deplacement
from cherrypie.commun.protocole import CodeNotification
from cherrypie.ihm.style import GABARITS_CATEGORIE
from cherrypie.modele.trajectoire import LONGUEUR_INSERTION, Etape
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
        assert devant - derriere >= Voiture.DISTANCE_SECURITE - 1e-6
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


# ---------- Piétons ----------

def test_pietons_lances_ensemble_traversent_a_la_file(simulation: Simulation) -> None:
    pietons = [Pieton(f"pieton_{numero}", "nations_nord", "nations_nord") for numero in range(1, 5)]
    deplacements = [simulation.ajouter(pieton) for pieton in pietons]
    simulation.avancer_jusqu_a(lambda: False, duree_max=6.0)
    avancements = sorted((deplacement.avancement for deplacement in deplacements), reverse=True)
    for devant, derriere in zip(avancements, avancements[1:]):
        assert devant - derriere >= Pieton.DISTANCE_SECURITE - 1e-6
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


# ---------- Priorité du VP ----------

# Pas de la simulation, et écart toléré entre la traversée du VP dans un anneau chargé et à vide.
PAS_DE_SIMULATION = 0.2
ECART_TOLERE_A_VIDE = 0.1


def traversee_dans_un_anneau_charge(sortie_du_vp: str, charge: bool) -> tuple[PassageVp, float, int]:
    """Fait arriver un VP du boulevard des Nations (sud), régulation active.

    Avec charge, deux véhicules par branche font le tour de l'anneau au moment où le VP
    approche. Renvoie la mesure du VP, le temps qu'il a passé arrêté avant l'anneau et le
    nombre d'autres véhicules sur l'anneau quand il y est entré.
    """
    simulation = Simulation(rond_point_bel_air())
    if charge:
        for entree in BRANCHES:
            for rang, avancement in enumerate((LONGUEUR_BRANCHE + 3.0, LONGUEUR_BRANCHE + 20.0)):
                simulation.ajouter(Voiture(f"voiture_{entree}{rang}", entree, entree), avancement=avancement)
    vp = simulation.ajouter(VehiculePrioritaire("vp_1", "nations_sud", sortie_du_vp))
    arret = 0.0
    sur_l_anneau_a_l_entree: int | None = None

    def suivre() -> bool:
        nonlocal arret, sur_l_anneau_a_l_entree
        usager = vp.usager
        if usager.etape is Etape.APPROCHE and simulation.instant > 0 and usager.vitesse == 0.0:
            arret += PAS_DE_SIMULATION
        if usager.etape is Etape.ANNEAU and sur_l_anneau_a_l_entree is None:
            autres = [deplacement for deplacement in simulation.en_route if deplacement is not vp]
            sur_l_anneau_a_l_entree = sum(deplacement.usager.etape is Etape.ANNEAU for deplacement in autres)
        return bool(simulation.logique.passages)

    assert simulation.avancer_jusqu_a(suivre, duree_max=60.0)
    return simulation.logique.passages[0], arret, sur_l_anneau_a_l_entree or 0


@pytest.mark.parametrize("sortie_du_vp", ["nations_nord", "nations_sud"], ids=["trajet-normal", "demi-tour"])
def test_vp_regule_ne_cede_pas_aux_vehicules_de_l_anneau(sortie_du_vp: str) -> None:
    a_vide, _, _ = traversee_dans_un_anneau_charge(sortie_du_vp, charge=False)
    charge, arret, sur_l_anneau = traversee_dans_un_anneau_charge(sortie_du_vp, charge=True)
    assert sur_l_anneau >= 8
    assert arret <= PAS_DE_SIMULATION
    assert charge.duree <= a_vide.duree * (1 + ECART_TOLERE_A_VIDE)


# ---------- Civils sur la branche du VP ----------

# Délai entre deux départs sur la même branche, en secondes, comme dans un scénario lancé d'un bloc.
DELAI_ENTRE_DEPARTS = 1.0
# Espace minimal entre le VP et une voiture rangée qu'il double, en mètres, pour qu'on les distingue à l'écran.
ESPACE_VISIBLE = 0.3


def cote_a_cote(vp: Deplacement, voiture: Deplacement) -> bool:
    """Indique si deux usagers de la même chaussée se chevauchent dans le sens de la marche."""
    longueur_vp = GABARITS_CATEGORIE[VehiculePrioritaire.CATEGORIE][0]
    longueur_voiture = GABARITS_CATEGORIE[Voiture.CATEGORIE][0]
    return voiture.avancement - longueur_voiture < vp.avancement < voiture.avancement + longueur_vp


def espace_lateral(vp: Deplacement, voiture: Deplacement) -> float:
    """Espace entre les flancs de deux usagers côte à côte sur la même chaussée, tels que les dessine la scène."""
    demi_largeurs = (GABARITS_CATEGORIE[VehiculePrioritaire.CATEGORIE][1] + GABARITS_CATEGORIE[Voiture.CATEGORIE][1]) / 2
    return abs(voiture.decalage - vp.decalage) - demi_largeurs


@dataclass
class Civil:
    """Ce qu'a fait une voiture partie de la même branche que le VP, pendant sa traversée."""

    deplacement: Deplacement
    s_est_rangee: bool = False
    espace_avec_le_vp: float = math.inf
    consigne_a_la_sortie_du_vp: CodeNotification | None = None
    decalage_a_la_sortie_du_vp: float = 0.0


def vp_parti_avec_des_civils(sortie_du_vp: str, civils: bool) -> tuple[PassageVp, float, list[Civil], list[Civil]]:
    """Lance trois voitures, puis un VP et une dernière voiture, du boulevard des Nations (sud).

    Les départs sont espacés de DELAI_ENTRE_DEPARTS, régulation active. Pendant la
    traversée du VP, vérifie qu'aucune voiture n'entre sur l'anneau et qu'une voiture
    rangée devant lui ne roule plus tant qu'il ne l'a pas dépassée. Renvoie la mesure du
    VP, le temps qu'il a passé arrêté avant l'anneau, les voitures parties devant lui et
    celle partie derrière.
    """
    simulation = Simulation(rond_point_bel_air())
    devant: list[Civil] = []
    derriere: list[Civil] = []
    vp: Deplacement | None = None
    arret = 0.0

    def observer() -> None:
        nonlocal arret
        if vp is None or simulation.logique.passages:
            return
        if vp.usager.etape is Etape.APPROCHE and vp.usager.vitesse == 0.0:
            arret += PAS_DE_SIMULATION
        for civil in devant + derriere:
            voiture = civil.deplacement
            assert voiture.usager.etape is Etape.APPROCHE, f"{voiture.usager.identifiant} entre avant la sortie du VP"
            rangee = voiture.decalage >= voiture.trajectoire.place_a_droite_a(voiture.avancement) - TOLERANCE_RANGEMENT
            depassee = vp.usager.etape is not Etape.APPROCHE or vp.avancement > voiture.avancement
            # Le pas où elle finit de se ranger, elle roule encore : on regarde les pas suivants.
            if civil in devant and civil.s_est_rangee and rangee and not depassee:
                assert voiture.usager.vitesse == 0.0, f"{voiture.usager.identifiant} rangée mais roule encore"
            civil.s_est_rangee = civil.s_est_rangee or rangee
            if civil in devant and vp.usager.etape is Etape.APPROCHE and cote_a_cote(vp, voiture):
                civil.espace_avec_le_vp = min(civil.espace_avec_le_vp, espace_lateral(vp, voiture))
            civil.consigne_a_la_sortie_du_vp = voiture.usager.consigne
            civil.decalage_a_la_sortie_du_vp = voiture.decalage

    def partir(usager: Voiture | VehiculePrioritaire) -> Deplacement:
        depart = simulation.ajouter(usager)
        fin = simulation.instant + DELAI_ENTRE_DEPARTS

        def delai_ecoule() -> bool:
            observer()
            return simulation.instant >= fin - 1e-9

        assert simulation.avancer_jusqu_a(delai_ecoule, duree_max=60.0)
        return depart

    if civils:
        devant = [Civil(partir(Voiture(f"voiture_{rang}", "nations_sud", "albert_camus"))) for rang in range(3)]
    vp = partir(VehiculePrioritaire("vp_1", "nations_sud", sortie_du_vp))
    if civils:
        derriere = [Civil(partir(Voiture("voiture_3", "nations_sud", "albert_camus")))]

    def suivre() -> bool:
        observer()
        return bool(simulation.logique.passages)

    assert simulation.avancer_jusqu_a(suivre, duree_max=60.0)
    return simulation.logique.passages[0], arret, devant, derriere


@pytest.mark.parametrize("sortie_du_vp", ["nations_nord", "nations_sud"], ids=["trajet-normal", "demi-tour"])
def test_civils_devant_le_vp_se_rangent_et_s_arretent(sortie_du_vp: str) -> None:
    _, _, devant, derriere = vp_parti_avec_des_civils(sortie_du_vp, civils=True)
    assert all(civil.s_est_rangee for civil in devant)
    assert not any(civil.s_est_rangee for civil in derriere)
    # Le VP double chaque voiture rangée sans la toucher, avec un espace qu'on voit à l'écran.
    assert all(ESPACE_VISIBLE <= civil.espace_avec_le_vp < math.inf for civil in devant)


@pytest.mark.parametrize("sortie_du_vp", ["nations_nord", "nations_sud"], ids=["trajet-normal", "demi-tour"])
def test_vp_double_les_civils_ranges_sans_attendre(sortie_du_vp: str) -> None:
    seul, _, _, _ = vp_parti_avec_des_civils(sortie_du_vp, civils=False)
    double, arret, _, _ = vp_parti_avec_des_civils(sortie_du_vp, civils=True)
    assert arret <= PAS_DE_SIMULATION
    assert double.duree <= seul.duree * (1 + ECART_TOLERE_A_VIDE)


@pytest.mark.parametrize("sortie_du_vp", ["nations_nord", "nations_sud"], ids=["trajet-normal", "demi-tour"])
def test_civils_doubles_reprennent_leur_voie_et_attendent_la_sortie_du_vp(sortie_du_vp: str) -> None:
    _, _, devant, derriere = vp_parti_avec_des_civils(sortie_du_vp, civils=True)
    for civil in devant + derriere:
        assert civil.consigne_a_la_sortie_du_vp is CodeNotification.ATTENDEZ
        assert civil.decalage_a_la_sortie_du_vp == pytest.approx(0.0)


# ---------- Entrées pendant et après le passage du VP ----------

def deux_voitures_en_attente(regulation: bool = True) -> tuple[Simulation, list]:
    """Deux voitures à l'arrêt sur deux branches, dont le trajet croise celui d'un VP qui arrive du sud."""
    simulation = Simulation(rond_point_bel_air())
    simulation.regler(regulation)
    # À 10 m de leur ligne, elles y arrivent après la première cadence du serveur.
    avancement = LONGUEUR_BRANCHE - 10.0
    voitures = [
        simulation.ajouter(Voiture("voiture_a", "jean_de_la_bruyere", "nations_nord"), avancement=avancement),
        simulation.ajouter(Voiture("voiture_b", "albert_camus", "jean_de_la_bruyere"), avancement=avancement),
    ]
    simulation.ajouter(VehiculePrioritaire("vp_1", "nations_sud", "nations_nord"))
    return simulation, voitures


def test_aucune_voiture_en_conflit_n_entre_pendant_le_passage_du_vp() -> None:
    simulation, voitures = deux_voitures_en_attente()

    def vp_sorti() -> bool:
        assert all(voiture.usager.etape is Etape.APPROCHE for voiture in voitures), "une voiture est entrée"
        return bool(simulation.logique.passages)

    assert simulation.avancer_jusqu_a(vp_sorti, duree_max=60.0)


def entrees_simultanees(simulation: Simulation, voitures: list, duree_max: float) -> int:
    """Plus grand nombre de voitures en train de rejoindre l'anneau au même moment."""
    plus_grand = 0

    def toutes_entrees() -> bool:
        nonlocal plus_grand
        en_insertion = [
            voiture for voiture in voitures
            if voiture.usager.etape is Etape.ANNEAU
            and voiture.avancement - voiture.trajectoire.longueur_approche < LONGUEUR_INSERTION
        ]
        plus_grand = max(plus_grand, len(en_insertion))
        return all(voiture.usager.etape is not Etape.APPROCHE for voiture in voitures)

    assert simulation.avancer_jusqu_a(toutes_entrees, duree_max=duree_max)
    return plus_grand


def test_deux_voitures_en_attente_entrent_une_a_la_fois() -> None:
    simulation = Simulation(rond_point_bel_air())
    avancement = LONGUEUR_BRANCHE - 10.0
    voitures = [
        simulation.ajouter(Voiture("voiture_a", "jean_de_la_bruyere", "nations_nord"), avancement=avancement),
        simulation.ajouter(Voiture("voiture_b", "albert_camus", "jean_de_la_bruyere"), avancement=avancement),
    ]
    assert entrees_simultanees(simulation, voitures, duree_max=30.0) == 1


def test_apres_le_vp_les_voitures_en_attente_entrent_une_a_la_fois() -> None:
    simulation, voitures = deux_voitures_en_attente()
    assert simulation.avancer_jusqu_a(lambda: bool(simulation.logique.passages), duree_max=60.0)
    assert entrees_simultanees(simulation, voitures, duree_max=90.0) == 1


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


