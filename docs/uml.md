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
    class InscriptionRefuseeError {
        -reessayer : bool
    }

    Exception <|-- CherryPieError
    CherryPieError <|-- ConfigurationInvalideError
    CherryPieError <|-- TrameInvalideError
    CherryPieError <|-- SignatureInvalideError
    CherryPieError <|-- RejeuDetecteError
    CherryPieError <|-- BrancheInconnueError
    CherryPieError <|-- UsagerInconnuError
    CherryPieError <|-- InscriptionRefuseeError
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
        -branches : list[ParametresBranche]
        -rayon : float
        -largeur_voie_anneau : float
        -largeur_chaussee : float
        -longueur_branche : float
        -capacite_par_branche : int
        -parametres_bdd : dict[str, str | int]
        +depuis_fichier(chemin: str | Path) Configuration$
    }

    class ParametresBranche {
        <<dataclass>>
        +nom : str
        +libelle : str
        +cap : float
        +terre_plein : float
        +passage_pieton : float
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
    Configuration "1" *-- "3..*" ParametresBranche
    Signataire ..> Enveloppe : crée et vérifie
    GardeAntiRejeu ..> Enveloppe : contrôle
```

- `Enveloppe` est la forme transmise sur le réseau : le `Message`, plus l'horodatage, le nonce et le HMAC. `Signataire.signer()` la construit ; à la réception, `Signataire.verifier()` puis `GardeAntiRejeu.controler()` la valident.
- `ParametresBranche` décrit une branche telle que la donne sa section `[branche.<identifiant>]` de `config.ini` : identifiant (celui du protocole), libellé affiché, cap depuis le nord, largeur du terre-plein et distance du passage piéton. La configuration refuse un identifiant qui n'est pas en minuscules sans accents, une section sans branche, deux branches au même cap, ou une voie d'anneau plus large que le rayon.
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
        +DISTANCE_SECURITE : float$
        -identifiant : str
        -branche_entree : str
        -branche_sortie : str
        -position : Position | None
        -cap : float | None
        -vitesse : float
        -segment : str | None
        -etape : Etape
        -consigne : CodeNotification | None
        +reagir(code: CodeNotification) bool
        +vitesse_autorisee() float
        +se_range() bool
        +verifier_cap(valeur: object) float$
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
        +calculer_trajectoire(rond_point: RondPoint) Trajectoire
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
| `VehiculePrioritaire` | `vp` | 11,1 m/s (40 km/h) | aucune, c'est lui qu'on laisse passer | approche, anneau sur la voie intérieure, sortie |

- `vitesse_autorisee()` et `se_range()` traduisent la consigne en cours : vitesse réduite de moitié pour `DEGAGEZ`, et rangement sur la droite pour `DEGAGEZ` et `CHANGEZ_VOIE`. La place disponible dépend de l'endroit (bord de la chaussée sur une branche, voie extérieure sur l'anneau) : c'est la trajectoire qui la donne, et le déplacement qui l'applique. `ATTENDEZ` ne change pas la vitesse : l'usager avance jusqu'à la ligne d'entrée de sa trajectoire et s'y arrête. `OK_PASSER` lève la consigne.
- `Pieton` redéfinit `calculer_trajectoire()` : il ne prend pas l'anneau, il traverse une seule branche, qui est à la fois son entrée et sa sortie. `VehiculePrioritaire` la redéfinit aussi, pour rester sur la voie intérieure de l'anneau.
- Le cap est la direction de marche, en degrés depuis le nord. `verifier_cap()` sert au setter et au serveur, qui contrôle le cap d'un POS avant de modifier l'usager.
- `depuis_dict()` instancie la bonne sous-classe d'après la catégorie reçue dans le HELLO.
- `Position` a son propre module (`modele/position.py`), partagé par les usagers, le rond-point et les trajectoires. Elle refuse les coordonnées infinies ou NaN.

Setters : `Usager.position`, `Usager.cap` (entre 0 et 360), `Usager.vitesse` (entre 0 et la vitesse maximale de la catégorie), `Usager.segment` et `Usager.etape`, mis à jour par le client quand il avance et par le serveur à chaque POS reçu. L'étape vaut `APPROCHE` tant que l'usager n'a pas bougé.

### Rond-point

```mermaid
classDiagram
    class RondPoint {
        -rayon : float
        -largeur_voie_anneau : float
        -longueur_branche : float
        -branches : list[Branche]
        -segments : list[Segment]
        +rayon_voie_interieure() float
        +rayon_voie_exterieure() float
        +rayon_ilot() float
        +rayon_bord() float
        +branche(nom: str) Branche
        +ecart_raccord(branche: Branche) float
        +segments_entre(entree: str, sortie: str) list[Segment]
        +depuis_config(config: Configuration) RondPoint$
        -segment_partant_de(branche: Branche) Segment
    }

    class Branche {
        -nom : str
        -libelle : str
        -cap : float
        -capacite : int
        -terre_plein : float
        -passage_pieton : float
        -largeur_chaussee : float
        +angle() float
        +decalage_voie() float
        +demi_largeur() float
        +point(distance_au_centre: float, decalage: float) Position
    }

    class Segment {
        -depart : Branche
        -arrivee : Branche
        -longueur : float
        +ouverture() float
        +nom() str
    }

    RondPoint "1" *-- "3..*" Branche
    RondPoint "1" *-- "3..*" Segment
    Segment --> "2" Branche
    Branche ..> ParametresBranche : construite d'après
```

- `RondPoint` crée ses branches et ses segments à partir de la configuration, et ils n'existent pas sans lui : composition. La géométrie de Bel Air est décrite dans [geometrie_bel_air.md](geometrie_bel_air.md).
- Chaque branche est placée à son cap ; `angle` le convertit en angle du repère (90° moins le cap). Elle a deux chaussées d'une voie, de part et d'autre d'un terre-plein : `decalage_voie` est l'écart entre l'axe et le milieu de chaque chaussée, `demi_largeur` l'écart jusqu'à leur bord extérieur. La chaussée d'entrée est à droite d'un usager qui arrive.
- L'anneau a deux voies de même largeur, séparées par son axe (`rayon`). `ecart_raccord()` donne l'angle entre l'axe d'une branche et le milieu de ses chaussées au bord de l'anneau : on entre un peu après l'axe, on sort un peu avant.
- Les segments suivent le sens de circulation, quel que soit l'ordre des branches dans la configuration. Pour Bel Air, `segments_entre("nations_sud", "nations_nord")` renvoie `nations_sud-jean_de_la_bruyere` puis `jean_de_la_bruyere-nations_nord`. Si l'entrée et la sortie sont la même branche, l'usager fait le tour complet.
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
        +place_a_droite : float
        +longueur() float
        +segment() None
        +position_a(distance: float, decalage: float) Position
        +cap_a(distance: float) float
    }

    class TronconArc {
        <<dataclass>>
        +segment : Segment
        +angle_debut : float
        +angle_fin : float
        +rayon_debut : float
        +rayon_fin : float
        +place_a_droite : float
        +etape() Etape
        +longueur() float
        +position_a(distance: float, decalage: float) Position
        +cap_a(distance: float) float
    }

    class Trajectoire {
        -troncons : list[TronconDroit | TronconArc]
        +longueur() float
        +longueur_approche() float
        +segments() list[Segment]
        +pour_vehicule(rond_point: RondPoint, entree: str, sortie: str, prioritaire: bool) Trajectoire$
        +pour_pieton(rond_point: RondPoint, branche: str) Trajectoire$
        +position_a(avancement: float, decalage: float) Position
        +cap_a(avancement: float) float
        +etape_a(avancement: float) Etape
        +segment_a(avancement: float) Segment | None
        +place_a_droite_a(avancement: float) float
        +passe_par(segment: Segment) bool
        -troncon_a(avancement: float) tuple
        -place_sur_la_chaussee(branche: Branche) float$
        -arcs(rond_point: RondPoint, entree: Branche, sortie: Branche, prioritaire: bool) list[TronconArc]$
        -decouper(chemin: list, limites: list, segments: list, rayon_exterieur: float) list[TronconArc]$
    }

    Trajectoire "1" *-- "1..*" TronconDroit
    Trajectoire "1" *-- "0..*" TronconArc
    TronconArc o-- Segment
    TronconDroit --> Etape
    TronconDroit ..> Position : calcule
    TronconArc ..> Position : calcule
```

- Une trajectoire est une suite de tronçons parcourus l'un après l'autre : des tronçons droits sur les chaussées des branches (approche, sortie, passage piéton) et des morceaux d'arc sur l'anneau. Les deux types de tronçons offrent les mêmes membres (`etape`, `longueur`, `segment`, `place_a_droite`, `position_a()`, `cap_a()`) : la trajectoire trouve le tronçon qui correspond à l'avancement et lui délègue le calcul.
- Un véhicule approche sur la chaussée d'entrée, depuis le bout de la branche jusqu'au bord de l'anneau : c'est la ligne d'entrée, où il s'arrête s'il doit attendre (`longueur_approche`). Il repart sur la chaussée de sortie de sa branche de sortie.
- Sur l'anneau, `arcs()` décrit le chemin par des points (angle, distance au centre) : raccord depuis la chaussée d'entrée, voie suivie, changement de voie éventuel, raccord vers la chaussée de sortie. Un véhicule qui sort à la première sortie suit la voie extérieure ; les autres suivent la voie intérieure jusqu'au segment qui mène à leur sortie, où ils se rabattent sur la voie extérieure ; le VP reste sur la voie intérieure. `decouper()` coupe ce chemin aux limites des segments, et découpe finement les transitions pour que l'usager y avance à vitesse régulière.
- `place_a_droite` est l'écart qu'un usager peut prendre pour se ranger : le bord de sa chaussée sur une branche, la largeur d'une voie sur la voie intérieure, rien sur la voie extérieure.
- Un piéton parcourt 4 m de trottoir jusqu'au bord de la chaussée d'entrée, traverse les deux chaussées et le terre-plein sur le passage piéton, puis repart sur le trottoir d'en face : il croise l'approche et la sortie des véhicules de cette branche.
- Le décalage latéral se compte vers la droite du sens de marche ; sur l'anneau, c'est l'extérieur. Le cap se compte depuis le nord, dans le sens des aiguilles d'une montre ; `cap_de_la_direction()` convertit une direction du repère en cap.
- Un point situé pile à la jonction de deux tronçons appartient au premier : un usager arrêté sur la ligne d'entrée est encore en approche.
- Les arcs ne font que référencer les segments du rond-point, sans les posséder : agrégation.

Setters : aucun, une trajectoire ne change plus une fois calculée.

## Paquet `serveur`

### Boucle réseau et logique

```mermaid
classDiagram
    class Serveur {
        -config : Configuration
        -logique : LogiqueServeur
        -signataire : Signataire
        -garde : GardeAntiRejeu
        -arret : threading.Event
        -ecoute_tcp : socket | None
        -socket_udp : socket | None
        -connexions : dict[int, Connexion]
        +demarrer() None
        +servir() None
        +arreter() None
        -attendre_et_traiter(attente: float) None
        -cadencer() None
        -accepter() None
        -lire_tcp(numero: int) None
        -traiter_trame(numero: int, trame: bytes) None
        -lire_udp() None
        -ouvrir(octets: bytes) Message
        -envoyer(numero: int, message: Message) None
        -vider(numero: int) None
        -fermer(numero: int, raison: str) None
    }

    class Connexion {
        -socket : socket
        -adresse : tuple[str, int]
        -decoupeur : DecoupeurTrames
        -a_envoyer : bytearray
        +recevoir() list[bytes]
        +envoyer(trame: bytes) None
        +vider() None
        +fermer() None
    }

    class LogiqueServeur {
        -rond_point : RondPoint
        -timeout_client : float
        -calculateur : CalculateurDensite
        -circulation : Circulation
        -regulateur : Regulateur
        -registre : Registre
        -sessions : dict[int, Session]
        -total_sessions : int
        -passages_en_cours : dict[str, PassageEnCours]
        -passages : list[PassageVp]
        +regulation_active() bool
        +vp_actif() bool
        +segments_reserves() list[str]
        +ouvrir_session(maintenant: float) int
        +fermer_session(numero: int) Usager | None
        +traiter_tcp(numero: int, message: Message, maintenant: float) Reponse
        +traiter_udp(message: Message, maintenant: float) None
        +sessions_expirees(maintenant: float) list[int]
        +superviseurs() list[int]
        +cadencer() list[tuple[int, Message]]
        +construire_etat() Message
        -signaler_vp(session: Session, message: Message) Reponse
        -terminer_vp(session: Session, maintenant: float) Reponse
        -regler(session: Session, message: Message) Reponse
    }

    class Reponse {
        <<dataclass>>
        +messages : tuple[Message, ...]
        +fermer : bool
    }

    class Session {
        -numero : int
        -identifiant : str | None
        -superviseur : bool
        -derniere_activite : float
        +est_expiree(maintenant: float, delai: float) bool
    }

    class Registre {
        -usagers : dict[str, Usager]
        +contient(identifiant: str) bool
        +ajouter(usager: Usager) None
        +obtenir(identifiant: str) Usager
        +retirer(identifiant: str) Usager
    }

    Serveur *-- LogiqueServeur
    Serveur "1" *-- "0..*" Connexion
    Connexion *-- DecoupeurTrames
    LogiqueServeur *-- Registre
    LogiqueServeur "1" *-- "0..*" Session
    LogiqueServeur ..> Reponse : renvoie
    LogiqueServeur --> RondPoint
    LogiqueServeur *-- CalculateurDensite
    LogiqueServeur *-- Circulation
    LogiqueServeur *-- Regulateur
    LogiqueServeur "1" *-- "0..*" PassageEnCours
    LogiqueServeur "1" *-- "0..*" PassageVp
    Registre "1" o-- "0..*" Usager
```

- La boucle réseau et la logique sont séparées. `Serveur` ne décide rien ; `LogiqueServeur` ne touche aucune socket, ce qui permet de la tester sans réseau. Elles se parlent par numéro de session : la boucle associe chaque numéro à une `Connexion` (la socket et ses tampons), la logique à une `Session` (usager, abonnement, dernière activité).
- `servir()` fait tourner une seule boucle `select` sur la socket d'écoute TCP, la socket UDP et les sockets des clients. Son délai d'attente court jusqu'à la prochaine cadence (`intervalle_etat`) : à chaque cadence, `cadencer()` ferme les sessions silencieuses et envoie le STATE aux supervisions. `arreter()` lève un `threading.Event` vérifié à chaque tour, ce qui arrête la boucle en moins d'un intervalle.
- Chaque trame reçue passe par `ouvrir()` (enveloppe, HMAC, anti-rejeu) avant d'être confiée à la logique. Une trame refusée est journalisée puis ignorée.
- `Connexion` utilise une socket non bloquante. Son découpeur recolle les trames reçues en plusieurs morceaux ou collées ensemble, et sa file d'envoi garde ce que la socket n'a pas pu accepter, jusqu'à ce que `select` la signale prête à écrire. Un client qui laisse plus de 1 Mio en attente est déconnecté.
- Aux frontières, une erreur imprévue sur une session ne ferme que cette session ; ailleurs dans la boucle, elle est journalisée et la boucle continue.

Setters : `Session.identifiant` (une seule fois, au HELLO), `Session.superviseur` (à l'ABONNEMENT) et `Session.derniere_activite` (à chaque message reçu, jamais en arrière).

### Densité et véhicules prioritaires

```mermaid
classDiagram
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

    class PassageEnCours {
        -identifiant : str
        -entree : str
        -sortie : str
        -segments_reserves : tuple[str, ...]
        -annonce : float
        -debut : datetime
        -regulation : bool
        -entree_anneau : float | None
        -releves_densite : list[float]
        +sur_l_anneau() bool
        +noter_etape(etape: Etape, maintenant: float) None
        +noter_densite(densite_moyenne: float) None
        +terminer(maintenant: float) PassageVp
    }

    class PassageVp {
        <<dataclass>>
        +identifiant : str
        +entree : str
        +sortie : str
        +debut : datetime
        +fin : datetime
        +duree : float
        +duree_anneau : float | None
        +regulation : bool
        +densite_moyenne : float
    }

    CalculateurDensite ..> NiveauDensite
    CalculateurDensite ..> Registre : lit
    PassageEnCours ..> PassageVp : produit
```

- `CalculateurDensite` compte, pour chaque branche, les usagers en approche sur cette branche (ceux qui roulent vers l'anneau ou attendent d'y entrer) et divise par sa capacité, en bornant à 1. `niveau()` applique les seuils du cahier des charges : faible en dessous de 0,4, moyenne en dessous de 0,7, forte au-delà.
- Un VP_ALERT crée un `PassageEnCours`, qui réserve les segments de la trajectoire du VP et démarre le chronomètre, en notant le mode de régulation en vigueur. Le premier POS du VP sur l'anneau note son entrée sur l'anneau, et `cadencer()` relève la densité moyenne des branches à chaque cadence. Le VP_FIN produit un `PassageVp`, une mesure figée (durée de l'annonce au VP_FIN, durée sur l'anneau seule) que `LogiqueServeur.passages` conserve pour l'enregistrement en base.
- `cadencer()` regroupe ce que la logique fait à chaque cadence : relevés de densité, puis un STATE par supervision. La boucle réseau n'a plus qu'à envoyer ce qu'elle renvoie.

### Ce que voit chaque conducteur

```mermaid
classDiagram
    class Vue {
        <<dataclass>>
        +distance : float | None
        +ceder : bool
    }

    class Chaussee {
        <<enumeration>>
        ENTREE
        SORTIE
    }

    class Circulation {
        -rond_point : RondPoint
        -tour_d_entree : str | None
        +voir(registre: Registre, prioritaires: frozenset[str]) dict[str, Vue]
        +passages_fermes(registre: Registre) set[tuple[str, Chaussee]]
        -devant(rang: int, vehicules: list[Usager], passages_fermes: set, prioritaire: bool) list[float]
        -devant_sur_la_branche(...) list[float]
        -devant_sur_l_anneau(...) list[float]
        -devant_sur_le_passage(rang: int, pietons: list[Usager]) list[float]
        -donner_le_tour(vehicules: list[Usager], distances: dict, prioritaires: frozenset[str]) str | None
        -peut_entrer(vehicule: Usager, distance: float | None, vehicules: list[Usager]) bool
        -reste_avant_la_ligne(vehicule: Usager) float
        -dans_sa_zone_d_entree(vehicule: Usager) bool
        -anneau_libre(branche: Branche, vehicules: list[Usager]) bool
        -sur_la_voie(rayon_de_voie: float, autre: Usager) bool
        -range(usager: Usager, sortie: Branche) bool
    }

    Circulation ..> Vue : produit
    Circulation ..> Chaussee : ferme
    Circulation ..> Registre : lit
```

- Chaque client roule sans voir les autres. `Circulation.voir()` calcule, pour chaque véhicule dont la position est connue, la distance jusqu'à l'obstacle le plus proche devant lui sur sa voie (autre véhicule ou piéton sur le passage) et s'il doit céder le passage. `cadencer()` l'envoie à chaque véhicule dans un message DEVANT, que la régulation soit active ou non : c'est la simulation de ce que voit un conducteur, pas une consigne.
- Sur une chaussée de branche, deux véhicules sont sur la même file si leurs écarts à l'axe diffèrent de moins d'un mètre : un usager rangé sur le bord ne gêne pas ceux qui roulent au milieu. Sur l'anneau, deux véhicules sont sur la même voie si leurs distances au centre diffèrent de moins d'une demi-largeur de voie.
- Le cédez-le-passage demande 15 m libres en amont et 10 m en aval du point d'entrée, sur les deux voies, puisque l'usager qui entre traverse la voie extérieure. Ces marges empêchent l'anneau de se bloquer en boucle.
- Les entrées se font une par une. `donner_le_tour()` accorde l'entrée à un seul véhicule proche de sa ligne, qui la garde pendant qu'il rejoint l'anneau ; c'est le seul état que `Circulation` retient d'une cadence à l'autre (`tour_d_entree`).
- `prioritaires` désigne les VP annoncés quand la régulation est active : ils entrent sans attendre leur tour et ne regardent que la voie intérieure.
- `passages_fermes()` donne les demi-chaussées où marche un piéton : seules celles-là bloquent les véhicules, et le STATE les transmet à la supervision. Un piéton voit le piéton qui le précède sur le passage, pour ne pas lui marcher dessus.

### Régulation

```mermaid
classDiagram
    class Regulateur {
        -rond_point : RondPoint
        -active : bool
        -consignes_envoyees : dict[str, CodeNotification]
        -entrees_bloquees : set[str]
        +decider(registre: Registre, passages: list[PassageEnCours], densites: dict[str, float]) list[Notification]
        +oublier(identifiant: str) None
        -consigne_voulue(usager: Usager, ...) tuple | None
        -consigne_de_dosage(usager: Usager, branche_temporisee: str | None) tuple | None$
        -branche_a_temporiser(densites: dict[str, float]) str | None$
        -changement(identifiant: str, voulue: tuple | None) Notification | None
        -tout_liberer() list[Notification]
        -chemin_restant(usager: Usager) list[str]
        -segments_devant(vp: Usager, passage: PassageEnCours) set[str]$
    }

    class Notification {
        <<dataclass>>
        +destinataire : str
        +code : CodeNotification
        +texte : str
        +vers_message(emetteur: str) Message
    }

    Regulateur ..> Notification : produit
    Regulateur ..> PassageEnCours : lit
    Regulateur ..> CalculateurDensite : niveaux
```

- `Regulateur.decider()` est appelé à chaque cadence par `cadencer()`. Il calcule la consigne voulue pour chaque usager, la compare à celle déjà envoyée (`consignes_envoyees`) et ne renvoie que les changements ; un usager libéré reçoit OK_PASSER.
- Autour d'un VP : DEGAGEZ pour qui est ou va passer sur un segment réservé devant le VP, CHANGEZ_VOIE pour la file sur la branche d'entrée du VP, ATTENDEZ pour qui entrerait sur un segment réservé, et ATTENDEZ pour les piétons devant les passages de l'entrée et de la sortie du VP. Sans VP, le dosage temporise la moins chargée des entrées occupées quand une branche est en densité forte.
- `oublier()` est appelé à la fermeture d'une session : après une reconnexion, la consigne qui vaut encore est renvoyée.
- Régulation coupée (`active` à False, message REGLAGE), `decider()` lève une fois les consignes en cours puis ne renvoie plus rien.

Setters : `Regulateur.active` (message REGLAGE).

## Paquet `client`

```mermaid
classDiagram
    class Thread

    class EtatConnexion {
        <<enumeration>>
        CONNEXION
        CONNECTE
        DECONNECTE
        TERMINE
    }

    class ClientUsager {
        -config : Configuration
        -deplacement : Deplacement
        -signataire : Signataire
        -garde : GardeAntiRejeu
        -arret : threading.Event
        -socket_tcp : socket | None
        -socket_udp : socket | None
        -decoupeur : DecoupeurTrames
        -recus : deque[Message]
        -etat : EtatConnexion
        -vp_annonce : bool
        -sur_position : Callable | None
        -sur_notification : Callable | None
        -sur_connexion : Callable | None
        +run() None
        +arreter() None
        -rouler() str
        -connecter() None
        -circuler() None
        -faire_un_pas() None
        -annoncer_vp() None
        -traiter(message: Message) None
        -voir_devant(message: Message) None
        -attendre(type_attendu: TypeMessage) Message
        -lire(attente: float) bool
        -envoyer(message: Message) None
        -changer_etat(etat: EtatConnexion, detail: str) None
    }

    class Deplacement {
        -usager : Usager
        -trajectoire : Trajectoire
        -avancement : float
        -limite : float | None
        -ceder : bool
        -decalage : float
        +termine() bool
        +noter_devant(distance: float | None, ceder: bool) None
        +avancer(duree: float) None
        -doit_s_arreter_a_la_ligne() bool
        -vitesse_permise() float
        -decalage_voulu() float
        -decaler(duree: float) None
        -placer_usager(vitesse: float) None
    }

    Thread <|-- ClientUsager
    ClientUsager *-- Deplacement
    ClientUsager ..> EtatConnexion : signale
    ClientUsager *-- DecoupeurTrames
    Deplacement --> Usager
    Deplacement --> Trajectoire
```

- Chaque `ClientUsager` est un `threading.Thread` avec ses propres sockets. Il ne dépend pas de Qt : il signale sa position, les consignes reçues et l'état de sa connexion par trois fonctions de rappel, appelées depuis son thread. L'IHM les relie à des signaux Qt par un `RelaisClient`, sans que le client touche jamais un widget. La position est transmise sous forme de copie (`Usager.vers_dict()`), jamais par l'objet partagé.
- `rouler()` enchaîne les connexions. Après une coupure, ou un refus provisoire (`InscriptionRefuseeError.reessayer`), il attend avec un délai qui double (1, 2, 4, 8 s, plafonné à 10 s). L'attente se fait sur un `threading.Event` : `arreter()` réveille le client sans attendre la fin du délai. Un refus définitif l'arrête.
- `circuler()` fait avancer l'usager d'un pas à chaque intervalle de position, envoie le POS en UDP, envoie un PING toutes les `intervalle_ping` secondes et traite les messages reçus. Elle s'arrête si le serveur reste muet plus de `timeout_client` secondes, et dit au revoir (BYE) à la fin du trajet ou à l'arrêt.
- Les messages lus attendent dans une file (`recus`) : une NOTIF arrivée dans la même lecture que le HELLO_ACK n'est pas perdue.
- `Deplacement` contient les règles de mouvement, sans réseau, ce qui permet de les tester seules. À chaque pas, l'usager parcourt la distance que permet sa consigne et s'arrête sur la ligne d'entrée pendant un ATTENDEZ ou un cédez-le-passage s'il ne l'a pas encore franchie. Pour se ranger, il se décale progressivement (2 m/s) jusqu'à la place que donne sa trajectoire ; pendant un DEGAGEZ, il ne ralentit qu'une fois rangé, pour ne pas boucher la voie qu'il libère. Chaque pas met à jour sa position, son cap, sa vitesse, son segment et son étape. `noter_devant()` fixe l'avancement à ne pas dépasser pour garder sa distance de sécurité avec l'obstacle de devant (`Usager.DISTANCE_SECURITE` : 6 m pour un véhicule, 1,5 m pour un piéton) ; l'usager ne recule jamais.
- Un client de VP envoie VP_ALERT à chaque connexion tant que le VP n'a pas quitté l'anneau, avec son `eta` (le temps qu'il lui faut pour atteindre l'anneau), puis VP_FIN au pas où il passe en étape de sortie.

Setters prévus : aucun.

## Paquet `ihm`

```mermaid
classDiagram
    class QMainWindow
    class QGraphicsScene
    class QGraphicsView
    class QGraphicsPathItem
    class QSplitter
    class QGroupBox
    class QObject
    class QThread

    class FenetreSupervision {
        -config : Configuration
        -scene : SceneRondPoint
        -vue : VueRondPoint
        -legende : Legende
        -panneau_creation : PanneauCreation
        -etat_connexion : QLabel
        -indicateur_regulation : QLabel
        -indicateur_vp : QLabel
        -case_regulation : QCheckBox
        -consignes : QListWidget
        -onglets : QTabWidget
        -case_a_aligner : bool
        -fil : QThread
        -reseau : ReseauSupervision
        +demarrer() None
        +arreter() None
        #closeEvent(evenement: QCloseEvent) None
        -afficher_etat(etat: dict) None
        -noter_connexion(etat: str, detail: str) None
        -regler(coche: bool) None
        -noter_consigne(identifiant: str, code: str, texte: str, appliquee: bool) None
        -colorer(etiquette: QLabel, texte: str, couleur: QColor) None$
        -relier() None
        -disposer() None
    }

    class SceneRondPoint {
        -rond_point : RondPoint
        -libelles : dict[str, str]
        -bandes_densite : dict[str, QGraphicsLineItem]
        -textes_densite : dict[str, QGraphicsTextItem]
        -arcs_reserves : dict[str, QGraphicsPathItem]
        -entrees_temporisees : dict[str, QGraphicsItemGroup]
        -passages_fermes : dict[tuple[str, str], QGraphicsLineItem]
        -marqueurs : dict[str, MarqueurUsager]
        +vers_scene(position: Position) QPointF$
        +afficher_etat(etat: dict) None
        -afficher_usagers(usagers: list[dict]) None
        -afficher_densite(nom: str, densite: float) None
        -dessiner_branche(branche: Branche) None
        -dessiner_anneau() None
        -dessiner_passage_pieton(branche: Branche) None
        -dessiner_densite(branche: Branche) None
        -dessiner_feu_entree(branche: Branche) None
        -dessiner_arc_reserve(segment: Segment) None
        -ajouter_ligne(debut: Position, fin: Position, crayon: QPen) QGraphicsLineItem
        -ecrire(texte: QGraphicsTextItem, contenu: str, branche: Branche) None$
    }

    class MarqueurUsager {
        -categorie : str
        -halo : QGraphicsEllipseItem | None
        +afficher(usager: dict, libelles: dict[str, str]) None
    }

    class VueRondPoint {
        #resizeEvent(evenement: QResizeEvent) None
    }

    class Legende {
        -libelles : list[str]
        -entrees() list[tuple]
        -entree(dessin: Callable, libelle: str) QWidget$
        -silhouette(categorie: str, contour: QColor, epaisseur: int) Callable$
        -bande(couleur: QColor, proportion: float) Callable$
    }

    class ReseauSupervision {
        +etat_recu : pyqtSignal$
        +connexion_changee : pyqtSignal$
        +termine : pyqtSignal$
        -config : Configuration
        -signataire : Signataire
        -garde : GardeAntiRejeu
        -arret : threading.Event
        -reglages : SimpleQueue[bool]
        -socket : socket | None
        -decoupeur : DecoupeurTrames
        -etat : EtatConnexion
        +tourner() None
        +demander_reglage(regulation: bool) None
        +arreter() None
        -boucler() None
        -connecter() None
        -ecouter() None
        -lire(attente: float) bool
        -transmettre_etat(message: Message) None
        -ouvrir(octets: bytes) Message
        -envoyer_reglages() None
        -abandonner_reglages() None
        -envoyer(message: Message) None
        -fermer() None
        -changer_etat(etat: EtatConnexion, detail: str) None
    }

    class PanneauCreation {
        +notification_recue : pyqtSignal$
        -config : Configuration
        -clients : list[ClientUsager]
        -libelles : dict[str, str]
        -lignes : dict[str, QTreeWidgetItem]
        -compteurs : dict[str, int]
        -choix_categorie : QComboBox
        -choix_entree : QComboBox
        -choix_sortie : QComboBox
        -choix_nombre : QSpinBox
        -bouton_lancer : QPushButton
        -liste_clients : QTreeWidget
        +lancer() list[ClientUsager]
        +arreter_clients(delai: float) None
        -lancer_un(categorie: str, entree: str, sortie: str) ClientUsager
        -noter_position(identifiant: str, usager: dict) None
        -noter_connexion(identifiant: str, etat: str, detail: str) None
        -adapter_sortie() None
        -disposer() None
    }

    class RelaisClient {
        +position_changee : pyqtSignal$
        +notification_recue : pyqtSignal$
        +connexion_changee : pyqtSignal$
        -identifiant : str
        +sur_position(usager: dict) None
        +sur_notification(code: CodeNotification, texte: str, appliquee: bool) None
        +sur_connexion(etat: EtatConnexion, detail: str) None
    }

    QMainWindow <|-- FenetreSupervision
    QGraphicsScene <|-- SceneRondPoint
    QGraphicsView <|-- VueRondPoint
    QGraphicsPathItem <|-- MarqueurUsager
    QGroupBox <|-- Legende
    QGroupBox <|-- PanneauCreation
    QObject <|-- ReseauSupervision
    QObject <|-- RelaisClient
    FenetreSupervision *-- SceneRondPoint
    FenetreSupervision *-- VueRondPoint
    FenetreSupervision *-- Legende
    FenetreSupervision *-- PanneauCreation
    FenetreSupervision *-- QThread
    FenetreSupervision *-- QSplitter
    FenetreSupervision *-- ReseauSupervision
    VueRondPoint --> SceneRondPoint
    SceneRondPoint "1" *-- "0..*" MarqueurUsager
    SceneRondPoint --> RondPoint
    PanneauCreation "1" *-- "0..*" ClientUsager
    ClientUsager --> RelaisClient : rappels
    RelaisClient ..> PanneauCreation : signaux
    ReseauSupervision ..> FenetreSupervision : signaux
```

- Trois sortes de threads se partagent la supervision : le thread de l'IHM, qui possède tous les widgets ; le `QThread` du réseau, où vit `ReseauSupervision` après `moveToThread()` ; un `threading.Thread` par `ClientUsager` lancé depuis le panneau. Seul le thread de l'IHM touche aux widgets. Les deux autres émettent des signaux, que Qt remet aux objets de l'IHM dans leur thread (connexion en file d'attente).
- Les signaux sont des attributs de classe (`pyqtSignal`), d'où le soulignement. `etat_recu` porte les données d'un STATE (`dict`), `connexion_changee` l'état de la connexion et un détail (`str, str`), `termine` n'a pas d'argument. Les signaux de `RelaisClient` commencent par l'identifiant de l'usager : `position_changee (str, dict)`, `notification_recue (str, str, str, bool)` pour le code, le texte et l'application de la consigne, `connexion_changee (str, str, str)`. `PanneauCreation.notification_recue` relaie ce dernier vers la fenêtre.
- `ReseauSupervision.tourner()` est relié au signal `started` du `QThread`. Comme le client, la boucle se connecte, s'abonne (ABONNEMENT), envoie un PING toutes les `intervalle_ping` secondes et se reconnecte avec le même backoff. Un STATE auquel il manque un champ est journalisé et ignoré, pour ne jamais faire échouer l'affichage.
- Tant que `tourner()` s'exécute, le `QThread` ne revient pas à sa boucle d'événements : un slot appelé en file d'attente n'y serait jamais exécuté. Les réglages demandés par l'IHM passent donc par une `SimpleQueue`, que la boucle vide à chaque tour ; l'attente sur la socket est bornée à 0,1 s pour qu'un réglage ou l'arrêt soit pris en compte vite. Les réglages demandés hors connexion sont abandonnés à la connexion suivante.
- `termine` est relié à `QThread.quit()` en connexion directe : à la fermeture, le thread de l'IHM attend le réseau dans `wait()` et ne traiterait pas un signal en file d'attente.
- `RelaisClient` adapte les rappels du client, qui ne dépend pas de Qt. Créé dans le thread de l'IHM, il émet un signal à chaque rappel. Le client garde ses fonctions de rappel, donc le relais, aussi longtemps qu'il vit.
- `SceneRondPoint` travaille en mètres, comme le modèle, avec l'ordonnée inversée (`vers_scene()`), et ne recalcule rien : elle montre l'état reçu. La chaussée est dessinée une fois d'après le rond-point : deux chaussées par branche avec leur terre-plein, lignes de rive, ligne de cédez-le-passage, passage piéton et refuge, flèches de sens, deux voies sur l'anneau. La voie intérieure des segments réservés et les entrées temporisées (barre sur la ligne et feu) sont posées cachées et rendues visibles d'après le STATE. Le niveau de densité reprend `CalculateurDensite.niveau()`, pour que les seuils restent ceux du serveur. Le cadre de la scène suit le dessin ; `VueRondPoint` le recadre à chaque changement de taille.
- `MarqueurUsager` dessine un usager à son gabarit (`style.py`), tourné selon le cap reçu dans le STATE. L'avant d'un véhicule est sur sa position : arrêté sur la ligne d'entrée, il la touche. Le VP a un halo et une rampe lumineuse.
- La fenêtre place la scène et les panneaux (serveur, légende, création, consignes) de part et d'autre d'un `QSplitter` : la scène prend toute la hauteur, et l'utilisateur peut lui donner plus de largeur.
- `style.py` réunit couleurs, tailles et libellés : la scène et la légende utilisent les mêmes constantes, si bien qu'une couleur changée l'est partout.
- L'interrupteur envoie un REGLAGE sur `clicked`, émis seulement par un clic, jamais par `setChecked()`. Après chaque connexion, la case reprend l'état du serveur au premier STATE ; ensuite, seul l'indicateur suit le serveur. Elle est grisée tant que la supervision n'est pas connectée.
- `closeEvent()` redéfinit la méthode protégée de Qt : il arrête et attend les clients lancés depuis le panneau, puis le réseau, avant de fermer la fenêtre.

Setters prévus : aucun.

## Paquet `bdd` (prévisionnel)

```mermaid
classDiagram
    class QWidget

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

    QWidget <|-- PanneauStats
    PanneauStats --> AccesBdd
```

- `PanneauStats` sera un onglet « Statistiques » de `FenetreSupervision`.
- `AccesBdd` utilise des requêtes paramétrées et `executemany` pour les instantanés de densité. Le serveur est le seul à écrire ; `PanneauStats` ne fait que lire.

Setters prévus : aucun.
