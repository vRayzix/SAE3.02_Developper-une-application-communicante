"""Exceptions métier du projet.

Toutes héritent de CherryPieError. Le serveur peut ainsi distinguer une erreur
attendue (trame refusée, configuration incomplète...), qu'il journalise puis
ignore, d'un vrai bug qu'il ne doit pas masquer.
"""


class CherryPieError(Exception):
    """Classe mère de toutes les erreurs métier du projet."""


class ConfigurationInvalideError(CherryPieError):
    """Le fichier de configuration est absent, mal formé ou incohérent."""


class TrameInvalideError(CherryPieError):
    """Trame illisible : longueur aberrante, JSON invalide ou champ manquant."""


class SignatureInvalideError(CherryPieError):
    """Le HMAC d'une enveloppe ne correspond pas à son contenu."""


class RejeuDetecteError(CherryPieError):
    """Enveloppe hors de la fenêtre de temps acceptée, ou nonce déjà reçu."""


class BrancheInconnueError(CherryPieError):
    """La branche demandée n'existe pas dans la configuration du rond-point."""


class UsagerInconnuError(CherryPieError):
    """L'identifiant ne correspond à aucun usager connecté."""


class InscriptionRefuseeError(CherryPieError):
    """Le serveur a refusé le HELLO d'un usager."""

    def __init__(self, raison: str, reessayer: bool) -> None:
        """Crée l'erreur à partir du HELLO_ACK reçu.

        Args:
            raison (str): raison donnée par le serveur.
            reessayer (bool): True si le refus est provisoire (identifiant encore connecté ailleurs).
        """
        super().__init__(raison)
        self.__reessayer = reessayer

    @property
    def reessayer(self) -> bool:
        """bool: True si un nouvel essai peut réussir, False si le refus est définitif."""
        return self.__reessayer
