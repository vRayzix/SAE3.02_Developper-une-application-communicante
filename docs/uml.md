# Diagramme de classes prévisionnel

Ce document décrit les classes prévues avant le développement. Il sera ajusté au fil de l'avancement, le diagramme final étant celui du code rendu.

Dépendances entre paquets : `commun` ne dépend d'aucun autre paquet ; `modele` utilise `commun` ; `serveur` et `client` utilisent `commun` et `modele` ; `ihm` lance des clients et lit la base ; seul `serveur` écrit dans `bdd`.

## Conventions

| Notation | Signification | En Python |
| --- | --- | --- |
| `-` | privé | attribut `self.__nom` ou méthode `__nom()` |
| `#` | protégé | méthode `_nom()`, réservée à la classe et à ses sous-classes |
| `+` | public | méthode ou propriété sans préfixe |
| souligné | membre de classe | constante de classe, `@classmethod` ou `@staticmethod` |
| `<<dataclass>>` | objet valeur | `@dataclass(frozen=True)`, champs publics en lecture seule |
| `<<enumeration>>` | énumération | sous-classe de `Enum` |

Tous les attributs d'instance sont privés, sauf les champs des objets valeur. Chacun est lu depuis l'extérieur par une propriété `@property` du même nom. Un setter n'existe que si l'attribut doit changer après la construction : il valide la valeur et lève une exception si elle est incohérente. Les setters prévus sont listés sous chaque diagramme. Les constructeurs ne sont pas représentés.

Relations : triangle vide pour l'héritage, losange plein pour la composition (la partie n'existe pas sans le tout), losange vide pour l'agrégation (le tout référence des objets qui existent sans lui), flèche simple pour l'association, flèche pointillée pour une dépendance ponctuelle.

## Paquet `commun`

### Erreurs métier

Toutes les erreurs du projet héritent de `CherryPieError`. Le serveur peut ainsi distinguer une trame refusée, qu'il journalise puis ignore, d'un vrai bug.

```mermaid
classDiagram
    class Exception
    class CherryPieError
    class ConfigurationInvalideError
    class TrameInvalideError
    class SignatureInvalideError
    class RejeuDetecteError
    class BrancheInconnueError
    class UsagerInconnuError

    Exception <|-- CherryPieError
    CherryPieError <|-- ConfigurationInvalideError
    CherryPieError <|-- TrameInvalideError
    CherryPieError <|-- SignatureInvalideError
    CherryPieError <|-- RejeuDetecteError
    CherryPieError <|-- BrancheInconnueError
    CherryPieError <|-- UsagerInconnuError
```

### Configuration, protocole, trames et sécurité

```mermaid
classDiagram
    class Configuration {
        -hote : str
        -port_tcp : int
        -port_udp : int
        -cle_hmac : bytes
        -fenetre_anti_rejeu : float
        -intervalle_ping : float
        -timeout_client : float
        -intervalle_position : float
        -backoff_initial : float
        -backoff_max : float
        -branches : list[str]
        -rayon : float
        -capacite_par_branche : int
        -parametres_bdd : dict[str, str | int]
        +depuis_fichier(chemin: str | Path) Configuration$
    }

    class TypeMessage {
        <<enumeration>>
        HELLO
        HELLO_ACK
        POS
        VP_ALERT
        VP_FIN
        NOTIF
        STATE
        ABONNEMENT
        REGLAGE
        PING
        PONG
        BYE
    }

    class CodeNotification {
        <<enumeration>>
        DEGAGEZ
        CHANGEZ_VOIE
        ATTENDEZ
        OK_PASSER
    }

    class Message {
        -type : TypeMessage
        -emetteur : str
        -donnees : dict
        +vers_dict() dict
        +depuis_dict(contenu: dict) Message$
    }

    class Enveloppe {
        <<dataclass>>
        +message : Message
        +ts : float
        +nonce : str
        +hmac : str
        +vers_dict() dict
        +vers_octets() bytes
        +depuis_dict(contenu: dict) Enveloppe$
        +depuis_octets(octets: bytes) Enveloppe$
    }

    class DecoupeurTrames {
        -tampon : bytearray
        +ajouter(octets: bytes) list[bytes]
        +encoder(charge: bytes) bytes$
    }

    class Signataire {
        -cle : bytes
        +signer(message: Message) Enveloppe
        +verifier(enveloppe: Enveloppe) None
        -calculer_hmac(enveloppe: Enveloppe) str
    }

    class GardeAntiRejeu {
        -fenetre : float
        -nonces_vus : dict[str, float]
        +controler(enveloppe: Enveloppe, maintenant: float) None
        -oublier_nonces_expires(maintenant: float) None
    }

    Message --> TypeMessage
    Enveloppe *-- Message
    Signataire ..> Enveloppe : crée et vérifie
    GardeAntiRejeu ..> Enveloppe : contrôle
```

- `Enveloppe` est la forme transmise sur le réseau : le `Message`, plus l'horodatage, le nonce et le HMAC. `Signataire.signer()` la construit ; à la réception, `Signataire.verifier()` puis `GardeAntiRejeu.controler()` la valident.
- `CodeNotification` fait partie du protocole plutôt que du serveur, parce que le client en a besoin pour réagir aux consignes.
- `DecoupeurTrames` tient le tampon d'une socket TCP : `ajouter()` renvoie les trames complètes et garde le reste pour la lecture suivante.

Setters prévus : aucun, ces objets ne changent plus une fois construits.

## Paquet `modele`

### Usagers

```mermaid
classDiagram
    class Position {
        <<dataclass>>
        +x : float
        +y : float
        +distance(autre: Position) float
    }

    class Usager {
        <<abstract>>
        +CATEGORIE : str$
        +VITESSE_MAX : float$
        +CONSIGNES_SUIVIES : frozenset[CodeNotification]$
        -identifiant : str
        -branche_entree : str
        -branche_sortie : str
        -position : Position | None
        -vitesse : float
        -segment : str | None
        -consigne : CodeNotification | None
        +reagir(code: CodeNotification) bool
        +vitesse_autorisee() float
        +decalage_lateral() float
        +calculer_trajectoire(rond_point: RondPoint) Trajectoire
        +vers_dict() dict
        +depuis_dict(contenu: dict) Usager$
    }

    class Voiture {
        +CATEGORIE$
        +VITESSE_MAX$
    }

    class Moto {
        +CATEGORIE$
        +VITESSE_MAX$
    }

    class Trottinette {
        +CATEGORIE$
        +VITESSE_MAX$
    }

    class Pieton {
        +CATEGORIE$
        +VITESSE_MAX$
        +CONSIGNES_SUIVIES$
        +calculer_trajectoire(rond_point: RondPoint) Trajectoire
    }

    class VehiculePrioritaire {
        +CATEGORIE$
        +VITESSE_MAX$
        +CONSIGNES_SUIVIES$
    }

    Usager <|-- Voiture
    Usager <|-- Moto
    Usager <|-- Trottinette
    Usager <|-- Pieton
    Usager <|-- VehiculePrioritaire
    Usager *-- "0..1" Position
    Usager ..> Trajectoire : calcule
```

`Usager.reagir()` applique la consigne reçue si elle fait partie de `CONSIGNES_SUIVIES` et renvoie `True` ; sinon il l'ignore et renvoie `False`. Chaque sous-classe redéfinit ce qui lui est propre :

| Classe | Catégorie | Vitesse max | Consignes suivies | Trajectoire |
| --- | --- | --- | --- | --- |
| `Voiture` | `voiture` | 8,3 m/s (30 km/h) | toutes | approche, anneau, sortie |
| `Moto` | `moto` | 8,3 m/s (30 km/h) | toutes | approche, anneau, sortie |
| `Trottinette` | `trottinette` | 5,6 m/s (20 km/h) | toutes | approche, anneau, sortie |
| `Pieton` | `pieton` | 1,4 m/s (5 km/h) | `ATTENDEZ`, `OK_PASSER` | traversée de sa branche |
| `VehiculePrioritaire` | `vp` | 11,1 m/s (40 km/h) | aucune, c'est lui qu'on laisse passer | approche, anneau, sortie |

- `vitesse_autorisee()` et `decalage_lateral()` traduisent la consigne en cours : vitesse réduite de moitié et décalage de 2 m pour `DEGAGEZ`, décalage seul pour `CHANGEZ_VOIE`. `ATTENDEZ` ne change pas la vitesse : l'usager avance jusqu'à la ligne d'entrée de sa trajectoire et s'y arrête. `OK_PASSER` lève la consigne.
- `Pieton` redéfinit `calculer_trajectoire()` : il ne prend pas l'anneau, il traverse une seule branche, qui est à la fois son entrée et sa sortie.
- `depuis_dict()` instancie la bonne sous-classe d'après la catégorie reçue dans le HELLO.
- `Position` a son propre module (`modele/position.py`), partagé par les usagers, le rond-point et les trajectoires. Elle refuse les coordonnées infinies ou NaN.

Setters : `Usager.position`, `Usager.vitesse` (entre 0 et la vitesse maximale de la catégorie) et `Usager.segment`, mis à jour par le client quand il avance et par le serveur à chaque POS reçu.

### Rond-point

```mermaid
classDiagram
    class RondPoint {
        -rayon : float
        -branches : list[Branche]
        -segments : list[Segment]
        +branche(nom: str) Branche
        +segments_entre(entree: str, sortie: str) list[Segment]
        +depuis_config(config: Configuration) RondPoint$
        -segment_partant_de(branche: Branche) Segment
    }

    class Branche {
        -nom : str
        -angle : float
        -capacite : int
        +point(distance_au_centre: float, decalage: float) Position
    }

    class Segment {
        -depart : Branche
        -arrivee : Branche
        -longueur : float
        +nom() str
    }

    RondPoint "1" *-- "3..*" Branche
    RondPoint "1" *-- "3..*" Segment
    Segment --> "2" Branche
```

- `RondPoint` crée ses branches et ses segments à partir de la configuration, et ils n'existent pas sans lui : composition.
- Les branches sont réparties régulièrement autour de l'anneau. La première est placée au nord, les suivantes dans le sens des aiguilles d'une montre : N, E, S et O tombent à leur place.
- Les segments suivent le sens de circulation, inverse des aiguilles d'une montre : `segments_entre("S", "N")` renvoie S-E puis E-N. Si l'entrée et la sortie sont la même branche, l'usager fait le tour complet.
- `RondPoint.branche()` lève `BrancheInconnueError` pour un nom qui n'existe pas.

Setters : aucun, la géométrie ne change plus une fois le rond-point construit.

### Trajectoires

```mermaid
classDiagram
    class Etape {
        <<enumeration>>
        APPROCHE
        ANNEAU
        TRAVERSEE
        SORTIE
    }

    class TronconDroit {
        <<dataclass>>
        +etape : Etape
        +depart : Position
        +arrivee : Position
        +longueur() float
        +segment() None
        +position_a(distance: float, decalage: float) Position
    }

    class TronconArc {
        <<dataclass>>
        +segment : Segment
        +rayon : float
        +etape() Etape
        +longueur() float
        +position_a(distance: float, decalage: float) Position
    }

    class Trajectoire {
        -troncons : list[TronconDroit | TronconArc]
        +longueur() float
        +longueur_approche() float
        +segments() list[Segment]
        +pour_vehicule(rond_point: RondPoint, entree: str, sortie: str) Trajectoire$
        +pour_pieton(rond_point: RondPoint, branche: str) Trajectoire$
        +position_a(avancement: float, decalage: float) Position
        +etape_a(avancement: float) Etape
        +segment_a(avancement: float) Segment | None
        +passe_par(segment: Segment) bool
        -troncon_a(avancement: float) tuple
    }

    Trajectoire "1" *-- "1..*" TronconDroit
    Trajectoire "1" *-- "0..*" TronconArc
    TronconArc o-- Segment
    TronconDroit --> Etape
    TronconDroit ..> Position : calcule
    TronconArc ..> Position : calcule
```

- Une trajectoire est une suite de tronçons parcourus l'un après l'autre : des tronçons droits sur les branches (approche, sortie, passage piéton) et des arcs sur l'anneau, un par segment. Les deux types de tronçons offrent les mêmes membres (`etape`, `longueur`, `segment`, `position_a()`) : la trajectoire trouve le tronçon qui correspond à l'avancement et lui délègue le calcul.
- L'avancement est la distance parcourue depuis le départ. `longueur_approche` donne la position de la ligne d'entrée, où s'arrête un usager qui a reçu `ATTENDEZ`. Un point situé pile à la jonction de deux tronçons appartient au premier : un usager arrêté sur la ligne est encore en approche.
- Un véhicule parcourt 50 m d'approche, les segments de l'anneau, puis 50 m de sortie. Un piéton parcourt 4 m de trottoir jusqu'au bord de la chaussée, traverse les 7 m du passage piéton, placé à 8 m de l'anneau, puis repart sur le trottoir d'en face : il croise l'approche des véhicules de cette branche.
- Le décalage latéral se compte vers la droite du sens de marche ; sur l'anneau, c'est l'extérieur.
- Les arcs ne font que référencer les segments du rond-point, sans les posséder : agrégation.

Setters : aucun, une trajectoire ne change plus une fois calculée.

## Paquet `serveur`

```mermaid
classDiagram
    class Serveur {
        -config : Configuration
        -ecoute_tcp : socket
        -socket_udp : socket
        -sessions : dict[socket, SessionClient]
        -registre : Registre
        -calculateur : CalculateurDensite
        -regulateur : Regulateur
        -signataire : Signataire
        -garde : GardeAntiRejeu
        -acces_bdd : AccesBdd | None
        -en_marche : bool
        +demarrer() None
        +arreter() None
        -accepter_client() None
        -lire_tcp(session: SessionClient) None
        -lire_udp() None
        -traiter(session: SessionClient, message: Message) None
        -retirer_inactifs(maintenant: float) None
        -diffuser_etat() None
    }

    class SessionClient {
        -connexion : socket
        -adresse : tuple[str, int]
        -decoupeur : DecoupeurTrames
        -identifiant : str | None
        -superviseur : bool
        -derniere_activite : float
        +envoyer(octets: bytes) None
        +fermer() None
    }

    class Registre {
        -usagers : dict[str, Usager]
        +ajouter(usager: Usager) None
        +retirer(identifiant: str) Usager
        +obtenir(identifiant: str) Usager
        +usagers_sur_branche(branche: str) list[Usager]
        +usagers_sur_segment(segment: str) list[Usager]
    }

    class NiveauDensite {
        <<enumeration>>
        FAIBLE
        MOYENNE
        FORTE
    }

    class CalculateurDensite {
        -rond_point : RondPoint
        +calculer(registre: Registre) dict[str, float]
        +niveau(densite: float) NiveauDensite$
    }

    class Regulateur {
        -rond_point : RondPoint
        -active : bool
        -vp_actif : str | None
        -segments_reserves : set[str]
        -entrees_bloquees : set[str]
        -consignes_envoyees : dict[str, CodeNotification]
        +signaler_vp(identifiant: str, entree: str, sortie: str) None
        +terminer_vp(identifiant: str) None
        +decider(registre: Registre, densites: dict[str, float]) list[Notification]
    }

    class Notification {
        <<dataclass>>
        +destinataire : str
        +code : CodeNotification
        +texte : str
        +vers_message() Message
    }

    Serveur "1" *-- "0..*" SessionClient
    Serveur *-- Registre
    Serveur *-- CalculateurDensite
    Serveur *-- Regulateur
    Serveur --> AccesBdd
    SessionClient *-- DecoupeurTrames
    Registre "1" o-- "0..*" Usager
    CalculateurDensite --> RondPoint
    CalculateurDensite ..> NiveauDensite
    Regulateur --> RondPoint
    Regulateur ..> Notification : produit
```

- `Serveur` fait tourner une seule boucle `select` sur la socket d'écoute TCP, la socket UDP et les sockets des clients. Chaque connexion TCP a sa `SessionClient`, avec son propre tampon de trames.
- Une session devient usager au HELLO (`identifiant` renseigné) ou superviseur à l'ABONNEMENT. Un POS reçu en UDP n'est accepté que si son identifiant correspond à une session active.
- `Regulateur.decider()` est appelé à chaque tour de boucle. Il compare la situation (VP actif ou non, densités, position des usagers) aux consignes déjà envoyées et ne renvoie que les nouvelles notifications. Quand la régulation est désactivée, il ne renvoie rien.
- `CalculateurDensite.niveau()` applique les seuils du cahier des charges : faible en dessous de 0,4, moyenne en dessous de 0,7, forte au-delà.

Setters prévus : `SessionClient.identifiant`, `SessionClient.superviseur`, `SessionClient.derniere_activite` et `Regulateur.active` (message REGLAGE).

## Paquet `client`

```mermaid
classDiagram
    class Thread
    class ClientUsager {
        -config : Configuration
        -usager : Usager
        -trajectoire : Trajectoire
        -avancement : float
        -connexion : socket | None
        -socket_udp : socket
        -decoupeur : DecoupeurTrames
        -signataire : Signataire
        -garde : GardeAntiRejeu
        -actif : bool
        +run() None
        +arreter() None
        -connecter() None
        -envoyer(message: Message) None
        -envoyer_position() None
        -avancer(duree: float) None
        -traiter(message: Message) None
    }

    Thread <|-- ClientUsager
    ClientUsager *-- Usager
    ClientUsager *-- Trajectoire
    ClientUsager *-- DecoupeurTrames
```

- Chaque `ClientUsager` est un `threading.Thread` avec ses propres sockets. `run()` enchaîne : connexion et HELLO, puis, à chaque pas, déplacement, envoi du POS en UDP, PING toutes les 2 s et lecture des notifications.
- `connecter()` réessaie après une coupure avec un délai qui double (1, 2, 4, 8 s, plafonné à 10 s) et renvoie un HELLO à chaque reconnexion.
- Un client de catégorie `vp` envoie VP_ALERT à son arrivée et VP_FIN à sa sortie du rond-point.

Setters prévus : aucun, `avancement` n'est modifié que par le client lui-même.

## Paquets `ihm` et `bdd`

```mermaid
classDiagram
    class QMainWindow
    class QGraphicsScene
    class QThread
    class QWidget

    class FenetreSupervision {
        -scene : SceneRondPoint
        -thread_reseau : ThreadReseau
        -panneau_creation : PanneauCreation
        -panneau_stats : PanneauStats
        -interrupteur_regulation : QCheckBox
        -afficher_etat(etat: dict) None
        -basculer_regulation(active: bool) None
        #closeEvent(evenement: QCloseEvent) None
    }

    class SceneRondPoint {
        -rond_point : RondPoint
        -marqueurs : dict[str, QGraphicsEllipseItem]
        +mettre_a_jour(usagers: list[dict], entrees_bloquees: list[str]) None
        -dessiner_rond_point() None
    }

    class ThreadReseau {
        +etat_recu : pyqtSignal~dict~
        +connexion_perdue : pyqtSignal~str~
        -config : Configuration
        -actif : bool
        +run() None
        +demander_reglage(regulation: bool) None
        +arreter() None
    }

    class PanneauCreation {
        -config : Configuration
        -clients : list[ClientUsager]
        -choix_categorie : QComboBox
        -choix_entree : QComboBox
        -choix_sortie : QComboBox
        -creer_usager() None
        +arreter_clients() None
    }

    class PanneauStats {
        -acces_bdd : AccesBdd
        -graphe_temps_vp : PlotWidget
        -graphe_densite : PlotWidget
        +rafraichir() None
    }

    class AccesBdd {
        -parametres : dict[str, str]
        -connexion : MySQLConnection | None
        +connecter() None
        +fermer() None
        +enregistrer_passage_vp(passage: dict) None
        +enregistrer_densites(instantanes: list[tuple]) None
        +enregistrer_evenement(identifiant: str, categorie: str, evenement: str) None
        +lire_passages_vp() list[dict]
        +lire_densites() list[dict]
    }

    QMainWindow <|-- FenetreSupervision
    QGraphicsScene <|-- SceneRondPoint
    QThread <|-- ThreadReseau
    QWidget <|-- PanneauCreation
    QWidget <|-- PanneauStats
    FenetreSupervision *-- SceneRondPoint
    FenetreSupervision *-- ThreadReseau
    FenetreSupervision *-- PanneauCreation
    FenetreSupervision *-- PanneauStats
    PanneauCreation "1" *-- "0..*" ClientUsager
    PanneauStats --> AccesBdd
```

- `ThreadReseau` ne touche aucun widget. Il reçoit les STATE et émet `etat_recu` ; c'est `FenetreSupervision`, dans le thread graphique, qui met la scène à jour dans `afficher_etat()`.
- `closeEvent()` redéfinit la méthode protégée de Qt pour arrêter proprement le thread réseau et les clients lancés avant de fermer la fenêtre.
- `PanneauCreation` lance un `ClientUsager` local pour la catégorie, l'entrée et la sortie choisies. Ce client se connecte au serveur comme n'importe quel autre.
- `AccesBdd` utilise des requêtes paramétrées et `executemany` pour les instantanés de densité. Le serveur est le seul à écrire ; `PanneauStats` ne fait que lire.

Setters prévus : aucun.
