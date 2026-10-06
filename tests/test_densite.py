"""Tests de la densité des branches."""

import pytest
from geometrie import rond_point_bel_air

from cherrypie.modele.trajectoire import Etape
from cherrypie.modele.usager import Pieton, Voiture
from cherrypie.serveur.densite import CalculateurDensite, NiveauDensite
from cherrypie.serveur.registre import Registre

CAPACITE = 4


@pytest.fixture
def calculateur() -> CalculateurDensite:
    return CalculateurDensite(rond_point_bel_air(capacite=CAPACITE))


def registre_avec(*usagers: Voiture | Pieton) -> Registre:
    registre = Registre()
    for usager in usagers:
        registre.ajouter(usager)
    return registre


def voiture(numero: int, entree: str = "nations_nord", etape: Etape = Etape.APPROCHE) -> Voiture:
    usager = Voiture(f"voiture_{numero}", entree, "nations_sud")
    usager.etape = etape
    return usager


# ---------- Calcul ----------

def test_rond_point_vide_densite_nulle_partout(calculateur: CalculateurDensite) -> None:
    assert calculateur.calculer(Registre()) == {"nations_nord": 0.0, "jean_de_la_bruyere": 0.0, "nations_sud": 0.0, "albert_camus": 0.0}


def test_usagers_en_approche_comptes_sur_leur_branche(calculateur: CalculateurDensite) -> None:
    densites = calculateur.calculer(registre_avec(voiture(1, "nations_nord"), voiture(2, "nations_nord"), voiture(3, "jean_de_la_bruyere")))
    assert densites["nations_nord"] == pytest.approx(2 / CAPACITE)
    assert densites["jean_de_la_bruyere"] == pytest.approx(1 / CAPACITE)
    assert densites["nations_sud"] == 0.0


@pytest.mark.parametrize("etape", [Etape.ANNEAU, Etape.SORTIE], ids=["anneau", "sortie"])
def test_usager_entre_sur_l_anneau_ne_compte_plus(calculateur: CalculateurDensite, etape: Etape) -> None:
    assert calculateur.calculer(registre_avec(voiture(1, "nations_nord", etape)))["nations_nord"] == 0.0


def test_pieton_qui_attend_compte_sur_sa_branche(calculateur: CalculateurDensite) -> None:
    assert calculateur.calculer(registre_avec(Pieton("pieton_1", "jean_de_la_bruyere", "jean_de_la_bruyere")))["jean_de_la_bruyere"] == pytest.approx(1 / CAPACITE)


def test_densite_bornee_a_un(calculateur: CalculateurDensite) -> None:
    registre = registre_avec(*(voiture(numero) for numero in range(2 * CAPACITE)))
    assert calculateur.calculer(registre)["nations_nord"] == pytest.approx(1.0)


# ---------- Niveaux ----------

@pytest.mark.parametrize(
    ("densite", "niveau"),
    [
        (0.0, NiveauDensite.FAIBLE),
        (0.39, NiveauDensite.FAIBLE),
        (0.4, NiveauDensite.MOYENNE),
        (0.69, NiveauDensite.MOYENNE),
        (0.7, NiveauDensite.FORTE),
        (1.0, NiveauDensite.FORTE),
    ],
)
def test_niveau_selon_les_seuils(densite: float, niveau: NiveauDensite) -> None:
    assert CalculateurDensite.niveau(densite) is niveau


@pytest.mark.parametrize("densite", [-0.1, 1.5, float("nan")], ids=["negative", "trop-grande", "nan"])
def test_densite_hors_bornes_refusee(densite: float) -> None:
    with pytest.raises(ValueError, match="entre 0 et 1"):
        CalculateurDensite.niveau(densite)
