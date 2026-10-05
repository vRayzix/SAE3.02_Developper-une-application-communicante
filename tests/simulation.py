"""Simulation sans réseau : la logique du serveur et les déplacements des clients, pas à pas.

Elle fait ce que font les ClientUsager et la boucle du serveur, sans sockets ni threads :
les scénarios longs restent rapides et donnent toujours le même résultat.
"""

from collections.abc import Callable

from cherrypie.client.deplacement import Deplacement
from cherrypie.commun.protocole import CodeNotification, Message, TypeMessage
from cherrypie.modele.rond_point import RondPoint
from cherrypie.modele.trajectoire import Etape
from cherrypie.modele.usager import Usager, VehiculePrioritaire
from cherrypie.serveur.logique import LogiqueServeur

# Une simulation ne s'interrompt jamais : aucune session n'a l'occasion d'expirer.
TIMEOUT_INFINI = float("inf")


class Simulation:
    """Rond-point simulé : chaque pas fait avancer tous les usagers puis tourne une cadence du serveur."""

    def __init__(self, rond_point: RondPoint, pas: float = 0.2) -> None:
        self.__rond_point = rond_point
        self.__pas = pas
        self.__logique = LogiqueServeur(rond_point, TIMEOUT_INFINI)
        self.__instant = 0.0
        self.__en_route: dict[int, Deplacement] = {}
        self.__vps_annonces: set[int] = set()
        self.__supervision = self.__logique.ouvrir_session(0.0)
        self.__logique.traiter_tcp(self.__supervision, Message(TypeMessage.ABONNEMENT, "supervision"), 0.0)

    @property
    def logique(self) -> LogiqueServeur:
        return self.__logique

    @property
    def instant(self) -> float:
        return self.__instant

    @property
    def en_route(self) -> list[Deplacement]:
        """list[Deplacement]: usagers qui n'ont pas fini leur trajet."""
        return list(self.__en_route.values())

    def regler(self, regulation: bool) -> None:
        """Active ou coupe la régulation, comme le ferait la supervision (REGLAGE)."""
        reglage = Message(TypeMessage.REGLAGE, "supervision", {"regulation": regulation})
        self.__logique.traiter_tcp(self.__supervision, reglage, self.__instant)

    def ajouter(self, usager: Usager, avancement: float = 0.0) -> Deplacement:
        """Inscrit un usager comme le ferait son client, puis le place à un avancement donné.

        Un VP s'annonce aussitôt (VP_ALERT), comme le fait son client.
        """
        numero = self.__logique.ouvrir_session(self.__instant)
        description = {"categorie": usager.CATEGORIE, "entree": usager.branche_entree, "sortie": usager.branche_sortie}
        reponse = self.__logique.traiter_tcp(numero, Message(TypeMessage.HELLO, usager.identifiant, description), self.__instant)
        assert reponse.messages[0].donnees["accepte"], reponse.messages[0].donnees
        deplacement = Deplacement(usager, usager.calculer_trajectoire(self.__rond_point))
        if avancement > 0:
            deplacement.avancer(avancement / usager.VITESSE_MAX)
        self.__en_route[numero] = deplacement
        if isinstance(usager, VehiculePrioritaire):
            reste = deplacement.trajectoire.longueur_approche - deplacement.avancement
            annonce = {"entree": usager.branche_entree, "sortie": usager.branche_sortie, "eta": reste / usager.VITESSE_MAX}
            self.__logique.traiter_tcp(numero, Message(TypeMessage.VP_ALERT, usager.identifiant, annonce), self.__instant)
            self.__vps_annonces.add(numero)
        return deplacement

    def avancer_jusqu_a(self, condition: Callable[[], bool], duree_max: float) -> bool:
        """Avance pas à pas jusqu'à ce que la condition soit vraie ; renvoie False si la durée est dépassée."""
        while not condition():
            if self.__instant >= duree_max:
                return False
            self.faire_un_pas()
        return True

    def faire_un_pas(self) -> None:
        """Fait avancer chaque usager d'un pas, transmet sa position, puis applique la cadence du serveur."""
        self.__instant += self.__pas
        for numero, deplacement in list(self.__en_route.items()):
            deplacement.avancer(self.__pas)
            self.__logique.traiter_udp(self.__position(deplacement.usager), self.__instant)
            if numero in self.__vps_annonces and deplacement.usager.etape is Etape.SORTIE:
                fin = Message(TypeMessage.VP_FIN, deplacement.usager.identifiant)
                self.__logique.traiter_tcp(numero, fin, self.__instant)
                self.__vps_annonces.discard(numero)
            if deplacement.termine:
                self.__logique.fermer_session(numero)
                del self.__en_route[numero]
        for numero, message in self.__logique.cadencer():
            deplacement = self.__en_route.get(numero)
            if deplacement is None:
                continue
            if message.type is TypeMessage.DEVANT:
                deplacement.noter_devant(message.donnees["distance"], message.donnees["ceder"])
            elif message.type is TypeMessage.NOTIF:
                deplacement.usager.reagir(CodeNotification(message.donnees["code"]))

    @staticmethod
    def __position(usager: Usager) -> Message:
        donnees = {
            "x": usager.position.x,
            "y": usager.position.y,
            "vitesse": usager.vitesse,
            "segment": usager.segment,
            "etape": usager.etape.value,
        }
        return Message(TypeMessage.POS, usager.identifiant, donnees)
