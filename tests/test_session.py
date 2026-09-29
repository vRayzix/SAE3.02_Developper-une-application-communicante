"""Tests de l'état d'une session TCP."""

import pytest

from cherrypie.serveur.session import Session


@pytest.fixture
def session() -> Session:
    return Session(7, maintenant=100.0)


# ---------- Ouverture ----------

def test_nouvelle_session_anonyme_et_non_abonnee(session: Session) -> None:
    assert session.numero == 7
    assert session.identifiant is None
    assert not session.superviseur
    assert session.derniere_activite == pytest.approx(100.0)


# ---------- Usager de la session ----------

def test_usager_rattache_a_la_session(session: Session) -> None:
    session.identifiant = "voiture_12"
    assert session.identifiant == "voiture_12"


def test_second_usager_sur_la_meme_session_refuse(session: Session) -> None:
    session.identifiant = "voiture_12"
    with pytest.raises(ValueError, match="déjà"):
        session.identifiant = "moto_3"


def test_identifiant_vide_refuse(session: Session) -> None:
    with pytest.raises(ValueError, match="invalide"):
        session.identifiant = ""


# ---------- Abonnement ----------

def test_session_abonnee_aux_state(session: Session) -> None:
    session.superviseur = True
    assert session.superviseur


def test_abonnement_non_booleen_refuse(session: Session) -> None:
    with pytest.raises(TypeError, match="True ou False"):
        session.superviseur = "oui"


# ---------- Activité et expiration ----------

def test_activite_notee(session: Session) -> None:
    session.derniere_activite = 103.5
    assert session.derniere_activite == pytest.approx(103.5)


def test_activite_dans_le_passe_refusee(session: Session) -> None:
    with pytest.raises(ValueError, match="antérieur"):
        session.derniere_activite = 99.0


def test_session_active_avant_le_delai(session: Session) -> None:
    assert not session.est_expiree(maintenant=106.0, delai=6.0)


def test_session_expiree_apres_le_delai(session: Session) -> None:
    assert session.est_expiree(maintenant=106.1, delai=6.0)
