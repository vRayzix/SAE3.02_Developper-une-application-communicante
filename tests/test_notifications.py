"""Tests des notifications envoyées aux usagers."""

import dataclasses

import pytest

from cherrypie.commun.protocole import CodeNotification, TypeMessage
from cherrypie.serveur.notifications import TEXTE_DEGAGEZ, Notification


@pytest.fixture
def notification() -> Notification:
    return Notification("voiture_12", CodeNotification.DEGAGEZ, TEXTE_DEGAGEZ)


def test_notification_devient_un_message_notif(notification: Notification) -> None:
    message = notification.vers_message("serveur")
    assert message.type is TypeMessage.NOTIF
    assert message.emetteur == "serveur"
    assert message.donnees == {"code": "DEGAGEZ", "message": TEXTE_DEGAGEZ}


def test_notification_non_modifiable(notification: Notification) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        notification.code = CodeNotification.OK_PASSER
