"""Tests de l'historique : écriture en base dans son thread, base injoignable, statistiques."""

import logging
from collections.abc import Iterator
from datetime import datetime

import pytest
from doublure_bdd import DoublureBdd
from outils import attendre

from cherrypie.bdd.enregistrements import EvenementConnexion, ReleveDensite, TypeConnexion
from cherrypie.bdd.historique import Historique
from cherrypie.serveur.passages import PassageVp

# Délai de nouvel essai court : les tests voient la base revenir sans attendre.
DELAI_REESSAI = 0.1
DELAI_ARRET = 2.0
INSTANT = datetime(2026, 11, 17, 15, 31, 14)
PASSAGE = PassageVp("vp_1", "nations_sud", "nations_nord", INSTANT, INSTANT, 7.3, 2.1, True, 0.4)
RELEVE = ReleveDensite(INSTANT, "nations_sud", 0.25)
CONNEXION = EvenementConnexion(INSTANT, "voiture_1", "voiture", TypeConnexion.CONNEXION, "inscrit")


@pytest.fixture
def base() -> DoublureBdd:
    return DoublureBdd()


@pytest.fixture
def historique(base: DoublureBdd) -> Iterator[Historique]:
    historique = Historique(base, DELAI_REESSAI)
    historique.start()
    yield historique
    historique.arreter(DELAI_ARRET)


# ---------- Écriture ----------

def test_enregistrements_ecrits_en_base(historique: Historique, base: DoublureBdd) -> None:
    historique.noter_passage(PASSAGE)
    historique.noter_densites([RELEVE, RELEVE])
    historique.noter_connexion(CONNEXION)
    attendre(lambda: historique.en_attente == 0 and len(base.releves) == 2)
    assert (base.passages, base.connexions) == ([PASSAGE], [CONNEXION])


def test_arret_ecrit_ce_qui_attend_et_ferme_la_connexion(base: DoublureBdd) -> None:
    historique = Historique(base, DELAI_REESSAI)
    historique.start()
    historique.noter_passage(PASSAGE)
    historique.arreter(DELAI_ARRET)
    assert not historique.is_alive()
    assert base.passages == [PASSAGE]
    assert not base.connectee


# ---------- Base injoignable ----------

def test_base_injoignable_enregistrements_gardes_puis_ecrits(
    historique: Historique, base: DoublureBdd, caplog: pytest.LogCaptureFixture
) -> None:
    base.joignable = False
    with caplog.at_level(logging.WARNING):
        historique.noter_passage(PASSAGE)
        historique.noter_connexion(CONNEXION)
        attendre(lambda: base.tentatives >= 3)
    assert historique.en_attente == 2 and base.passages == []
    # Journalisée une fois, la panne ne remplit pas le journal à chaque nouvel essai.
    assert caplog.text.count("historique non écrit") == 1
    base.joignable = True
    attendre(lambda: historique.en_attente == 0)
    assert (base.passages, base.connexions) == ([PASSAGE], [CONNEXION])


def test_panne_pendant_l_ecriture_sans_doublon(historique: Historique, base: DoublureBdd) -> None:
    historique.noter_passage(PASSAGE)
    attendre(lambda: base.passages == [PASSAGE])
    base.joignable = False
    historique.noter_densites([RELEVE])
    attendre(lambda: base.tentatives >= 2)
    base.joignable = True
    attendre(lambda: historique.en_attente == 0)
    assert (base.passages, base.releves) == ([PASSAGE], [RELEVE])


# ---------- Statistiques ----------

def test_statistiques_lues_apres_l_ecriture(historique: Historique) -> None:
    historique.noter_passage(PASSAGE)
    historique.demander_statistiques(7)
    reponses: list[tuple[int, dict]] = []
    attendre(lambda: bool(reponses.extend(historique.reponses_pretes()) or reponses))
    ((numero, statistiques),) = reponses
    assert numero == 7 and statistiques["disponible"] is True
    assert [passage["vp"] for passage in statistiques["passages"]] == ["vp_1"]


def test_statistiques_base_injoignable(historique: Historique, base: DoublureBdd) -> None:
    base.joignable = False
    historique.demander_statistiques(3)
    reponses: list[tuple[int, dict]] = []
    attendre(lambda: bool(reponses.extend(historique.reponses_pretes()) or reponses))
    ((numero, statistiques),) = reponses
    assert numero == 3
    assert statistiques == {"disponible": False, "raison": "base injoignable (doublure:3306)"}
