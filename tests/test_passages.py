"""Tests du suivi d'un VP pendant sa traversée."""

import dataclasses

import pytest

from cherrypie.modele.trajectoire import Etape
from cherrypie.serveur.passages import PassageEnCours


@pytest.fixture
def passage() -> PassageEnCours:
    return PassageEnCours("vp_1", "S", "N", ["S-E", "E-N"])


# ---------- Annonce ----------

def test_vp_annonce_reserve_sa_trajectoire(passage: PassageEnCours) -> None:
    assert passage.segments_reserves == ("S-E", "E-N")
    assert not passage.sur_l_anneau


def test_approche_ne_demarre_pas_le_chronometre(passage: PassageEnCours) -> None:
    passage.noter_etape(Etape.APPROCHE, 10.0, regulation=True)
    assert not passage.sur_l_anneau


# ---------- Chronomètre ----------

def test_chronometre_demarre_au_premier_pos_sur_l_anneau(passage: PassageEnCours) -> None:
    passage.noter_etape(Etape.ANNEAU, 10.0, regulation=True)
    passage.noter_etape(Etape.ANNEAU, 10.2, regulation=True)
    assert passage.entree_anneau == pytest.approx(10.0)


def test_duree_de_l_entree_sur_l_anneau_au_vp_fin(passage: PassageEnCours) -> None:
    passage.noter_etape(Etape.ANNEAU, 10.0, regulation=True)
    mesure = passage.terminer(15.5)
    assert mesure.duree == pytest.approx(5.5)
    assert (mesure.fin - mesure.debut).total_seconds() == pytest.approx(5.5)
    assert (mesure.identifiant, mesure.entree, mesure.sortie) == ("vp_1", "S", "N")


def test_mode_de_regulation_note_a_l_entree_sur_l_anneau(passage: PassageEnCours) -> None:
    passage.noter_etape(Etape.ANNEAU, 10.0, regulation=False)
    passage.noter_etape(Etape.ANNEAU, 10.2, regulation=True)
    assert passage.terminer(12.0).regulation is False


def test_vp_jamais_vu_sur_l_anneau_sans_mesure(passage: PassageEnCours) -> None:
    passage.noter_etape(Etape.APPROCHE, 10.0, regulation=True)
    assert passage.terminer(15.0) is None


def test_mesure_non_modifiable(passage: PassageEnCours) -> None:
    passage.noter_etape(Etape.ANNEAU, 10.0, regulation=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        passage.terminer(12.0).duree = 1.0


# ---------- Densité pendant la traversée ----------

def test_densite_relevee_seulement_sur_l_anneau(passage: PassageEnCours) -> None:
    passage.noter_densite(0.9)
    passage.noter_etape(Etape.ANNEAU, 10.0, regulation=True)
    passage.noter_densite(0.2)
    passage.noter_densite(0.4)
    assert passage.terminer(12.0).densite_moyenne == pytest.approx(0.3)


def test_densite_moyenne_nulle_sans_releve(passage: PassageEnCours) -> None:
    passage.noter_etape(Etape.ANNEAU, 10.0, regulation=True)
    assert passage.terminer(10.1).densite_moyenne == 0.0
