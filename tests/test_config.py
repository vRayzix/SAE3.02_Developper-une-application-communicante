"""Tests de la lecture et de la validation de config.ini."""

import traceback
from pathlib import Path

import pytest

from cherrypie.commun.config import Configuration
from cherrypie.commun.erreurs import ConfigurationInvalideError

CHEMIN_EXEMPLE = Path(__file__).resolve().parent.parent / "config.exemple.ini"


@pytest.fixture
def texte_exemple() -> str:
    return CHEMIN_EXEMPLE.read_text(encoding="utf-8")


def ecrire_config(dossier: Path, texte: str) -> Path:
    chemin = dossier / "config.ini"
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def ecrire_variante(dossier: Path, texte: str, ligne: str, remplacement: str) -> Path:
    """Écrit une copie du fichier d'exemple dans laquelle une ligne a été remplacée."""
    assert ligne in texte, f"ligne absente du fichier d'exemple : {ligne!r}"
    return ecrire_config(dossier, texte.replace(ligne, remplacement))


# ---------- Lecture du fichier d'exemple ----------

def test_exemple_valeurs_reseau() -> None:
    config = Configuration.depuis_fichier(CHEMIN_EXEMPLE)
    assert config.hote == "127.0.0.1"
    assert config.port_tcp == 5000
    assert config.port_udp == 5001


def test_exemple_valeurs_securite_et_delais() -> None:
    config = Configuration.depuis_fichier(CHEMIN_EXEMPLE)
    assert config.cle_hmac == b"remplacer_par_une_cle_secrete"
    assert config.fenetre_anti_rejeu == pytest.approx(5.0)
    assert config.intervalle_ping == pytest.approx(2.0)
    assert config.timeout_client == pytest.approx(6.0)
    assert config.intervalle_position == pytest.approx(0.2)
    assert config.intervalle_etat == pytest.approx(0.2)
    assert config.backoff_initial == pytest.approx(1.0)
    assert config.backoff_max == pytest.approx(10.0)


def test_exemple_valeurs_rond_point() -> None:
    config = Configuration.depuis_fichier(CHEMIN_EXEMPLE)
    assert config.branches == ["N", "E", "S", "O"]
    assert config.rayon == pytest.approx(20.0)
    assert config.capacite_par_branche == 8


def test_exemple_valeurs_bdd() -> None:
    config = Configuration.depuis_fichier(CHEMIN_EXEMPLE)
    assert config.parametres_bdd == {
        "hote": "localhost",
        "port": 3306,
        "utilisateur": "cherrypie",
        "mot_de_passe": "remplacer_par_le_mot_de_passe",
        "base": "cherrypie",
    }


def test_branches_modifiees_de_l_exterieur_sans_effet() -> None:
    config = Configuration.depuis_fichier(CHEMIN_EXEMPLE)
    config.branches.append("X")
    assert config.branches == ["N", "E", "S", "O"]


# ---------- Fichier absent ou illisible ----------

def test_fichier_introuvable_refuse(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationInvalideError, match="introuvable"):
        Configuration.depuis_fichier(tmp_path / "absent.ini")


def test_fichier_sans_section_refuse(tmp_path: Path) -> None:
    chemin = ecrire_config(tmp_path, "hote = 127.0.0.1\n")
    with pytest.raises(ConfigurationInvalideError, match="ligne 1 : valeur placée avant toute section"):
        Configuration.depuis_fichier(chemin)


def test_fichier_non_utf8_refuse(tmp_path: Path, texte_exemple: str) -> None:
    chemin = tmp_path / "config.ini"
    chemin.write_bytes(texte_exemple.encode("latin-1"))
    with pytest.raises(ConfigurationInvalideError, match="UTF-8"):
        Configuration.depuis_fichier(chemin)


# ---------- Valeurs manquantes ----------

def test_section_absente_refusee(tmp_path: Path, texte_exemple: str) -> None:
    chemin = ecrire_variante(tmp_path, texte_exemple, "[bdd]", "[base_de_donnees]")
    with pytest.raises(ConfigurationInvalideError, match=r"section \[bdd\]"):
        Configuration.depuis_fichier(chemin)


def test_cle_absente_refusee(tmp_path: Path, texte_exemple: str) -> None:
    chemin = ecrire_variante(tmp_path, texte_exemple, "port_tcp = 5000\n", "")
    with pytest.raises(ConfigurationInvalideError, match="port_tcp absent"):
        Configuration.depuis_fichier(chemin)


def test_cle_vide_refusee(tmp_path: Path, texte_exemple: str) -> None:
    chemin = ecrire_variante(tmp_path, texte_exemple, "cle_hmac = remplacer_par_une_cle_secrete", "cle_hmac =")
    with pytest.raises(ConfigurationInvalideError, match="cle_hmac est vide"):
        Configuration.depuis_fichier(chemin)


# ---------- Valeurs incohérentes ----------

VALEURS_INCOHERENTES = [
    pytest.param("port_tcp = 5000", "port_tcp = cinq_mille", "doit être un entier", id="port-non-entier"),
    pytest.param("port_udp = 5001", "port_udp = 70000", "au plus 65535", id="port-trop-grand"),
    pytest.param("port = 3306", "port = 0", "au moins 1", id="port-bdd-nul"),
    pytest.param("intervalle_ping = 2", "intervalle_ping = 0", "strictement positif", id="delai-nul"),
    pytest.param("intervalle_etat = 0.2", "intervalle_etat = -0.2", "strictement positif", id="cadence-negative"),
    pytest.param("intervalle_position = 0.2", "intervalle_position = 0,2", "doit être un nombre", id="virgule"),
    pytest.param("backoff_max = 10", "backoff_max = inf", "fini", id="delai-infini"),
    pytest.param("rayon = 20", "rayon = -20", "strictement positif", id="rayon-negatif"),
    pytest.param("capacite_par_branche = 8", "capacite_par_branche = 0", "au moins 1", id="capacite-nulle"),
    pytest.param("branches = N, E, S, O", "branches = N, S", "au moins 3 branches", id="trop-peu-de-branches"),
    pytest.param("branches = N, E, S, O", "branches = N, E, N, O", "double", id="branche-en-double"),
    pytest.param("branches = N, E, S, O", "branches = N, , S, O", "nom vide", id="branche-sans-nom"),
    pytest.param("timeout_client = 6", "timeout_client = 1", "timeout_client", id="timeout-sous-le-ping"),
    pytest.param("backoff_initial = 1", "backoff_initial = 20", "backoff_initial", id="backoff-inverse"),
]


@pytest.mark.parametrize(("ligne", "remplacement", "motif"), VALEURS_INCOHERENTES)
def test_valeur_incoherente_refusee(
    tmp_path: Path, texte_exemple: str, ligne: str, remplacement: str, motif: str
) -> None:
    chemin = ecrire_variante(tmp_path, texte_exemple, ligne, remplacement)
    with pytest.raises(ConfigurationInvalideError, match=motif):
        Configuration.depuis_fichier(chemin)


# ---------- Caractères spéciaux ----------

def test_mot_de_passe_avec_pourcent_lu_tel_quel(tmp_path: Path, texte_exemple: str) -> None:
    chemin = ecrire_variante(
        tmp_path, texte_exemple, "mot_de_passe = remplacer_par_le_mot_de_passe", "mot_de_passe = 50%de_sel"
    )
    config = Configuration.depuis_fichier(chemin)
    assert config.parametres_bdd["mot_de_passe"] == "50%de_sel"


# ---------- Confidentialité ----------

def test_repr_de_la_configuration_ne_montre_pas_la_cle() -> None:
    config = Configuration.depuis_fichier(CHEMIN_EXEMPLE)
    assert "remplacer_par_une_cle_secrete" not in repr(config)
    assert "remplacer_par_le_mot_de_passe" not in repr(config)


SECRET = "cle_tres_secrete_42"

LIGNES_MALFORMEES = [
    pytest.param(
        "cle_hmac = remplacer_par_une_cle_secrete", f"cle_hmac {SECRET}", "ligne 12", id="sans-egal"
    ),
    pytest.param("[reseau]", f"cle_hmac = {SECRET}\n[reseau]", "ligne 4", id="avant-toute-section"),
]


@pytest.mark.parametrize(("ligne", "remplacement", "position"), LIGNES_MALFORMEES)
def test_ligne_malformee_signalee_sans_son_contenu(
    tmp_path: Path, texte_exemple: str, ligne: str, remplacement: str, position: str
) -> None:
    chemin = ecrire_variante(tmp_path, texte_exemple, ligne, remplacement)
    with pytest.raises(ConfigurationInvalideError, match=position) as erreur:
        Configuration.depuis_fichier(chemin)
    # La trace complète est ce qui finirait dans un journal : l'erreur chaînée ne doit pas y figurer.
    assert SECRET not in "".join(traceback.format_exception(erreur.value))
