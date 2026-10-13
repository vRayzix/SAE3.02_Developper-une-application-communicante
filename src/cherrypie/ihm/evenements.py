"""Événements du serveur, déduits de deux STATE successifs."""

from __future__ import annotations

from datetime import datetime, timedelta

CHAUSSEES = {"entree": "chaussée d'entrée", "sortie": "chaussée de sortie"}


class EvenementsServeur:
    """Compare chaque STATE au précédent et décrit ce qui a changé, en phrases.

    Le serveur diffuse un état, pas des événements : un VP annoncé apparaît dans `vps`, une
    entrée temporisée dans `entrees_bloquees`, un passage fermé dans `passages_fermes`. Le
    premier STATE après une connexion sert de référence et ne produit aucun événement.
    """

    def __init__(self, libelles: dict[str, str]) -> None:
        """Prépare la comparaison.

        Args:
            libelles (dict[str, str]): nom de rue de chaque branche, par identifiant.
        """
        self.__libelles = dict(libelles)
        self.__precedent: dict | None = None

    @property
    def libelles(self) -> dict[str, str]:
        """dict[str, str]: nom de rue de chaque branche, par identifiant (copie)."""
        return dict(self.__libelles)

    def oublier(self) -> None:
        """Oublie le dernier STATE : après une reconnexion, le suivant sert de nouvelle référence."""
        self.__precedent = None

    def comparer(self, etat: dict, maintenant: datetime) -> list[str]:
        """Décrit les changements depuis le STATE précédent, puis retient celui-ci.

        Args:
            etat (dict): données d'un STATE.
            maintenant (datetime): heure de réception, pour situer l'arrivée prévue d'un VP.

        Returns:
            list[str]: une phrase par événement, dans un ordre stable.
        """
        precedent, self.__precedent = self.__precedent, etat
        if precedent is None:
            return []
        return (
            self.__regulation(precedent, etat)
            + self.__vps(precedent, etat, maintenant)
            + self.__entrees(precedent, etat)
            + self.__passages(precedent, etat)
        )

    @staticmethod
    def __regulation(precedent: dict, etat: dict) -> list[str]:
        """Régulation activée ou coupée."""
        if precedent["regulation"] == etat["regulation"]:
            return []
        return ["Régulation activée" if etat["regulation"] else "Régulation coupée"]

    def __vps(self, precedent: dict, etat: dict, maintenant: datetime) -> list[str]:
        """VP annoncés, avec leur trajet et leur arrivée prévue, puis VP dont la traversée est finie."""
        avant = {vp["id"] for vp in precedent["vps"]}
        apres = {vp["id"] for vp in etat["vps"]}
        evenements = []
        for vp in etat["vps"]:
            if vp["id"] not in avant:
                arrivee = (maintenant + timedelta(seconds=vp["eta"])).time().isoformat(timespec="seconds")
                trajet = f"{self.__libelles[vp['entree']]} vers {self.__libelles[vp['sortie']]}"
                evenements.append(f"VP {vp['id']} annoncé : {trajet}, à l'anneau vers {arrivee}")
        evenements += [f"VP {identifiant} : fin de traversée" for identifiant in sorted(avant - apres)]
        return evenements

    def __entrees(self, precedent: dict, etat: dict) -> list[str]:
        """Entrées temporisées ou libérées."""
        avant, apres = set(precedent["entrees_bloquees"]), set(etat["entrees_bloquees"])
        return [f"Entrée temporisée : {self.__libelles[branche]}" for branche in sorted(apres - avant)] + [
            f"Entrée libérée : {self.__libelles[branche]}" for branche in sorted(avant - apres)
        ]

    def __passages(self, precedent: dict, etat: dict) -> list[str]:
        """Demi-chaussées fermées ou rouvertes par un piéton."""
        avant = {(ferme["branche"], ferme["chaussee"]) for ferme in precedent["passages_fermes"]}
        apres = {(ferme["branche"], ferme["chaussee"]) for ferme in etat["passages_fermes"]}
        return [
            f"Passage piéton fermé : {self.__libelles[branche]}, {CHAUSSEES[chaussee]}"
            for branche, chaussee in sorted(apres - avant)
        ] + [
            f"Passage piéton rouvert : {self.__libelles[branche]}, {CHAUSSEES[chaussee]}"
            for branche, chaussee in sorted(avant - apres)
        ]
