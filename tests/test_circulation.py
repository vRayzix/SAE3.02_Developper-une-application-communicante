"""Tests de ce que voit chaque conducteur : file, voies, cédez-le-passage et passage piéton."""

import math

import pytest
from geometrie import ALBERT_CAMUS, JEAN_DE_LA_BRUYERE, NATIONS_NORD, NATIONS_SUD, rond_point_bel_air

from cherrypie.client.deplacement import Deplacement
from cherrypie.commun.protocole import CodeNotification
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import LONGUEUR_TROTTOIR, Trajectoire
from cherrypie.modele.usager import Pieton, Usager, VehiculePrioritaire, Voiture
from cherrypie.serveur.circulation import Chaussee, Circulation, Vue
from cherrypie.serveur.registre import Registre

LONGUEUR_BRANCHE = rond_point_bel_air().longueur_branche
# Pas utilisé pour chercher sur une trajectoire l'avancement d'un point donné, en mètres.
PAS_DE_RECHERCHE = 0.05
PART_MIN_DU_CHEMIN = 0.9


@pytest.fixture
def rond_point() -> RondPoint:
    return rond_point_bel_air()


@pytest.fixture
def registre() -> Registre:
    return Registre()


@pytest.fixture
def placer(rond_point: RondPoint, registre: Registre):
    """Place un usager à un avancement donné de sa trajectoire et l'inscrit au registre."""

    def placer_usager(usager: Usager, avancement: float, consigne: CodeNotification | None = None) -> Usager:
        if consigne is not None:
            usager.reagir(consigne)
        deplacement = Deplacement(usager, usager.calculer_trajectoire(rond_point))
        # En un seul pas, l'usager n'est pas encore rangé au départ : il roule à sa vitesse maximale.
        deplacement.avancer(avancement / usager.VITESSE_MAX)
        registre.ajouter(usager)
        return usager

    return placer_usager


def voir(rond_point: RondPoint, registre: Registre) -> dict[str, Vue]:
    return Circulation(rond_point).voir(registre)


def milieu_de_voie(rond_point: RondPoint, usager: Usager, segment: str) -> float:
    """Avancement au milieu du morceau de voie qu'un usager suit sur un segment."""
    avancement = 0.0
    for troncon in usager.calculer_trajectoire(rond_point).troncons:
        if troncon.segment is not None and troncon.segment.nom == segment and troncon.rayon_debut == troncon.rayon_fin:
            return avancement + troncon.longueur / 2
        avancement += troncon.longueur
    raise AssertionError(f"pas de voie suivie sur {segment}")


def debut_de_sortie(rond_point: RondPoint, usager: Usager) -> float:
    """Avancement où l'usager quitte l'anneau pour sa chaussée de sortie."""
    return usager.calculer_trajectoire(rond_point).longueur - rond_point.longueur_branche


def avancement_a_l_angle(trajectoire: Trajectoire, angle: float) -> float:
    """Premier avancement sur l'anneau où la position vue du centre atteint un angle, en degrés."""
    avancement = trajectoire.longueur_approche
    precedent = None
    while avancement <= trajectoire.longueur:
        position = trajectoire.position_a(avancement)
        courant = math.degrees(math.atan2(position.y, position.x)) % 360
        if precedent is not None and (angle - precedent) % 360 <= (courant - precedent) % 360:
            return avancement
        precedent, avancement = courant, avancement + PAS_DE_RECHERCHE
    raise AssertionError(f"angle {angle} jamais atteint")


# ---------- File sur une branche ----------

def test_voie_libre_sans_personne_devant(rond_point: RondPoint, registre: Registre, placer) -> None:
    # Loin de sa ligne, il n'a pas encore son tour d'entrée : il s'arrêterait sur la ligne.
    placer(Voiture("voiture_1", NATIONS_NORD, NATIONS_SUD), 10.0)
    assert voir(rond_point, registre) == {"voiture_1": Vue(None, True)}


def test_vehicule_voit_celui_qui_le_precede(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", NATIONS_NORD, NATIONS_SUD), 30.0)
    placer(Voiture("voiture_2", NATIONS_NORD, NATIONS_SUD), 20.0)
    vues = voir(rond_point, registre)
    assert vues["voiture_2"].distance == pytest.approx(10.0)
    assert vues["voiture_1"].distance is None


def test_au_meme_point_le_premier_arrive_passe_devant(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", NATIONS_NORD, NATIONS_SUD), 0.0)
    placer(Voiture("voiture_2", NATIONS_NORD, NATIONS_SUD), 0.0)
    vues = voir(rond_point, registre)
    assert vues["voiture_2"].distance == pytest.approx(0.0)
    assert vues["voiture_1"].distance is None


def test_vehicule_range_sur_le_cote_ne_gene_pas(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", NATIONS_NORD, NATIONS_SUD), 30.0, CodeNotification.CHANGEZ_VOIE)
    placer(Voiture("voiture_2", NATIONS_NORD, NATIONS_SUD), 20.0)
    assert voir(rond_point, registre)["voiture_2"].distance is None


def test_vehicules_ranges_font_la_file_entre_eux(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", NATIONS_NORD, NATIONS_SUD), 30.0, CodeNotification.CHANGEZ_VOIE)
    placer(Voiture("voiture_2", NATIONS_NORD, NATIONS_SUD), 20.0, CodeNotification.CHANGEZ_VOIE)
    assert voir(rond_point, registre)["voiture_2"].distance == pytest.approx(10.0)


def test_vehicule_en_sortie_voit_celui_qui_le_precede(rond_point: RondPoint, registre: Registre, placer) -> None:
    premiere = Voiture("voiture_1", NATIONS_SUD, NATIONS_NORD)
    sortie = debut_de_sortie(rond_point, premiere)
    placer(premiere, sortie + 25.0)
    placer(Voiture("voiture_2", NATIONS_SUD, NATIONS_NORD), sortie + 12.0)
    assert voir(rond_point, registre)["voiture_2"].distance == pytest.approx(13.0)


# ---------- Sur l'anneau ----------

def test_vehicule_sur_l_anneau_voit_celui_de_devant(rond_point: RondPoint, registre: Registre, placer) -> None:
    segment = f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}"
    milieu = milieu_de_voie(rond_point, Voiture("voiture_0", NATIONS_SUD, NATIONS_NORD), segment)
    placer(Voiture("voiture_1", NATIONS_SUD, NATIONS_NORD), milieu + 5.0)
    placer(Voiture("voiture_2", NATIONS_SUD, NATIONS_NORD), milieu - 5.0)
    assert voir(rond_point, registre)["voiture_2"].distance == pytest.approx(10.0)


def test_vehicule_sur_l_autre_voie_ne_gene_pas(rond_point: RondPoint, registre: Registre, placer) -> None:
    # Sur ce segment, la voiture 1 sort à la sortie suivante (voie extérieure) ; la voiture 2
    # va plus loin (voie intérieure).
    segment = f"{NATIONS_NORD}-{ALBERT_CAMUS}"
    exterieure = Voiture("voiture_1", NATIONS_NORD, ALBERT_CAMUS)
    interieure = Voiture("voiture_2", JEAN_DE_LA_BRUYERE, NATIONS_SUD)
    placer(exterieure, milieu_de_voie(rond_point, exterieure, segment))
    placer(interieure, milieu_de_voie(rond_point, interieure, segment) - 10.0)
    assert voir(rond_point, registre)["voiture_2"].distance is None


def test_vehicule_degage_passe_sur_la_voie_exterieure(rond_point: RondPoint, registre: Registre, placer) -> None:
    segment = f"{NATIONS_SUD}-{JEAN_DE_LA_BRUYERE}"
    milieu = milieu_de_voie(rond_point, Voiture("voiture_0", NATIONS_SUD, NATIONS_NORD), segment)
    placer(Voiture("voiture_1", NATIONS_SUD, NATIONS_NORD), milieu + 5.0, CodeNotification.DEGAGEZ)
    placer(Voiture("voiture_2", NATIONS_SUD, NATIONS_NORD), milieu - 5.0)
    assert voir(rond_point, registre)["voiture_2"].distance is None


def test_vehicule_au_dela_de_sa_sortie_ignore(rond_point: RondPoint, registre: Registre, placer) -> None:
    # La voiture 1 sort rue Albert Camus ; la voiture 2 roule déjà plus loin, sur la même voie extérieure.
    premiere = Voiture("voiture_1", NATIONS_NORD, ALBERT_CAMUS)
    seconde = Voiture("voiture_2", JEAN_DE_LA_BRUYERE, NATIONS_SUD)
    placer(premiere, LONGUEUR_BRANCHE + 5.0)
    placer(seconde, milieu_de_voie(rond_point, seconde, f"{ALBERT_CAMUS}-{NATIONS_SUD}"))
    assert voir(rond_point, registre)["voiture_1"].distance is None


def test_vehicule_sur_sa_branche_de_sortie_vu_depuis_l_anneau(
    rond_point: RondPoint, registre: Registre, placer
) -> None:
    devant = Voiture("voiture_1", NATIONS_SUD, NATIONS_NORD)
    derriere = Voiture("voiture_2", JEAN_DE_LA_BRUYERE, NATIONS_NORD)
    placer(devant, debut_de_sortie(rond_point, devant) + 6.0)
    avancement = milieu_de_voie(rond_point, derriere, f"{JEAN_DE_LA_BRUYERE}-{NATIONS_NORD}")
    placer(derriere, avancement)
    chemin_restant = debut_de_sortie(rond_point, derriere) + 6.0 - avancement
    # Le serveur mesure le reste de l'anneau à la distance au centre du suiveur : il compte un
    # peu court, ce qui garde le suiveur un peu plus loin que la distance de sécurité.
    distance = voir(rond_point, registre)["voiture_2"].distance
    assert PART_MIN_DU_CHEMIN * chemin_restant <= distance <= chemin_restant


def test_obstacle_hors_de_portee_ignore(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", NATIONS_NORD, JEAN_DE_LA_BRUYERE), LONGUEUR_BRANCHE + 80.0)
    placer(Voiture("voiture_2", NATIONS_NORD, JEAN_DE_LA_BRUYERE), LONGUEUR_BRANCHE + 1.0)
    assert voir(rond_point, registre)["voiture_2"].distance is None


# ---------- Cédez-le-passage ----------

@pytest.mark.parametrize(
    ("ecart_au_point_d_entree", "doit_ceder"),
    [(-5.0, True), (-25.0, False), (5.0, True), (20.0, False)],
    ids=["5-m-en-amont", "25-m-en-amont", "5-m-en-aval", "20-m-en-aval"],
)
@pytest.mark.parametrize("consigne", [None, CodeNotification.DEGAGEZ], ids=["voie-interieure", "voie-exterieure"])
def test_entree_retenue_si_l_anneau_est_occupe_pres_du_point_d_entree(
    rond_point: RondPoint,
    registre: Registre,
    placer,
    ecart_au_point_d_entree: float,
    doit_ceder: bool,
    consigne: CodeNotification | None,
) -> None:
    # La voiture 1 vient du boulevard, côté sud, et passe devant l'entrée du boulevard, côté nord.
    nord = rond_point.branche(NATIONS_NORD)
    point_d_entree = nord.angle + rond_point.ecart_raccord(nord)
    angle = point_d_entree + math.degrees(ecart_au_point_d_entree / rond_point.rayon)
    passante = Voiture("voiture_1", NATIONS_SUD, ALBERT_CAMUS)
    placer(passante, avancement_a_l_angle(passante.calculer_trajectoire(rond_point), angle), consigne)
    placer(Voiture("voiture_2", NATIONS_NORD, NATIONS_SUD), 40.0)
    assert voir(rond_point, registre)["voiture_2"].ceder is doit_ceder


# ---------- Passage piéton ----------

def avancement_du_pieton(rond_point: RondPoint, chaussee: str) -> float:
    """Avancement d'un piéton du boulevard des Nations (nord) au milieu d'une partie du passage."""
    nord = rond_point.branche(NATIONS_NORD)
    milieux = {
        "entree": LONGUEUR_TROTTOIR + nord.largeur_chaussee / 2,
        "refuge": LONGUEUR_TROTTOIR + nord.largeur_chaussee + nord.terre_plein / 2,
        "sortie": LONGUEUR_TROTTOIR + 1.5 * nord.largeur_chaussee + nord.terre_plein,
    }
    return milieux[chaussee]


def vues_avec_un_pieton(rond_point: RondPoint, registre: Registre, placer, chaussee: str) -> dict[str, Vue]:
    """Vues d'une voiture en approche et d'une voiture en sortie, avec un piéton sur le passage du nord."""
    placer(Pieton("pieton_1", NATIONS_NORD, NATIONS_NORD), avancement_du_pieton(rond_point, chaussee))
    placer(Voiture("voiture_entrante", NATIONS_NORD, NATIONS_SUD), 10.0)
    sortante = Voiture("voiture_sortante", NATIONS_SUD, NATIONS_NORD)
    placer(sortante, debut_de_sortie(rond_point, sortante) + 2.0)
    return voir(rond_point, registre)


def test_pieton_sur_la_chaussee_d_entree_ne_bloque_que_l_entree(
    rond_point: RondPoint, registre: Registre, placer
) -> None:
    vues = vues_avec_un_pieton(rond_point, registre, placer, "entree")
    distance_au_passage = LONGUEUR_BRANCHE - 10.0 - rond_point.branche(NATIONS_NORD).passage_pieton
    assert vues["voiture_entrante"].distance == pytest.approx(distance_au_passage)
    assert vues["voiture_sortante"].distance is None


def test_pieton_sur_la_chaussee_de_sortie_ne_bloque_que_la_sortie(
    rond_point: RondPoint, registre: Registre, placer
) -> None:
    vues = vues_avec_un_pieton(rond_point, registre, placer, "sortie")
    assert vues["voiture_entrante"].distance is None
    distance_au_passage = rond_point.branche(NATIONS_NORD).passage_pieton - 2.0
    assert vues["voiture_sortante"].distance == pytest.approx(distance_au_passage)


def test_pieton_sur_le_refuge_ne_bloque_personne(rond_point: RondPoint, registre: Registre, placer) -> None:
    vues = vues_avec_un_pieton(rond_point, registre, placer, "refuge")
    assert vues["voiture_entrante"].distance is None
    assert vues["voiture_sortante"].distance is None


@pytest.mark.parametrize(
    ("chaussee", "fermes"),
    [("entree", {(NATIONS_NORD, Chaussee.ENTREE)}), ("refuge", set()), ("sortie", {(NATIONS_NORD, Chaussee.SORTIE)})],
)
def test_passages_fermes_selon_la_chaussee_traversee(
    rond_point: RondPoint, registre: Registre, placer, chaussee: str, fermes: set
) -> None:
    placer(Pieton("pieton_1", NATIONS_NORD, NATIONS_NORD), avancement_du_pieton(rond_point, chaussee))
    assert Circulation(rond_point).passages_fermes(registre) == fermes


def test_pieton_qui_attend_ne_bloque_pas(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Pieton("pieton_1", NATIONS_NORD, NATIONS_NORD), 1.0)
    placer(Voiture("voiture_1", NATIONS_NORD, NATIONS_SUD), 10.0)
    assert voir(rond_point, registre)["voiture_1"].distance is None


def test_vehicule_deja_passe_ne_voit_plus_le_pieton(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Pieton("pieton_1", NATIONS_NORD, NATIONS_NORD), LONGUEUR_TROTTOIR + 2.0)
    placer(Voiture("voiture_1", NATIONS_NORD, NATIONS_SUD), LONGUEUR_BRANCHE - 2.0)
    assert voir(rond_point, registre)["voiture_1"].distance is None


def test_usager_sans_position_n_a_pas_de_vue(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Pieton("pieton_1", NATIONS_NORD, NATIONS_NORD), 1.0)
    registre.ajouter(Voiture("voiture_1", NATIONS_NORD, NATIONS_SUD))
    assert voir(rond_point, registre) == {"pieton_1": Vue(None, False)}


# ---------- Piétons à la file ----------

def test_pieton_voit_celui_qui_le_precede(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Pieton("pieton_1", NATIONS_NORD, NATIONS_NORD), 6.0)
    placer(Pieton("pieton_2", NATIONS_NORD, NATIONS_NORD), 4.0)
    vues = voir(rond_point, registre)
    assert vues["pieton_2"].distance == pytest.approx(2.0)
    assert vues["pieton_1"] == Vue(None, False)


def test_pietons_partis_ensemble_le_premier_inscrit_passe_devant(
    rond_point: RondPoint, registre: Registre, placer
) -> None:
    placer(Pieton("pieton_1", NATIONS_NORD, NATIONS_NORD), 0.0)
    placer(Pieton("pieton_2", NATIONS_NORD, NATIONS_NORD), 0.0)
    vues = voir(rond_point, registre)
    assert vues["pieton_2"].distance == pytest.approx(0.0)
    assert vues["pieton_1"].distance is None


def test_pieton_d_une_autre_branche_ignore(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Pieton("pieton_1", NATIONS_NORD, NATIONS_NORD), 6.0)
    placer(Pieton("pieton_2", NATIONS_SUD, NATIONS_SUD), 4.0)
    assert voir(rond_point, registre)["pieton_2"].distance is None


# ---------- Tour d'entrée ----------

def en_attente_pres_de_la_ligne(rond_point: RondPoint, placer, identifiant: str, entree: str) -> Usager:
    """Place une voiture à 5 m de sa ligne d'entrée."""
    return placer(Voiture(identifiant, entree, ALBERT_CAMUS), rond_point.longueur_branche - 5.0)


def test_une_seule_entree_accordee_a_la_fois(rond_point: RondPoint, registre: Registre, placer) -> None:
    en_attente_pres_de_la_ligne(rond_point, placer, "voiture_1", JEAN_DE_LA_BRUYERE)
    en_attente_pres_de_la_ligne(rond_point, placer, "voiture_2", NATIONS_SUD)
    vues = voir(rond_point, registre)
    assert sorted(vue.ceder for vue in vues.values()) == [False, True]


def test_le_tour_reste_a_celui_qui_l_a_recu(rond_point: RondPoint, registre: Registre, placer) -> None:
    en_attente_pres_de_la_ligne(rond_point, placer, "voiture_1", JEAN_DE_LA_BRUYERE)
    en_attente_pres_de_la_ligne(rond_point, placer, "voiture_2", NATIONS_SUD)
    circulation = Circulation(rond_point)
    premier = circulation.voir(registre)
    titulaire = circulation.tour_d_entree
    assert premier[titulaire].ceder is False
    assert circulation.voir(registre)[titulaire].ceder is False


def test_vehicule_qui_rejoint_l_anneau_bloque_les_autres_entrees(
    rond_point: RondPoint, registre: Registre, placer
) -> None:
    placer(Voiture("voiture_1", JEAN_DE_LA_BRUYERE, ALBERT_CAMUS), rond_point.longueur_branche + 3.0)
    en_attente_pres_de_la_ligne(rond_point, placer, "voiture_2", NATIONS_SUD)
    assert voir(rond_point, registre)["voiture_2"].ceder is True


def test_pas_de_tour_pour_un_vehicule_qui_doit_attendre(rond_point: RondPoint, registre: Registre, placer) -> None:
    attente = Voiture("voiture_1", JEAN_DE_LA_BRUYERE, ALBERT_CAMUS)
    placer(attente, rond_point.longueur_branche - 5.0, CodeNotification.ATTENDEZ)
    en_attente_pres_de_la_ligne(rond_point, placer, "voiture_2", NATIONS_SUD)
    vues = voir(rond_point, registre)
    assert (vues["voiture_1"].ceder, vues["voiture_2"].ceder) == (True, False)


def test_vp_prioritaire_entre_sans_prendre_le_tour(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(VehiculePrioritaire("vp_1", NATIONS_SUD, NATIONS_NORD), rond_point.longueur_branche - 5.0)
    en_attente_pres_de_la_ligne(rond_point, placer, "voiture_2", JEAN_DE_LA_BRUYERE)
    vues = Circulation(rond_point).voir(registre, prioritaires=frozenset({"vp_1"}))
    assert (vues["vp_1"].ceder, vues["voiture_2"].ceder) == (False, False)
