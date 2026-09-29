"""Tests des usagers : sous-classes, consignes, état et sérialisation."""

import pytest

from cherrypie.commun.erreurs import BrancheInconnueError
from cherrypie.commun.protocole import CodeNotification
from cherrypie.modele.position import Position
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import Etape
from cherrypie.modele.usager import (
    CLASSES_PAR_CATEGORIE,
    DECALAGE_DEGAGEMENT,
    FACTEUR_RALENTISSEMENT,
    Moto,
    Pieton,
    Trottinette,
    Usager,
    VehiculePrioritaire,
    Voiture,
)


@pytest.fixture
def voiture() -> Voiture:
    return Voiture("voiture_12", "N", "E")


@pytest.fixture
def pieton() -> Pieton:
    return Pieton("pieton_4", "N", "N")


# ---------- Sous-classes ----------

@pytest.mark.parametrize(
    ("classe", "categorie", "vitesse_kmh"),
    [
        (Voiture, "voiture", 30),
        (Moto, "moto", 30),
        (Trottinette, "trottinette", 20),
        (Pieton, "pieton", 5),
        (VehiculePrioritaire, "vp", 40),
    ],
)
def test_sous_classe_categorie_et_vitesse_max(classe: type, categorie: str, vitesse_kmh: int) -> None:
    assert classe.CATEGORIE == categorie
    assert classe.VITESSE_MAX == pytest.approx(vitesse_kmh / 3.6)


def test_chaque_categorie_a_sa_classe() -> None:
    assert set(CLASSES_PAR_CATEGORIE) == {"voiture", "moto", "trottinette", "pieton", "vp"}


def test_usager_non_instanciable_directement() -> None:
    with pytest.raises(TypeError, match="classe mère"):
        Usager("inconnu_1", "N", "E")


@pytest.mark.parametrize(
    ("identifiant", "entree", "sortie"),
    [("", "N", "E"), ("moto_1", "", "E"), ("moto_1", "N", None)],
    ids=["identifiant-vide", "entree-vide", "sortie-absente"],
)
def test_identifiant_ou_branche_invalide_refuse(identifiant: str, entree: str, sortie: object) -> None:
    with pytest.raises(ValueError, match="texte non vide"):
        Moto(identifiant, entree, sortie)


def test_nouvel_usager_a_l_arret_et_sans_position(voiture: Voiture) -> None:
    assert voiture.position is None
    assert voiture.vitesse == 0.0
    assert voiture.segment is None
    assert voiture.consigne is None


# ---------- Consignes ----------

def test_degagez_ralentit_et_decale(voiture: Voiture) -> None:
    assert voiture.reagir(CodeNotification.DEGAGEZ)
    assert voiture.vitesse_autorisee() == pytest.approx(Voiture.VITESSE_MAX * FACTEUR_RALENTISSEMENT)
    assert voiture.decalage_lateral() == pytest.approx(DECALAGE_DEGAGEMENT)


def test_changez_voie_decale_sans_ralentir(voiture: Voiture) -> None:
    assert voiture.reagir(CodeNotification.CHANGEZ_VOIE)
    assert voiture.vitesse_autorisee() == pytest.approx(Voiture.VITESSE_MAX)
    assert voiture.decalage_lateral() == pytest.approx(DECALAGE_DEGAGEMENT)


def test_attendez_ne_ralentit_pas_avant_la_ligne(voiture: Voiture) -> None:
    assert voiture.reagir(CodeNotification.ATTENDEZ)
    assert voiture.consigne is CodeNotification.ATTENDEZ
    assert voiture.vitesse_autorisee() == pytest.approx(Voiture.VITESSE_MAX)
    assert voiture.decalage_lateral() == 0.0


def test_ok_passer_leve_la_consigne(voiture: Voiture) -> None:
    voiture.reagir(CodeNotification.DEGAGEZ)
    assert voiture.reagir(CodeNotification.OK_PASSER)
    assert voiture.consigne is None
    assert voiture.vitesse_autorisee() == pytest.approx(Voiture.VITESSE_MAX)
    assert voiture.decalage_lateral() == 0.0


def test_nouvelle_consigne_remplace_la_precedente(voiture: Voiture) -> None:
    voiture.reagir(CodeNotification.DEGAGEZ)
    voiture.reagir(CodeNotification.ATTENDEZ)
    assert voiture.consigne is CodeNotification.ATTENDEZ


@pytest.mark.parametrize("code", list(CodeNotification))
def test_vehicule_prioritaire_ignore_toutes_les_consignes(code: CodeNotification) -> None:
    vp = VehiculePrioritaire("vp_1", "S", "N")
    assert not vp.reagir(code)
    assert vp.consigne is None


@pytest.mark.parametrize("code", [CodeNotification.DEGAGEZ, CodeNotification.CHANGEZ_VOIE])
def test_pieton_ignore_les_consignes_de_circulation(pieton: Pieton, code: CodeNotification) -> None:
    assert not pieton.reagir(code)
    assert pieton.consigne is None
    assert pieton.decalage_lateral() == 0.0


def test_pieton_attend_pour_traverser(pieton: Pieton) -> None:
    assert pieton.reagir(CodeNotification.ATTENDEZ)
    assert pieton.consigne is CodeNotification.ATTENDEZ


# ---------- Mise à jour de l'état ----------

def test_vitesse_dans_les_limites_acceptee(voiture: Voiture) -> None:
    voiture.vitesse = 5.0
    assert voiture.vitesse == pytest.approx(5.0)


@pytest.mark.parametrize("vitesse", [-1.0, 30.0, float("nan")], ids=["negative", "trop-rapide", "nan"])
def test_vitesse_hors_limites_refusee(voiture: Voiture, vitesse: float) -> None:
    with pytest.raises(ValueError, match="hors limites"):
        voiture.vitesse = vitesse


def test_vitesse_non_numerique_refusee(voiture: Voiture) -> None:
    with pytest.raises(TypeError, match="vitesse"):
        voiture.vitesse = "5"


def test_position_mise_a_jour(voiture: Voiture) -> None:
    voiture.position = Position(3.5, -20.0)
    assert voiture.position == Position(3.5, -20.0)


def test_position_hors_classe_position_refusee(voiture: Voiture) -> None:
    with pytest.raises(TypeError, match="position"):
        voiture.position = (3.5, -20.0)


def test_segment_remis_a_none_en_quittant_l_anneau(voiture: Voiture) -> None:
    voiture.segment = "N-O"
    voiture.segment = None
    assert voiture.segment is None


def test_segment_vide_refuse(voiture: Voiture) -> None:
    with pytest.raises(ValueError, match="segment"):
        voiture.segment = ""


# ---------- Sérialisation ----------

def test_vers_dict_nouvel_usager(voiture: Voiture) -> None:
    assert voiture.vers_dict() == {
        "id": "voiture_12",
        "categorie": "voiture",
        "entree": "N",
        "sortie": "E",
        "x": None,
        "y": None,
        "vitesse": 0.0,
        "segment": None,
        "consigne": None,
    }


def test_aller_retour_dict_conserve_classe_et_etat(voiture: Voiture) -> None:
    voiture.position = Position(3.5, -20.0)
    voiture.vitesse = 4.2
    voiture.segment = "S-E"
    voiture.reagir(CodeNotification.DEGAGEZ)
    copie = Usager.depuis_dict(voiture.vers_dict())
    assert type(copie) is Voiture
    assert copie.vers_dict() == voiture.vers_dict()


def test_depuis_dict_contenu_d_un_hello() -> None:
    usager = Usager.depuis_dict({"id": "vp_1", "categorie": "vp", "entree": "S", "sortie": "N"})
    assert isinstance(usager, VehiculePrioritaire)
    assert usager.position is None
    assert usager.vitesse == 0.0


def test_depuis_dict_categorie_inconnue_refusee() -> None:
    with pytest.raises(ValueError, match="inconnue"):
        Usager.depuis_dict({"id": "tank_1", "categorie": "tank", "entree": "S", "sortie": "N"})


def test_depuis_dict_champ_manquant_refuse() -> None:
    with pytest.raises(ValueError, match="sortie"):
        Usager.depuis_dict({"id": "moto_1", "categorie": "moto", "entree": "S"})


# ---------- Trajectoire selon la catégorie ----------

@pytest.fixture
def rond_point() -> RondPoint:
    return RondPoint(["N", "E", "S", "O"], 20.0, 8)


@pytest.mark.parametrize("classe", [Voiture, Moto, Trottinette, VehiculePrioritaire])
def test_vehicule_passe_par_l_anneau(rond_point: RondPoint, classe: type) -> None:
    trajectoire = classe(f"{classe.CATEGORIE}_1", "S", "N").calculer_trajectoire(rond_point)
    assert [segment.nom for segment in trajectoire.segments] == ["S-E", "E-N"]


def test_pieton_traverse_sa_branche_sans_prendre_l_anneau(rond_point: RondPoint, pieton: Pieton) -> None:
    trajectoire = pieton.calculer_trajectoire(rond_point)
    assert Etape.TRAVERSEE in [troncon.etape for troncon in trajectoire.troncons]
    assert trajectoire.segments == []


def test_pieton_avec_entree_et_sortie_differentes_refuse() -> None:
    with pytest.raises(ValueError, match="une seule branche"):
        Pieton("pieton_5", "N", "E")


def test_trajectoire_vers_une_branche_inconnue_refusee(rond_point: RondPoint) -> None:
    with pytest.raises(BrancheInconnueError):
        Voiture("voiture_1", "S", "X").calculer_trajectoire(rond_point)
