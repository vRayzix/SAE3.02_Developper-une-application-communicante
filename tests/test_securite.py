"""Tests de la signature HMAC et de la protection anti-rejeu."""

import dataclasses
import re
import time

import pytest

from cherrypie.commun.erreurs import RejeuDetecteError, SignatureInvalideError
from cherrypie.commun.protocole import Enveloppe, Message, TypeMessage
from cherrypie.commun.securite import GardeAntiRejeu, Signataire

CLE = b"cle_de_test_partagee"
FENETRE = 5.0
T0 = 1_727_093_000.0


def enveloppe_datee(ts: float, nonce: str = "a1b2c3d4e5f60718") -> Enveloppe:
    return Enveloppe(Message(TypeMessage.PING, "moto_3"), ts, nonce, "00" * 32)


@pytest.fixture
def signataire() -> Signataire:
    return Signataire(CLE)


@pytest.fixture
def garde() -> GardeAntiRejeu:
    return GardeAntiRejeu(FENETRE)


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


# ---------- Anti-rejeu : horodatage ----------

def test_controler_enveloppe_recente_acceptee(garde: GardeAntiRejeu) -> None:
    garde.controler(enveloppe_datee(T0), maintenant=T0 + 0.2)


def test_controler_enveloppe_a_la_limite_de_la_fenetre_acceptee(garde: GardeAntiRejeu) -> None:
    garde.controler(enveloppe_datee(T0), maintenant=T0 + FENETRE)


def test_controler_enveloppe_trop_ancienne_refusee(garde: GardeAntiRejeu) -> None:
    with pytest.raises(RejeuDetecteError, match="hors fenêtre"):
        garde.controler(enveloppe_datee(T0), maintenant=T0 + FENETRE + 0.1)


def test_controler_enveloppe_datee_du_futur_refusee(garde: GardeAntiRejeu) -> None:
    with pytest.raises(RejeuDetecteError, match="hors fenêtre"):
        garde.controler(enveloppe_datee(T0 + FENETRE + 0.1), maintenant=T0)


def test_fenetre_nulle_refusee() -> None:
    with pytest.raises(ValueError, match="fenêtre"):
        GardeAntiRejeu(0)


# ---------- Anti-rejeu : nonces ----------

def test_controler_meme_enveloppe_deux_fois_refusee(garde: GardeAntiRejeu) -> None:
    enveloppe = enveloppe_datee(T0)
    garde.controler(enveloppe, maintenant=T0)
    with pytest.raises(RejeuDetecteError, match="déjà reçu"):
        garde.controler(enveloppe, maintenant=T0 + 1)


def test_controler_nonces_differents_acceptes(garde: GardeAntiRejeu) -> None:
    garde.controler(enveloppe_datee(T0, "0000000000000001"), maintenant=T0)
    garde.controler(enveloppe_datee(T0, "0000000000000002"), maintenant=T0)
    assert len(garde.nonces_vus) == 2


def test_controler_enveloppe_refusee_ne_retient_pas_son_nonce(garde: GardeAntiRejeu) -> None:
    with pytest.raises(RejeuDetecteError):
        garde.controler(enveloppe_datee(T0 - 60), maintenant=T0)
    assert garde.nonces_vus == {}


def test_nonce_oublie_une_fois_la_fenetre_passee(garde: GardeAntiRejeu) -> None:
    garde.controler(enveloppe_datee(T0, "0000000000000001"), maintenant=T0)
    garde.controler(enveloppe_datee(T0 + 10, "0000000000000002"), maintenant=T0 + 10)
    assert list(garde.nonces_vus) == ["0000000000000002"]


def test_rejeu_apres_oubli_du_nonce_toujours_refuse(garde: GardeAntiRejeu) -> None:
    enveloppe = enveloppe_datee(T0)
    garde.controler(enveloppe, maintenant=T0)
    garde.controler(enveloppe_datee(T0 + 10, "ffffffffffffffff"), maintenant=T0 + 10)
    with pytest.raises(RejeuDetecteError, match="hors fenêtre"):
        garde.controler(enveloppe, maintenant=T0 + 10)


# ---------- Chaîne de réception complète ----------

def test_trame_capturee_puis_rejouee_refusee(
    signataire: Signataire, garde: GardeAntiRejeu, message_alerte: Message
) -> None:
    octets = signataire.signer(message_alerte).vers_octets()
    premiere = Enveloppe.depuis_octets(octets)
    signataire.verifier(premiere)
    garde.controler(premiere, time.time())
    rejouee = Enveloppe.depuis_octets(octets)
    # La signature d'une trame rejouée est intacte : seul l'anti-rejeu peut l'arrêter.
    signataire.verifier(rejouee)
    with pytest.raises(RejeuDetecteError, match="déjà reçu"):
        garde.controler(rejouee, time.time())


# ---------- Confidentialité de la clé ----------

def test_repr_du_signataire_ne_montre_pas_la_cle(signataire: Signataire) -> None:
    assert CLE.decode() not in repr(signataire)
    assert CLE.decode() not in str(signataire)


def test_refus_de_signature_ne_montre_ni_la_cle_ni_de_hmac(
    signataire: Signataire, enveloppe_signee: Enveloppe
) -> None:
    with pytest.raises(SignatureInvalideError) as refus:
        signataire.verifier(dataclasses.replace(enveloppe_signee, nonce="0" * 16))
    assert CLE.decode() not in str(refus.value)
    # Montrer le HMAC attendu donnerait à un attaquant la signature valide du message.
    assert not re.search(r"[0-9a-f]{64}", str(refus.value))
