"""État d'une session TCP, vu par la logique du serveur."""

from __future__ import annotations


class Session:
    """Connexion TCP d'un client, du point de vue de la logique du serveur.

    Une session devient celle d'un usager au HELLO, ou celle d'une supervision à
    l'ABONNEMENT. Elle ne connaît pas la socket : la boucle réseau fait le lien
    grâce au numéro de session.
    """

    def __init__(self, numero: int, maintenant: float) -> None:
        """Ouvre une session.

        Args:
            numero (int): numéro attribué par le serveur, jamais réutilisé.
            maintenant (float): instant d'ouverture, sur l'horloge monotone du serveur.
        """
        self.__numero = numero
        self.__derniere_activite = maintenant
        self.__identifiant: str | None = None
        self.__superviseur = False

    @property
    def numero(self) -> int:
        """int: numéro de la session."""
        return self.__numero

    @property
    def identifiant(self) -> str | None:
        """str | None: identifiant de l'usager de la session, None avant son HELLO."""
        return self.__identifiant

    @identifiant.setter
    def identifiant(self, valeur: str) -> None:
        """Rattache un usager à la session.

        Raises:
            ValueError: si l'identifiant est vide ou si la session a déjà un usager.
        """
        if not isinstance(valeur, str) or not valeur:
            raise ValueError(f"identifiant d'usager invalide : {valeur!r}")
        if self.__identifiant is not None:
            raise ValueError(f"la session {self.__numero} porte déjà l'usager {self.__identifiant}")
        self.__identifiant = valeur

    @property
    def superviseur(self) -> bool:
        """bool: True si la session est celle d'une supervision abonnée aux STATE."""
        return self.__superviseur

    @superviseur.setter
    def superviseur(self, valeur: bool) -> None:
        """Abonne ou désabonne la session aux STATE.

        Raises:
            TypeError: si la valeur n'est pas un booléen.
        """
        if not isinstance(valeur, bool):
            raise TypeError(f"un abonnement vaut True ou False (reçu : {valeur!r})")
        self.__superviseur = valeur

    @property
    def derniere_activite(self) -> float:
        """float: instant du dernier message reçu, sur l'horloge monotone du serveur."""
        return self.__derniere_activite

    @derniere_activite.setter
    def derniere_activite(self, valeur: float) -> None:
        """Note l'arrivée d'un message.

        Raises:
            ValueError: si l'instant précède la dernière activité connue ; l'horloge
                du serveur est monotone, ce serait une erreur de programmation.
        """
        # Écrit ainsi, le test refuse aussi NaN, pour lequel toute comparaison est fausse.
        if not valeur >= self.__derniere_activite:
            raise ValueError(f"instant {valeur} antérieur à la dernière activité ({self.__derniere_activite})")
        self.__derniere_activite = valeur

    def est_expiree(self, maintenant: float, delai: float) -> bool:
        """Indique si la session est restée silencieuse trop longtemps.

        Args:
            maintenant (float): instant présent, sur l'horloge monotone du serveur.
            delai (float): silence maximal toléré, en secondes.

        Returns:
            bool: True si aucun message n'est arrivé depuis plus de `delai` secondes.
        """
        return maintenant - self.__derniere_activite > delai
