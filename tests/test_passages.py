"""Tests du suivi d'un VP pendant sa traversée."""

import dataclasses

import pytest

from cherrypie.modele.trajectoire import Etape
from cherrypie.serveur.passages import PassageEnCours


@pytest.fixture
def passage() -> PassageEnCours:
    return PassageEnCours("vp_1", "S", "N", ["S-E", "E-N"], annonce=10.0, regulation=True)


# ---------- Annonce ----------

def test_vp_annonce_reserve_sa_trajectoire(passage: PassageEnCours) -> None:
    assert passage.segments_reserves == ("S-E", "E-N")
    assert not passage.sur_l_anneau


def test_approche_ne_marque_pas_l_entree_sur_l_anneau(passage: PassageEnCours) -> None:
    passage.noter_etape(Etape.APPROCHE, 12.0)
    assert not passage.sur_l_anneau


# ---------- Chronomètre ----------

def test_duree_de_l_annonce_au_vp_fin(passage: PassageEnCours) -> None:
    mesure = passage.terminer(18.5)
    assert mesure.duree == pytest.approx(8.5)
    assert (mesure.fin - mesure.debut).total_seconds() == pytest.approx(8.5)
    assert (mesure.identifiant, mesure.entree, mesure.sortie) == ("vp_1", "S", "N")


def test_duree_sur_l_anneau_depuis_le_premier_pos_sur_l_anneau(passage: PassageEnCours) -> None:
    passage.noter_etape(Etape.ANNEAU, 14.0)
    passage.noter_etape(Etape.ANNEAU, 14.2)
    assert passage.terminer(18.5).duree_anneau == pytest.approx(4.5)


def test_vp_jamais_vu_sur_l_anneau_sans_duree_sur_l_anneau(passage: PassageEnCours) -> None:
    assert passage.terminer(18.5).duree_anneau is None


@pytest.mark.parametrize("regulation", [True, False])
def test_mode_de_regulation_note_a_l_annonce(regulation: bool) -> None:
    passage = PassageEnCours("vp_1", "S", "N", ["S-E"], annonce=0.0, regulation=regulation)
    assert passage.terminer(5.0).regulation is regulation


def test_mesure_non_modifiable(passage: PassageEnCours) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        passage.terminer(12.0).duree = 1.0


# ---------- Densité pendant la traversée ----------

def test_densite_moyenne_sur_toute_la_traversee(passage: PassageEnCours) -> None:
    passage.noter_densite(0.2)
    passage.noter_etape(Etape.ANNEAU, 12.0)
    passage.noter_densite(0.4)
    assert passage.terminer(13.0).densite_moyenne == pytest.approx(0.3)


def test_densite_moyenne_nulle_sans_releve(passage: PassageEnCours) -> None:
    assert passage.terminer(10.1).densite_moyenne == 0.0
