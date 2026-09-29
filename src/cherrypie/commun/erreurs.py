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
