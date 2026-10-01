"""Tests des exceptions métier."""

import pytest

from cherrypie.commun.erreurs import (
    BrancheInconnueError,
    CherryPieError,
    ConfigurationInvalideError,
    InscriptionRefuseeError,
    RejeuDetecteError,
    SignatureInvalideError,
    TrameInvalideError,
    UsagerInconnuError,
)

ERREURS_METIER = [
    ConfigurationInvalideError,
    TrameInvalideError,
    SignatureInvalideError,
    RejeuDetecteError,
    BrancheInconnueError,
    UsagerInconnuError,
]


# ---------- Hiérarchie ----------

@pytest.mark.parametrize("classe", ERREURS_METIER)
def test_erreur_metier_herite_de_cherrypie_error(classe: type) -> None:
    assert issubclass(classe, CherryPieError)


@pytest.mark.parametrize("classe", ERREURS_METIER)
def test_erreur_metier_attrapee_par_la_classe_mere(classe: type) -> None:
    with pytest.raises(CherryPieError, match="détail"):
        raise classe("détail")


# ---------- Inscription refusée ----------

def test_inscription_refusee_garde_sa_raison_et_le_droit_de_reessayer() -> None:
    refus = InscriptionRefuseeError("l'identifiant voiture_12 est déjà connecté", reessayer=True)
    assert isinstance(refus, CherryPieError)
    assert str(refus) == "l'identifiant voiture_12 est déjà connecté"
    assert refus.reessayer
