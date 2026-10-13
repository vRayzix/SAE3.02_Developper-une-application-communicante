"""Tests des événements du serveur déduits de deux STATE successifs."""

from datetime import datetime

import pytest

from cherrypie.ihm.evenements import EvenementsServeur

LIBELLES = {"nations_sud": "Bd des Nations (sud)", "nations_nord": "Bd des Nations (nord)", "albert_camus": "Rue Albert Camus"}
MAINTENANT = datetime(2026, 11, 17, 15, 31, 14)
VP = {"id": "vp_1", "entree": "nations_sud", "sortie": "nations_nord", "eta": 6.0}


def etat(**changements: object) -> dict:
    """Données d'un STATE calme : régulation active, aucun VP, rien de fermé."""
    return {"regulation": True, "vps": [], "entrees_bloquees": [], "passages_fermes": []} | changements


@pytest.fixture
def evenements() -> EvenementsServeur:
    suivi = EvenementsServeur(LIBELLES)
    suivi.comparer(etat(), MAINTENANT)
    return suivi


# ---------- Référence ----------

def test_premier_state_sans_evenement() -> None:
    assert EvenementsServeur(LIBELLES).comparer(etat(vps=[VP], regulation=False), MAINTENANT) == []


def test_state_identique_sans_evenement(evenements: EvenementsServeur) -> None:
    assert evenements.comparer(etat(), MAINTENANT) == []


def test_apres_oubli_le_state_suivant_sert_de_reference(evenements: EvenementsServeur) -> None:
    evenements.oublier()
    assert evenements.comparer(etat(regulation=False), MAINTENANT) == []


# ---------- Événements ----------

@pytest.mark.parametrize(
    ("suivant", "attendus"),
    [
        (etat(regulation=False), [("Régulation coupée", "")]),
        (
            etat(vps=[VP]),
            [("VP annoncé", "vp_1, Bd des Nations (sud) vers Bd des Nations (nord), à l'anneau vers 15:31:20")],
        ),
        (etat(entrees_bloquees=["albert_camus"]), [("Entrée temporisée", "Rue Albert Camus")]),
        (
            etat(passages_fermes=[{"branche": "nations_nord", "chaussee": "sortie"}]),
            [("Passage piéton fermé", "Bd des Nations (nord), chaussée de sortie")],
        ),
    ],
    ids=["regulation", "vp-annonce", "entree-temporisee", "passage-ferme"],
)
def test_changement_decrit(evenements: EvenementsServeur, suivant: dict, attendus: list[tuple[str, str]]) -> None:
    assert evenements.comparer(suivant, MAINTENANT) == attendus


def test_retour_a_l_etat_calme_decrit(evenements: EvenementsServeur) -> None:
    agite = etat(
        regulation=False,
        vps=[VP],
        entrees_bloquees=["albert_camus"],
        passages_fermes=[{"branche": "nations_nord", "chaussee": "entree"}],
    )
    evenements.comparer(agite, MAINTENANT)
    assert evenements.comparer(etat(), MAINTENANT) == [
        ("Régulation activée", ""),
        ("Fin de traversée", "vp_1"),
        ("Entrée libérée", "Rue Albert Camus"),
        ("Passage piéton rouvert", "Bd des Nations (nord), chaussée d'entrée"),
    ]
