"""Registre des usagers connectés au serveur."""

from __future__ import annotations

from cherrypie.commun.erreurs import UsagerInconnuError
from cherrypie.modele.usager import Usager


class Registre:
    """Usagers connectés, rangés par identifiant.

    Le registre référence les usagers sans décider de leur vie : c'est la session
    TCP de chacun qui l'inscrit au HELLO et le retire à sa fermeture.
    """

    def __init__(self) -> None:
        """Crée un registre vide."""
        self.__usagers: dict[str, Usager] = {}

    @property
    def usagers(self) -> list[Usager]:
        """list[Usager]: usagers connectés, dans l'ordre d'arrivée (copie)."""
        return list(self.__usagers.values())

    def contient(self, identifiant: str) -> bool:
        """Indique si un usager est connecté sous cet identifiant.

        Args:
            identifiant (str): identifiant de l'usager.

        Returns:
            bool: True s'il est dans le registre.
        """
        return identifiant in self.__usagers

    def ajouter(self, usager: Usager) -> None:
        """Inscrit un usager.

        Args:
            usager (Usager): usager qui vient de se présenter.

        Raises:
            ValueError: si un usager est déjà inscrit sous le même identifiant.
        """
        if usager.identifiant in self.__usagers:
            raise ValueError(f"l'identifiant {usager.identifiant} est déjà inscrit")
        self.__usagers[usager.identifiant] = usager

    def obtenir(self, identifiant: str) -> Usager:
        """Retrouve un usager connecté.

        Args:
            identifiant (str): identifiant de l'usager.

        Returns:
            Usager: l'usager inscrit sous cet identifiant.

        Raises:
            UsagerInconnuError: si aucun usager connecté ne porte cet identifiant.
        """
        try:
            return self.__usagers[identifiant]
        except KeyError:
            raise UsagerInconnuError(f"aucun usager connecté sous l'identifiant {identifiant!r}") from None

    def retirer(self, identifiant: str) -> Usager:
        """Retire un usager du registre.

        Args:
            identifiant (str): identifiant de l'usager.

        Returns:
            Usager: l'usager retiré.

        Raises:
            UsagerInconnuError: si aucun usager connecté ne porte cet identifiant.
        """
        usager = self.obtenir(identifiant)
        del self.__usagers[identifiant]
        return usager
