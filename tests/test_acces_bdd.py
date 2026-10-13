"""Tests de l'accès à la base : requêtes paramétrées, commits, lecture et erreurs traduites.

mysql.connector.connect est remplacé par une FausseConnexion qui note ce qu'on lui
demande : aucun de ces tests n'a besoin de MariaDB, sauf ceux marqués « bdd ».
"""

from datetime import datetime
from pathlib import Path

import mysql.connector
import pytest
from doublure_bdd import FausseConnexion
from mysql.connector import errorcode

from cherrypie.bdd.acces_bdd import REQUETE_DENSITE, REQUETE_PASSAGE, AccesBdd
from cherrypie.bdd.enregistrements import EvenementConnexion, ReleveDensite, TypeConnexion
from cherrypie.commun.config import Configuration
from cherrypie.commun.erreurs import (
    AccesBddRefuseError,
    BaseAbsenteError,
    BddError,
    BddInjoignableError,
    ConfigurationInvalideError,
)
from cherrypie.serveur.passages import PassageVp

RACINE = Path(__file__).resolve().parent.parent
SCHEMA = RACINE / "src" / "cherrypie" / "bdd" / "schema.sql"
PARAMETRES = {
    "hote": "10.0.0.2", "port": 3306, "utilisateur": "cherrypie", "mot_de_passe": "secret", "base": "cherrypie"
}
DELAI_CONNEXION = 3.0
DEBUT = datetime(2026, 11, 17, 15, 31, 14)
FIN = datetime(2026, 11, 17, 15, 31, 21)
PASSAGE = PassageVp("vp_1", "nations_sud", "nations_nord", DEBUT, FIN, 7.3, 2.1, True, 0.4)


@pytest.fixture
def connexions(monkeypatch: pytest.MonkeyPatch) -> list[FausseConnexion]:
    """Remplace mysql.connector.connect ; la liste reçoit chaque connexion ouverte."""
    ouvertes: list[FausseConnexion] = []

    def connecter(**parametres: object) -> FausseConnexion:
        connexion = FausseConnexion(**parametres)
        ouvertes.append(connexion)
        return connexion

    monkeypatch.setattr(mysql.connector, "connect", connecter)
    return ouvertes


@pytest.fixture
def acces(connexions: list[FausseConnexion]) -> AccesBdd:
    acces = AccesBdd(PARAMETRES, DELAI_CONNEXION)
    acces.connecter()
    return acces


def refuser(monkeypatch: pytest.MonkeyPatch, errno: int) -> None:
    """Fait échouer toute connexion avec le code d'erreur donné."""

    def connecter(**_: object) -> None:
        raise mysql.connector.Error(msg="refus", errno=errno)

    monkeypatch.setattr(mysql.connector, "connect", connecter)


# ---------- Connexion ----------

def test_connexion_avec_les_parametres_de_config(acces: AccesBdd, connexions: list[FausseConnexion]) -> None:
    assert acces.connectee
    assert connexions[0].parametres == {
        "host": "10.0.0.2",
        "port": 3306,
        "user": "cherrypie",
        "password": "secret",
        "database": "cherrypie",
        "connection_timeout": DELAI_CONNEXION,
    }


def test_connecter_deux_fois_garde_la_meme_connexion(acces: AccesBdd, connexions: list[FausseConnexion]) -> None:
    acces.connecter()
    assert len(connexions) == 1


def test_fermer_ferme_la_connexion(acces: AccesBdd, connexions: list[FausseConnexion]) -> None:
    acces.fermer()
    acces.fermer()
    assert connexions[0].fermee
    assert not acces.connectee


@pytest.mark.parametrize(
    ("errno", "erreur", "message"),
    [
        (errorcode.CR_CONN_HOST_ERROR, BddInjoignableError, "injoignable"),
        (errorcode.CR_UNKNOWN_HOST, BddInjoignableError, "injoignable"),
        (errorcode.ER_ACCESS_DENIED_ERROR, AccesBddRefuseError, "accès refusé à cherrypie"),
        (errorcode.ER_BAD_DB_ERROR, BaseAbsenteError, "la base cherrypie n'existe pas"),
        (errorcode.ER_PARSE_ERROR, BddError, "erreur de la base"),
    ],
    ids=["serveur-eteint", "hote-inconnu", "acces-refuse", "base-absente", "autre"],
)
def test_erreur_de_connexion_traduite(
    monkeypatch: pytest.MonkeyPatch, errno: int, erreur: type[BddError], message: str
) -> None:
    refuser(monkeypatch, errno)
    acces = AccesBdd(PARAMETRES, DELAI_CONNEXION)
    with pytest.raises(erreur, match=message):
        acces.connecter()
    assert not acces.connectee


def test_ecriture_sans_connexion_refusee() -> None:
    with pytest.raises(BddInjoignableError, match="aucune connexion"):
        AccesBdd(PARAMETRES, DELAI_CONNEXION).enregistrer_passages([PASSAGE])


# ---------- Écriture ----------

def test_passages_inseres_en_lot_puis_valides(acces: AccesBdd, connexions: list[FausseConnexion]) -> None:
    acces.enregistrer_passages([PASSAGE, PASSAGE])
    connexion = connexions[0]
    ((requete, lignes),) = connexion.requetes
    assert requete == REQUETE_PASSAGE and "%s" in requete
    assert lignes[0] == ("vp_1", "nations_sud", "nations_nord", DEBUT, FIN, 7.3, 2.1, True, 0.4)
    assert len(lignes) == 2
    assert connexion.commits == 1
    assert connexion.curseurs_fermes == 1


def test_releves_et_connexions_inseres(acces: AccesBdd, connexions: list[FausseConnexion]) -> None:
    acces.enregistrer_densites([ReleveDensite(DEBUT, "nations_sud", 0.25)])
    evenement = EvenementConnexion(DEBUT, "voiture_1", "voiture", TypeConnexion.DECONNEXION, "BYE")
    acces.enregistrer_connexions([evenement])
    (densite, connexion) = connexions[0].requetes
    assert densite == (REQUETE_DENSITE, [(DEBUT, "nations_sud", 0.25)])
    assert connexion[1] == [(DEBUT, "voiture_1", "voiture", "deconnexion", "BYE")]
    assert connexions[0].commits == 2


def test_lot_vide_n_ecrit_rien(acces: AccesBdd, connexions: list[FausseConnexion]) -> None:
    acces.enregistrer_densites([])
    assert connexions[0].requetes == [] and connexions[0].commits == 0


def test_ecriture_coupee_pas_de_commit(acces: AccesBdd, connexions: list[FausseConnexion]) -> None:
    connexions[0].panne = True
    with pytest.raises(BddInjoignableError, match="injoignable"):
        acces.enregistrer_passages([PASSAGE])
    assert connexions[0].commits == 0
    assert connexions[0].curseurs_fermes == 1


def test_script_execute_instruction_par_instruction(acces: AccesBdd, connexions: list[FausseConnexion]) -> None:
    acces.executer_script(SCHEMA.read_text(encoding="utf-8"))
    requetes = [requete for requete, _ in connexions[0].requetes]
    tables = ["passage_vp", "releve_densite", "evenement_connexion"]
    assert [f"CREATE TABLE IF NOT EXISTS {table}" in requete for requete, table in zip(requetes, tables)] == [True] * 3
    assert len(requetes) == 3
    assert connexions[0].commits == 1


# ---------- Lecture ----------

def test_statistiques_du_plus_ancien_au_plus_recent(acces: AccesBdd, connexions: list[FausseConnexion]) -> None:
    recent, ancien = datetime(2026, 11, 17, 15, 40), datetime(2026, 11, 17, 15, 30)
    connexions[0].lignes = [
        [
            ("vp_2", "nations_sud", "nations_nord", recent, 13.6, None, 0, 0.5),
            ("vp_1", "nations_sud", "nations_nord", ancien, 7.3, 2.1, 1, 0.4),
        ],
        [(recent, "nations_sud", 0.5)],
    ]
    statistiques = acces.lire_statistiques(200, 2000)
    assert [passage["vp"] for passage in statistiques["passages"]] == ["vp_1", "vp_2"]
    assert statistiques["passages"][0]["regulation"] is True
    assert statistiques["passages"][1]["debut"] == "2026-11-17T15:40:00"
    assert statistiques["densites"] == [{"instant": "2026-11-17T15:40:00", "branche": "nations_sud", "densite": 0.5}]
    assert [parametres for _, parametres in connexions[0].requetes] == [(200,), (2000,)]


# ---------- Vraie base ----------

@pytest.fixture
def vraie_bdd() -> AccesBdd:
    """Accès à la base de config.ini ; le test est ignoré sans config.ini ou sans base joignable."""
    chemin = RACINE / "config.ini"
    if not chemin.exists():
        pytest.skip("pas de config.ini à la racine du dépôt")
    try:
        config = Configuration.depuis_fichier(chemin)
    except ConfigurationInvalideError as erreur:
        pytest.skip(f"config.ini à compléter : {erreur}")
    acces = AccesBdd(config.parametres_bdd, config.delai_connexion_bdd)
    try:
        acces.connecter()
    except BddError as erreur:
        pytest.skip(f"base MariaDB absente : {erreur}")
    yield acces
    acces.fermer()


@pytest.mark.bdd
def test_vraie_base_schema_et_lecture(vraie_bdd: AccesBdd) -> None:
    # Le schéma se relance sans rien perdre ; la lecture n'écrit rien.
    vraie_bdd.executer_script(SCHEMA.read_text(encoding="utf-8"))
    statistiques = vraie_bdd.lire_statistiques(1, 1)
    assert set(statistiques) == {"passages", "densites"}
