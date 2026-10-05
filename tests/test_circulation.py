"""Tests de ce que voit chaque conducteur : file, voies, cédez-le-passage et passage piéton."""

import math

import pytest

from cherrypie.client.deplacement import Deplacement
from cherrypie.commun.protocole import CodeNotification
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import DISTANCE_PASSAGE_PIETON, LONGUEUR_BRANCHE, LONGUEUR_TROTTOIR
from cherrypie.modele.usager import Pieton, Usager, Voiture
from cherrypie.serveur.circulation import Circulation, Vue
from cherrypie.serveur.registre import Registre

RAYON = 20.0
QUART = 2 * math.pi * RAYON / 4


@pytest.fixture
def rond_point() -> RondPoint:
    return RondPoint(["N", "E", "S", "O"], RAYON, 8)


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
        deplacement.avancer(avancement / usager.vitesse_autorisee())
        registre.ajouter(usager)
        return usager

    return placer_usager


def voir(rond_point: RondPoint, registre: Registre) -> dict[str, Vue]:
    return Circulation(rond_point).voir(registre)


# ---------- File sur une branche ----------

def test_voie_libre_sans_personne_devant(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "N", "S"), 10.0)
    assert voir(rond_point, registre) == {"voiture_1": Vue(None, False)}


def test_vehicule_voit_celui_qui_le_precede(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "N", "S"), 30.0)
    placer(Voiture("voiture_2", "N", "S"), 20.0)
    vues = voir(rond_point, registre)
    assert vues["voiture_2"].distance == pytest.approx(10.0)
    assert vues["voiture_1"].distance is None


def test_au_meme_point_le_premier_arrive_passe_devant(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "N", "S"), 0.0)
    placer(Voiture("voiture_2", "N", "S"), 0.0)
    vues = voir(rond_point, registre)
    assert vues["voiture_2"].distance == pytest.approx(0.0)
    assert vues["voiture_1"].distance is None


def test_vehicule_range_sur_le_cote_ne_gene_pas(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "N", "S"), 30.0, CodeNotification.CHANGEZ_VOIE)
    placer(Voiture("voiture_2", "N", "S"), 20.0)
    assert voir(rond_point, registre)["voiture_2"].distance is None


def test_vehicules_ranges_font_la_file_entre_eux(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "N", "S"), 30.0, CodeNotification.CHANGEZ_VOIE)
    placer(Voiture("voiture_2", "N", "S"), 20.0, CodeNotification.CHANGEZ_VOIE)
    assert voir(rond_point, registre)["voiture_2"].distance == pytest.approx(10.0)


def test_vehicule_en_sortie_voit_celui_qui_le_precede(rond_point: RondPoint, registre: Registre, placer) -> None:
    sortie = LONGUEUR_BRANCHE + 2 * QUART
    placer(Voiture("voiture_1", "S", "N"), sortie + 25.0)
    placer(Voiture("voiture_2", "S", "N"), sortie + 12.0)
    assert voir(rond_point, registre)["voiture_2"].distance == pytest.approx(13.0)


# ---------- Sur l'anneau ----------

def test_vehicule_sur_l_anneau_voit_celui_de_devant(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "S", "N"), LONGUEUR_BRANCHE + 20.0)
    placer(Voiture("voiture_2", "S", "N"), LONGUEUR_BRANCHE + 5.0)
    assert voir(rond_point, registre)["voiture_2"].distance == pytest.approx(15.0)


def test_vehicule_au_dela_de_sa_sortie_ignore(rond_point: RondPoint, registre: Registre, placer) -> None:
    # La voiture 1 sort à O ; la voiture 2 est déjà plus loin sur l'anneau, entre O et S.
    placer(Voiture("voiture_1", "N", "O"), LONGUEUR_BRANCHE + 5.0)
    placer(Voiture("voiture_2", "E", "S"), LONGUEUR_BRANCHE + 2 * QUART + 10.0)
    assert voir(rond_point, registre)["voiture_1"].distance is None


def test_vehicule_sur_sa_branche_de_sortie_vu_depuis_l_anneau(
    rond_point: RondPoint, registre: Registre, placer
) -> None:
    placer(Voiture("voiture_1", "S", "N"), LONGUEUR_BRANCHE + 2 * QUART + 6.0)
    placer(Voiture("voiture_2", "E", "N"), LONGUEUR_BRANCHE + QUART - 4.0)
    assert voir(rond_point, registre)["voiture_2"].distance == pytest.approx(10.0)


def test_obstacle_hors_de_portee_ignore(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "N", "E"), LONGUEUR_BRANCHE + 60.0)
    placer(Voiture("voiture_2", "N", "E"), LONGUEUR_BRANCHE)
    assert voir(rond_point, registre)["voiture_2"].distance is None


# ---------- Cédez-le-passage ----------

@pytest.mark.parametrize(
    ("avancement_sur_l_anneau", "doit_ceder"),
    [(QUART - 5.0, True), (QUART - 30.0, False), (QUART + 5.0, True), (QUART + 20.0, False)],
    ids=["5-m-en-amont", "30-m-en-amont", "5-m-en-aval", "20-m-en-aval"],
)
def test_entree_retenue_si_l_anneau_est_occupe_pres_du_point_d_entree(
    rond_point: RondPoint, registre: Registre, placer, avancement_sur_l_anneau: float, doit_ceder: bool
) -> None:
    # La voiture 1 vient de E et passe devant l'entrée N, un quart de tour plus loin.
    placer(Voiture("voiture_1", "E", "S"), LONGUEUR_BRANCHE + avancement_sur_l_anneau)
    placer(Voiture("voiture_2", "N", "S"), 40.0)
    assert voir(rond_point, registre)["voiture_2"].ceder is doit_ceder


def test_vehicule_range_sur_l_anneau_laisse_entrer(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Voiture("voiture_1", "E", "S"), LONGUEUR_BRANCHE + QUART - 5.0, CodeNotification.DEGAGEZ)
    placer(Voiture("voiture_2", "N", "S"), 40.0)
    assert voir(rond_point, registre)["voiture_2"].ceder is False


# ---------- Passage piéton ----------

def test_pieton_qui_traverse_bloque_la_branche_avant_le_passage(
    rond_point: RondPoint, registre: Registre, placer
) -> None:
    placer(Pieton("pieton_1", "N", "N"), LONGUEUR_TROTTOIR + 2.0)
    placer(Voiture("voiture_1", "N", "S"), 10.0)
    distance_au_passage = LONGUEUR_BRANCHE - 10.0 - DISTANCE_PASSAGE_PIETON
    assert voir(rond_point, registre)["voiture_1"].distance == pytest.approx(distance_au_passage)


def test_pieton_qui_attend_ne_bloque_pas(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Pieton("pieton_1", "N", "N"), 1.0)
    placer(Voiture("voiture_1", "N", "S"), 10.0)
    assert voir(rond_point, registre)["voiture_1"].distance is None


def test_vehicule_deja_passe_ne_voit_plus_le_pieton(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Pieton("pieton_1", "N", "N"), LONGUEUR_TROTTOIR + 2.0)
    placer(Voiture("voiture_1", "N", "S"), LONGUEUR_BRANCHE - 2.0)
    assert voir(rond_point, registre)["voiture_1"].distance is None


def test_pieton_et_usager_sans_position_n_ont_pas_de_vue(rond_point: RondPoint, registre: Registre, placer) -> None:
    placer(Pieton("pieton_1", "N", "N"), 1.0)
    registre.ajouter(Voiture("voiture_1", "N", "S"))
    assert voir(rond_point, registre) == {}
