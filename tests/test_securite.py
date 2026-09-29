"""Tests de la signature HMAC des enveloppes."""

import dataclasses
import re
import time

import pytest

from cherrypie.commun.erreurs import SignatureInvalideError
from cherrypie.commun.protocole import Enveloppe, Message, TypeMessage
from cherrypie.commun.securite import Signataire

CLE = b"cle_de_test_partagee"


@pytest.fixture
def signataire() -> Signataire:
    return Signataire(CLE)


@pytest.fixture
def message_alerte() -> Message:
    return Message(TypeMessage.VP_ALERT, "vp_1", {"entree": "N", "sortie": "E", "eta": 8.0})


@pytest.fixture
def enveloppe_signee(signataire: Signataire, message_alerte: Message) -> Enveloppe:
    return signataire.signer(message_alerte)


# ---------- Signature ----------

def test_signer_conserve_le_message(enveloppe_signee: Enveloppe, message_alerte: Message) -> None:
    assert enveloppe_signee.message == message_alerte


def test_signer_horodate_a_l_instant_present(signataire: Signataire, message_alerte: Message) -> None:
    avant = time.time()
    enveloppe = signataire.signer(message_alerte)
    assert avant <= enveloppe.ts <= time.time()


def test_signer_produit_un_nonce_et_un_hmac_hexadecimaux(enveloppe_signee: Enveloppe) -> None:
    assert re.fullmatch(r"[0-9a-f]{16}", enveloppe_signee.nonce)
    assert re.fullmatch(r"[0-9a-f]{64}", enveloppe_signee.hmac)


def test_signer_deux_fois_donne_deux_nonces(signataire: Signataire, message_alerte: Message) -> None:
    assert signataire.signer(message_alerte).nonce != signataire.signer(message_alerte).nonce


def test_cle_vide_refusee() -> None:
    with pytest.raises(ValueError, match="clé"):
        Signataire(b"")


# ---------- Vérification d'une enveloppe authentique ----------

def test_verifier_enveloppe_intacte_acceptee(signataire: Signataire, enveloppe_signee: Enveloppe) -> None:
    signataire.verifier(enveloppe_signee)


def test_verifier_apres_passage_par_le_reseau_acceptee(signataire: Signataire, enveloppe_signee: Enveloppe) -> None:
    signataire.verifier(Enveloppe.depuis_octets(enveloppe_signee.vers_octets()))


def test_verifier_donnees_recues_dans_un_autre_ordre_acceptee(
    signataire: Signataire, enveloppe_signee: Enveloppe
) -> None:
    contenu = enveloppe_signee.vers_dict()
    contenu["donnees"] = dict(reversed(list(contenu["donnees"].items())))
    signataire.verifier(Enveloppe.depuis_dict(contenu))


# ---------- Vérification d'une enveloppe altérée ----------

def test_verifier_donnees_modifiees_refusee(signataire: Signataire, enveloppe_signee: Enveloppe) -> None:
    falsifie = Message(TypeMessage.VP_ALERT, "vp_1", {"entree": "S", "sortie": "E", "eta": 8.0})
    with pytest.raises(SignatureInvalideError):
        signataire.verifier(dataclasses.replace(enveloppe_signee, message=falsifie))


def test_verifier_emetteur_usurpe_refuse(signataire: Signataire, enveloppe_signee: Enveloppe) -> None:
    usurpe = Message(TypeMessage.VP_ALERT, "vp_2", enveloppe_signee.message.donnees)
    with pytest.raises(SignatureInvalideError):
        signataire.verifier(dataclasses.replace(enveloppe_signee, message=usurpe))


def test_verifier_horodatage_modifie_refuse(signataire: Signataire, enveloppe_signee: Enveloppe) -> None:
    with pytest.raises(SignatureInvalideError):
        signataire.verifier(dataclasses.replace(enveloppe_signee, ts=enveloppe_signee.ts + 1))


def test_verifier_nonce_modifie_refuse(signataire: Signataire, enveloppe_signee: Enveloppe) -> None:
    with pytest.raises(SignatureInvalideError):
        signataire.verifier(dataclasses.replace(enveloppe_signee, nonce="0" * 16))


def test_verifier_signee_avec_une_autre_cle_refusee(signataire: Signataire, message_alerte: Message) -> None:
    enveloppe = Signataire(b"une_autre_cle").signer(message_alerte)
    with pytest.raises(SignatureInvalideError):
        signataire.verifier(enveloppe)


def test_verifier_hmac_vide_refuse(signataire: Signataire, enveloppe_signee: Enveloppe) -> None:
    with pytest.raises(SignatureInvalideError):
        signataire.verifier(dataclasses.replace(enveloppe_signee, hmac=""))


def test_verifier_hmac_non_ascii_refuse(signataire: Signataire, enveloppe_signee: Enveloppe) -> None:
    with pytest.raises(SignatureInvalideError):
        signataire.verifier(dataclasses.replace(enveloppe_signee, hmac="é" * 64))
