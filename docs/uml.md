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
        -parametres_bdd : dict[str, str]
        +depuis_fichier(chemin: str) Configuration$
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
        +vers_octets() bytes
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
        -calculer_hmac(contenu: dict) str
    }

    class GardeAntiRejeu {
        -fenetre : float
        -nonces_vus : dict[str, float]
        +controler(enveloppe: Enveloppe, maintenant: float) None
        -purger(maintenant: float) None
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
        -position : Position
        -vitesse : float
        -segment : str | None
        -consigne : CodeNotification | None
        +reagir(code: CodeNotification) None
        +vitesse_autorisee() float
        +decalage_lateral() float
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
    Usager *-- Position
```

`Usager.reagir()` enregistre la consigne reçue si elle fait partie de `CONSIGNES_SUIVIES`, et l'ignore sinon. Chaque sous-classe redéfinit ce qui lui est propre :

| Classe | Catégorie | Vitesse max | Consignes suivies |
| --- | --- | --- | --- |
| `Voiture` | `voiture` | 8,3 m/s (30 km/h) | toutes |
| `Moto` | `moto` | 8,3 m/s (30 km/h) | toutes |
| `Trottinette` | `trottinette` | 5,6 m/s (20 km/h) | toutes |
| `Pieton` | `pieton` | 1,4 m/s (5 km/h) | `ATTENDEZ`, `OK_PASSER` |
| `VehiculePrioritaire` | `vp` | 11,1 m/s (40 km/h) | aucune, c'est lui qu'on laisse passer |

Les vitesses sont des valeurs de départ, à régler pendant les essais. `vitesse_autorisee()` et `decalage_lateral()` traduisent la consigne en cours en mouvement : arrêt pour `ATTENDEZ`, ralentissement et décalage pour `DEGAGEZ`, décalage pour `CHANGEZ_VOIE`. `depuis_dict()` instancie la bonne sous-classe d'après la catégorie reçue dans le HELLO.

### Rond-point et trajectoires

```mermaid
classDiagram
    class RondPoint {
        -rayon : float
        -branches : list[Branche]
        -segments : list[Segment]
        +branche(nom: str) Branche
        +segments_entre(entree: str, sortie: str) list[Segment]
        +depuis_config(config: Configuration) RondPoint$
    }

    class Branche {
        -nom : str
        -angle : float
        -capacite : int
    }

    class Segment {
        -depart : Branche
        -arrivee : Branche
        -longueur : float
        +nom() str
    }

    class Trajectoire {
        -entree : Branche
        -sortie : Branche
        -segments : list[Segment]
        -longueur : float
        +calculer(rond_point: RondPoint, entree: str, sortie: str) Trajectoire$
        +position_a(avancement: float, decalage: float) Position
        +segment_a(avancement: float) Segment | None
        +passe_par(segment: Segment) bool
    }

    RondPoint "1" *-- "3..*" Branche
    RondPoint "1" *-- "3..*" Segment
    Segment --> "2" Branche
    Trajectoire o-- "1..*" Segment
    Trajectoire --> "2" Branche
    Trajectoire ..> Position : calcule
```

- `RondPoint` crée ses branches et ses segments à partir de la configuration, et ils n'existent pas sans lui : composition. Une `Trajectoire` ne fait que référencer des segments du rond-point : agrégation.
- Les segments suivent le sens de circulation, inverse des aiguilles d'une montre : avec les branches N, E, S et O, `segments_entre("S", "N")` renvoie S-E puis E-N.
- `position_a()` donne la position d'un usager à partir de la distance déjà parcourue sur sa trajectoire ; le décalage sert à s'écarter quand un véhicule prioritaire arrive.

Setters prévus : `Usager.position`, `Usager.vitesse` et `Usager.segment`, mis à jour par le client quand il avance et par le serveur à chaque POS reçu.
