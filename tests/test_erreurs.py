"""Tests des exceptions métier."""

import pytest

from cherrypie.commun.erreurs import (
    BrancheInconnueError,
    CherryPieError,
    ConfigurationInvalideError,
    RejeuDetecteError,
    SignatureInvalideError,
    TrameInvalideError,
)

ERREURS_METIER = [
    ConfigurationInvalideError,
    TrameInvalideError,
    SignatureInvalideError,
    RejeuDetecteError,
    BrancheInconnueError,
]


# ---------- Hiérarchie ----------

@pytest.mark.parametrize("classe", ERREURS_METIER)
def test_erreur_metier_herite_de_cherrypie_error(classe: type) -> None:
    assert issubclass(classe, CherryPieError)


@pytest.mark.parametrize("classe", ERREURS_METIER)
def test_erreur_metier_attrapee_par_la_classe_mere(classe: type) -> None:
    with pytest.raises(CherryPieError, match="détail"):
        raise classe("détail")
