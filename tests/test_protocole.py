"""Tests du format des messages et des enveloppes."""

import dataclasses

import pytest

from cherrypie.commun.erreurs import TrameInvalideError
from cherrypie.commun.protocole import CodeNotification, Enveloppe, Message, TypeMessage


@pytest.fixture
def message_pos() -> Message:
    return Message(TypeMessage.POS, "voiture_12", {"x": 3.5, "y": -1.0, "vitesse": 8.3, "segment": "N-O"})


@pytest.fixture
def enveloppe_pos(message_pos: Message) -> Enveloppe:
    return Enveloppe(message_pos, 1727093000.512, "9f2c1a0b7d3e4f56", "ab" * 32)


# ---------- Énumérations ----------

def test_type_message_retrouve_depuis_sa_valeur() -> None:
    assert TypeMessage("VP_ALERT") is TypeMessage.VP_ALERT


def test_type_devant_retrouve_depuis_sa_valeur() -> None:
    assert TypeMessage("DEVANT") is TypeMessage.DEVANT


def test_code_notification_retrouve_depuis_sa_valeur() -> None:
    assert CodeNotification("OK_PASSER") is CodeNotification.OK_PASSER


# ---------- Construction ----------

def test_message_sans_donnees_a_un_dictionnaire_vide() -> None:
    assert Message(TypeMessage.PING, "moto_3").donnees == {}


def test_message_independant_du_dictionnaire_fourni() -> None:
    donnees = {"regulation": True}
    message = Message(TypeMessage.REGLAGE, "supervision", donnees)
    donnees["regulation"] = False
    assert message.donnees == {"regulation": True}


def test_message_donnees_modifiees_de_l_exterieur_sans_effet(message_pos: Message) -> None:
    message_pos.donnees["x"] = 0.0
    assert message_pos.donnees["x"] == pytest.approx(3.5)


def test_message_emetteur_vide_refuse() -> None:
    with pytest.raises(ValueError, match="émetteur"):
        Message(TypeMessage.PING, "")


def test_message_type_en_texte_refuse() -> None:
    with pytest.raises(TypeError, match="type de message"):
        Message("PING", "moto_3")


def test_message_donnees_hors_dictionnaire_refusees() -> None:
    with pytest.raises(TypeError, match="dictionnaire"):
        Message(TypeMessage.POS, "moto_3", [1.0, 2.0])


# ---------- Sérialisation ----------

def test_vers_dict_champs_du_protocole(message_pos: Message) -> None:
    assert message_pos.vers_dict() == {
        "type": "POS",
        "id": "voiture_12",
        "donnees": {"x": 3.5, "y": -1.0, "vitesse": 8.3, "segment": "N-O"},
    }


def test_aller_retour_dict_conserve_le_message(message_pos: Message) -> None:
    assert Message.depuis_dict(message_pos.vers_dict()) == message_pos


def test_messages_differents_non_egaux(message_pos: Message) -> None:
    autre = Message(TypeMessage.POS, "voiture_13", message_pos.donnees)
    assert autre != message_pos


# ---------- Lecture d'un dictionnaire invalide ----------

def test_depuis_dict_objet_non_dictionnaire_refuse() -> None:
    with pytest.raises(TrameInvalideError, match="objet JSON"):
        Message.depuis_dict(["POS", "voiture_12"])


def test_depuis_dict_champ_manquant_refuse() -> None:
    with pytest.raises(TrameInvalideError, match="donnees"):
        Message.depuis_dict({"type": "POS", "id": "voiture_12"})


def test_depuis_dict_type_inconnu_refuse() -> None:
    with pytest.raises(TrameInvalideError, match="inconnu"):
        Message.depuis_dict({"type": "TELEPORTE", "id": "voiture_12", "donnees": {}})


def test_depuis_dict_emetteur_non_textuel_refuse() -> None:
    with pytest.raises(TrameInvalideError, match="émetteur"):
        Message.depuis_dict({"type": "PING", "id": 12, "donnees": {}})


def test_depuis_dict_donnees_non_dictionnaire_refusees() -> None:
    with pytest.raises(TrameInvalideError, match="dictionnaire"):
        Message.depuis_dict({"type": "PING", "id": "moto_3", "donnees": "rien"})


# ---------- Enveloppe ----------

def test_enveloppe_vers_dict_a_plat(enveloppe_pos: Enveloppe) -> None:
    assert enveloppe_pos.vers_dict() == {
        "type": "POS",
        "id": "voiture_12",
        "ts": 1727093000.512,
        "nonce": "9f2c1a0b7d3e4f56",
        "donnees": {"x": 3.5, "y": -1.0, "vitesse": 8.3, "segment": "N-O"},
        "hmac": "ab" * 32,
    }


def test_enveloppe_aller_retour_octets(enveloppe_pos: Enveloppe) -> None:
    assert Enveloppe.depuis_octets(enveloppe_pos.vers_octets()) == enveloppe_pos


def test_enveloppe_non_modifiable(enveloppe_pos: Enveloppe) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        enveloppe_pos.nonce = "0000"


def test_enveloppe_non_signee_a_un_hmac_vide(message_pos: Message) -> None:
    assert Enveloppe(message_pos, 1727093000.0, "00ff").hmac == ""


# ---------- Lecture d'une enveloppe invalide ----------

def test_enveloppe_octets_non_json_refuses() -> None:
    with pytest.raises(TrameInvalideError, match="JSON invalide"):
        Enveloppe.depuis_octets(b'{"type": "POS", ')


def test_enveloppe_octets_non_utf8_refuses() -> None:
    with pytest.raises(TrameInvalideError, match="UTF-8"):
        Enveloppe.depuis_octets(b"\xff\xfe\x00")


def test_enveloppe_champ_nonce_manquant_refuse(enveloppe_pos: Enveloppe) -> None:
    contenu = enveloppe_pos.vers_dict()
    del contenu["nonce"]
    with pytest.raises(TrameInvalideError, match="nonce"):
        Enveloppe.depuis_dict(contenu)


def test_enveloppe_nonce_vide_refuse(enveloppe_pos: Enveloppe) -> None:
    contenu = enveloppe_pos.vers_dict()
    contenu["nonce"] = ""
    with pytest.raises(TrameInvalideError, match="nonce"):
        Enveloppe.depuis_dict(contenu)


@pytest.mark.parametrize("ts", ["1727093000", True, None], ids=["texte", "booleen", "null"])
def test_enveloppe_horodatage_non_numerique_refuse(enveloppe_pos: Enveloppe, ts: object) -> None:
    contenu = enveloppe_pos.vers_dict()
    contenu["ts"] = ts
    with pytest.raises(TrameInvalideError, match="horodatage"):
        Enveloppe.depuis_dict(contenu)


def test_enveloppe_horodatage_nan_refuse() -> None:
    octets = b'{"type":"PING","id":"moto_3","ts":NaN,"nonce":"00ff","donnees":{},"hmac":""}'
    with pytest.raises(TrameInvalideError, match="fini"):
        Enveloppe.depuis_octets(octets)
