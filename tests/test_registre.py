"""Tests du registre des usagers connectés."""

import pytest

from cherrypie.commun.erreurs import UsagerInconnuError
from cherrypie.modele.usager import Moto, Voiture
from cherrypie.serveur.registre import Registre


@pytest.fixture
def registre() -> Registre:
    return Registre()


# ---------- Ajout ----------

def test_registre_vide_au_depart(registre: Registre) -> None:
    assert registre.usagers == []
    assert not registre.contient("voiture_12")


def test_usager_ajoute_retrouve(registre: Registre) -> None:
    voiture = Voiture("voiture_12", "N", "E")
    registre.ajouter(voiture)
    assert registre.contient("voiture_12")
    assert registre.obtenir("voiture_12") is voiture


def test_usagers_dans_l_ordre_d_arrivee(registre: Registre) -> None:
    registre.ajouter(Voiture("voiture_12", "N", "E"))
    registre.ajouter(Moto("moto_3", "S", "O"))
    assert [usager.identifiant for usager in registre.usagers] == ["voiture_12", "moto_3"]


def test_identifiant_deja_inscrit_refuse(registre: Registre) -> None:
    registre.ajouter(Voiture("voiture_12", "N", "E"))
    with pytest.raises(ValueError, match="déjà inscrit"):
        registre.ajouter(Moto("voiture_12", "S", "O"))


def test_liste_des_usagers_modifiee_de_l_exterieur_sans_effet(registre: Registre) -> None:
    registre.ajouter(Voiture("voiture_12", "N", "E"))
    registre.usagers.clear()
    assert registre.contient("voiture_12")


# ---------- Retrait ----------

def test_usager_retire_n_est_plus_connecte(registre: Registre) -> None:
    voiture = Voiture("voiture_12", "N", "E")
    registre.ajouter(voiture)
    assert registre.retirer("voiture_12") is voiture
    assert not registre.contient("voiture_12")


# ---------- Usager inconnu ----------

def test_obtenir_usager_inconnu_refuse(registre: Registre) -> None:
    with pytest.raises(UsagerInconnuError, match="voiture_99"):
        registre.obtenir("voiture_99")


def test_retirer_usager_inconnu_refuse(registre: Registre) -> None:
    with pytest.raises(UsagerInconnuError):
        registre.retirer("voiture_99")
