"""Tests de l'onglet « Statistiques » : affichage d'une réponse STATS_REPONSE, en plateforme offscreen."""

import pyqtgraph as pg
import pytest
from PyQt6.QtWidgets import QApplication

from cherrypie.ihm.panneau_stats import PanneauStats

LIBELLES = {"nations_sud": "Bd des Nations (sud)", "albert_camus": "Rue Albert Camus"}


def passage(duree: float, regulation: bool) -> dict:
    return {
        "vp": "vp_1", "entree": "nations_sud", "sortie": "nations_nord", "debut": "2026-11-17T15:00:00",
        "duree": duree, "duree_anneau": 2.0, "regulation": regulation, "densite_moyenne": 0.3,
    }


def releve(instant: str, branche: str, densite: float) -> dict:
    return {"instant": instant, "branche": branche, "densite": densite}


STATISTIQUES = {
    "disponible": True,
    "passages": [passage(7.0, True), passage(14.0, False), passage(8.0, True)],
    "densites": [
        releve("2026-11-17T15:00:00", "nations_sud", 0.25),
        releve("2026-11-17T15:00:05", "nations_sud", 0.5),
        releve("2026-11-17T15:00:00", "albert_camus", 0.125),
    ],
}


@pytest.fixture
def panneau(qapp: QApplication) -> PanneauStats:
    return PanneauStats(LIBELLES)


def courbes(graphique: pg.PlotWidget) -> dict[str, pg.PlotDataItem]:
    return {courbe.name(): courbe for courbe in graphique.getPlotItem().listDataItems()}


# ---------- Réponse disponible ----------

def test_resume_avec_moyennes_et_gain(panneau: PanneauStats) -> None:
    panneau.afficher(STATISTIQUES)
    assert panneau.resume.text() == (
        "Temps de traversée du VP, avec régulation : 7,5 s en moyenne sur 2 traversée(s) ; "
        "sans régulation : 14,0 s en moyenne sur 1 traversée(s) ; gain : 46 %"
    )
    assert "3 traversée(s) de VP et 3 relevé(s) de densité" in panneau.etat.text()


def test_une_serie_par_mode_de_regulation(panneau: PanneauStats) -> None:
    panneau.afficher(STATISTIQUES)
    series = courbes(panneau.traversees)
    assert list(series["avec régulation"].getData()[1]) == [7.0, 8.0]
    assert list(series["sans régulation"].getData()[0]) == [2]


def test_une_courbe_de_densite_par_branche_en_pourcentage(panneau: PanneauStats) -> None:
    panneau.afficher(STATISTIQUES)
    series = courbes(panneau.densites)
    assert set(series) == {"Bd des Nations (sud)", "Rue Albert Camus"}
    assert list(series["Bd des Nations (sud)"].getData()[1]) == [25.0, 50.0]


def test_nouvel_affichage_remplace_l_ancien(panneau: PanneauStats) -> None:
    panneau.afficher(STATISTIQUES)
    panneau.afficher(STATISTIQUES)
    assert len(courbes(panneau.densites)) == len(LIBELLES)


def test_un_seul_mode_mesure_sans_gain(panneau: PanneauStats) -> None:
    panneau.afficher({"disponible": True, "passages": [passage(7.0, True)], "densites": []})
    assert panneau.resume.text().endswith("sans régulation : aucune mesure")


# ---------- Réponse indisponible ----------

def test_base_injoignable_expliquee(panneau: PanneauStats) -> None:
    panneau.afficher({"disponible": False, "raison": "base injoignable (10.0.0.2:3306)"})
    assert panneau.etat.text().endswith("statistiques indisponibles, base injoignable (10.0.0.2:3306)")


def test_actualiser_emet_la_demande(panneau: PanneauStats) -> None:
    demandes: list[bool] = []
    panneau.actualisation_demandee.connect(lambda: demandes.append(True))
    panneau.bouton.click()
    assert demandes == [True]
