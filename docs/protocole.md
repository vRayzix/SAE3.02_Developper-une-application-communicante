# Protocole de communication

Ce document décrit les messages échangés entre le serveur du rond-point, les clients usagers et la supervision. Il suit le code de `src/cherrypie/commun/` et doit être mis à jour à chaque changement du protocole.

## Transports

| Transport | Port | Usage |
| --- | --- | --- |
| TCP | 5050 | messages qui doivent arriver : HELLO, HELLO_ACK, VP_ALERT, VP_FIN, BYE, PING, PONG, NOTIF, STATE, ABONNEMENT, REGLAGE, DEVANT, STATS_DEMANDE, STATS_REPONSE |
| UDP | 5051 | positions (POS), environ toutes les 200 ms ; une position perdue est remplacée par la suivante |

Les ports et les délais se règlent dans `config.ini`.

## Découpage des trames TCP

TCP transmet un flux d'octets sans frontières entre les messages : une lecture peut renvoyer une demi-trame, ou plusieurs trames à la suite. Chaque trame est donc précédée de la longueur de sa charge utile.

| Octets | Contenu |
| --- | --- |
| 0 à 3 | longueur `n` de la charge, entier non signé en ordre réseau (`struct.pack("!I", n)`) |
| 4 à 3 + n | enveloppe JSON encodée en UTF-8 |

Le récepteur tient un tampon par socket (`DecoupeurTrames`). Il y accumule les octets reçus et n'en extrait une trame que lorsqu'elle est complète. Une longueur annoncée supérieure à 1 Mio est refusée (`TrameInvalideError`) : le flux ne peut plus être resynchronisé et la connexion doit être fermée.

En UDP, un datagramme contient exactement une enveloppe JSON, sans en-tête de longueur.

## Enveloppe

Tous les messages, en TCP comme en UDP, ont la même forme : un objet JSON à plat.

```json
{"type": "POS", "id": "voiture_12", "ts": 1727093000.512, "nonce": "9f2c1a0b7d3e4f56", "donnees": {"x": 8.4, "y": 15.6, "cap": 298.2, "vitesse": 8.3, "segment": "jean_de_la_bruyere-nations_nord", "etape": "anneau"}, "hmac": "5d41402abc4b2a76…"}
```

| Champ | Type | Rôle |
| --- | --- | --- |
| `type` | texte | type du message (voir le tableau suivant) |
| `id` | texte | identifiant de l'émetteur : `voiture_12`, `vp_1`, `serveur`... |
| `ts` | nombre | horodatage d'émission, en secondes depuis l'epoch |
| `nonce` | texte | 16 caractères hexadécimaux tirés au hasard pour chaque message |
| `donnees` | objet | contenu propre au type de message |
| `hmac` | texte | HMAC-SHA256 en hexadécimal, calculé sur tous les autres champs |

Dans le code, `Message` porte `type`, `id` et `donnees` ; `Enveloppe` y ajoute `ts`, `nonce` et `hmac`. Le calcul du HMAC et le contrôle anti-rejeu sont décrits dans [securite.md](securite.md).

## Types de messages

| type | Sens | Transport | donnees |
| --- | --- | --- | --- |
| HELLO | client → serveur | TCP | `{"categorie": "voiture", "entree": "nations_sud", "sortie": "albert_camus"}`, catégorie parmi `voiture`, `moto`, `trottinette`, `pieton`, `vp` |
| HELLO_ACK | serveur → client | TCP | `{"accepte": true}`, ou `{"accepte": false, "raison": "...", "reessayer": true}` en cas de refus |
| POS | client → serveur | UDP | `{"x": 8.4, "y": 15.6, "cap": 298.2, "vitesse": 8.3, "segment": "jean_de_la_bruyere-nations_nord", "etape": "anneau"}` |
| VP_ALERT | client VP → serveur | TCP | `{"entree": "nations_sud", "sortie": "nations_nord", "eta": 4.5}`, `eta` en secondes avant l'anneau |
| VP_FIN | client VP → serveur | TCP | `{}` |
| NOTIF | serveur → client | TCP | `{"code": "DEGAGEZ", "message": "..."}`, code parmi `DEGAGEZ`, `CHANGEZ_VOIE`, `ATTENDEZ`, `OK_PASSER` |
| STATE | serveur → supervision | TCP | `{"usagers": [...], "densite": {"nations_nord": 0.25, ...}, "vp_actif": true, "vps": [{"id": "vp_1", "entree": "nations_sud", "sortie": "nations_nord", "eta": 4.5}], "segments_reserves": ["jean_de_la_bruyere-nations_nord", "nations_sud-jean_de_la_bruyere"], "entrees_bloquees": [], "passages_fermes": [{"branche": "nations_nord", "chaussee": "sortie"}], "regulation": true}`, voir plus bas |
| ABONNEMENT | supervision → serveur | TCP | `{}` : la connexion reçoit ensuite les STATE |
| REGLAGE | supervision → serveur | TCP | `{"regulation": false}`, voir « Régulation » |
| PING | client → serveur | TCP | `{}` |
| PONG | serveur → client | TCP | `{}` |
| BYE | client → serveur | TCP | `{}` |
| DEVANT | serveur → client | TCP | `{"distance": 12.4, "ceder": false}`, voir « Ce que voit un conducteur » |
| STATS_DEMANDE | supervision → serveur | TCP | `{}`, voir « Historique et statistiques » |
| STATS_REPONSE | serveur → supervision | TCP | `{"disponible": true, "passages": [...], "densites": [...]}`, ou `{"disponible": false, "raison": "..."}` |

Les branches sont désignées par leur identifiant, tiré du nom de la rue : `nations_nord`, `jean_de_la_bruyere`, `nations_sud` et `albert_camus` pour le rond-point de Bel Air (voir [geometrie_bel_air.md](geometrie_bel_air.md)). Un segment porte le nom de ses deux branches, dans le sens de circulation, séparés par un tiret.

Chaque élément de la liste `usagers` d'un STATE décrit un usager connecté :

```json
{"id": "voiture_12", "categorie": "voiture", "entree": "nations_sud", "sortie": "nations_nord", "x": 29.5, "y": -33.9, "cap": 327.0, "vitesse": 8.0, "segment": null, "etape": "approche", "consigne": null}
```

`x`, `y` et `cap` valent `null` tant que le serveur n'a reçu aucune position de l'usager. Le cap est la direction dans laquelle l'usager avance, en degrés depuis le nord dans le sens des aiguilles d'une montre : la supervision s'en sert pour tourner chaque véhicule dans son sens de marche. Les autres champs du STATE :

- `densite` : pour chaque branche, le nombre d'usagers en approche sur cette branche divisé par sa capacité, borné entre 0 et 1. Faible en dessous de 0,4, moyenne en dessous de 0,7, forte au-delà.
- `vp_actif` : `true` si au moins un VP annoncé n'a pas fini sa traversée.
- `vps` : les VP annoncés dont la traversée n'est pas finie, avec leur trajet et l'`eta` de leur VP_ALERT (le temps annoncé pour atteindre l'anneau, en secondes, compté depuis l'annonce). La supervision en tire les événements « VP annoncé » et « fin de traversée ».
- `segments_reserves` : segments de l'anneau réservés aux VP en cours de traversée, triés par nom, pour que la supervision puisse les afficher. Ils sont envoyés que la régulation soit active ou non.
- `entrees_bloquees` : branches où au moins un usager attend sur ordre du régulateur (ATTENDEZ), triées par nom.
- `passages_fermes` : demi-chaussées fermées par un piéton qui les traverse, avec leur branche et leur chaussée (`entree` ou `sortie`). Elles sont fermées que la régulation soit active ou non.
- `consigne` de chaque usager : la dernière consigne que le serveur lui a envoyée, `null` s'il circule librement.
- `regulation` : `true` si la régulation est active.

## Ce que voit un conducteur (DEVANT)

Chaque client roule sans voir les autres : sans aide, deux voitures pourraient se traverser, et un VP ne serait jamais gêné par le trafic. Le serveur, qui connaît toutes les positions, simule donc ce qu'un conducteur verrait par son pare-brise. **DEVANT n'est pas une consigne de régulation** : il part à chaque cadence vers chaque usager, que la régulation soit active ou non.

- `distance` : distance, en mètres, jusqu'à l'obstacle le plus proche devant le véhicule sur sa voie, ou `null` si rien ne gêne dans les 50 m. Un obstacle est un autre véhicule sur la même voie, ou un piéton en train de traverser le passage piéton de la branche. Une chaussée de branche n'a qu'une file : tout véhicule devant sur la même chaussée est un obstacle, rangé ou non. Seul un VP prioritaire (régulation active) double ceux qui se sont rangés sur le bord : pour lui, un véhicule dont l'écart à l'axe diffère du sien d'au moins 1 m n'est pas sur sa file. Sur l'anneau, deux véhicules sont sur la même voie si leurs distances au centre diffèrent de moins d'une demi-largeur de voie ; l'obstacle compte jusqu'à la sortie du véhicule, chaussée de sortie comprise. Les distances sur l'anneau sont mesurées à la distance au centre du véhicule, ce qui compte un peu court dans les raccords : c'est le côté prudent.
- Un piéton ne ferme que la demi-chaussée sur laquelle il marche : la chaussée d'entrée bloque les véhicules en approche, la chaussée de sortie ceux qui quittent l'anneau par cette branche. Sur le refuge du terre-plein, il ne bloque personne.
- `ceder` : `true` si le véhicule doit s'arrêter sur sa ligne d'entrée, au bord de l'anneau. Les entrées se font une par une : le serveur donne son tour à un seul véhicule, à moins de 12 m de sa ligne, sans obstacle devant lui ni consigne ATTENDEZ ou CHANGEZ_VOIE, l'anneau libre sur 15 m avant et 10 m après son point d'entrée. Pour rejoindre sa voie, un véhicule qui entre traverse la voie extérieure : l'anneau doit être libre sur les deux voies. Le véhicule garde son tour jusqu'à avoir parcouru 10 m sur l'anneau ; s'il le perd avant sa ligne, personne ne le reçoit à cette cadence, car il a pu franchir la ligne avec l'autorisation précédente. Tous les autres véhicules en approche reçoivent `true`.
- Régulation active, un VP annoncé ne cède jamais le passage : les autres dégagent sa voie. Sur sa chaussée d'approche, il double les usagers rangés. Sur l'anneau, il ne voit que les obstacles de la voie intérieure, la sienne, même pendant qu'il la rejoint.
- Un piéton reçoit la distance au piéton qui le précède sur le même passage, et `ceder` à `false`.

Le client garde une distance de sécurité avec l'obstacle signalé, 6 m pour un véhicule et 1,5 m pour un piéton, qui couvre aussi le retard d'un pas de la position vue par le serveur. Il ne recule jamais, et s'arrête sur sa ligne d'entrée tant que `ceder` vaut `true`. Les usagers arrêtés forment ainsi une vraie file au lieu de s'empiler au même point.

Les marges du cédez-le-passage empêchent l'anneau de se remplir au point de se bloquer en boucle : pour qu'un véhicule entre, il faut 25 m libres autour de son point d'entrée, ce qui interdit d'aligner sur tout l'anneau des véhicules espacés seulement de la distance de sécurité.

## Véhicules prioritaires

- Un VP s'annonce par VP_ALERT dès que son HELLO est accepté. Le serveur ne l'accepte que d'un usager inscrit de catégorie `vp`, avec la même entrée et la même sortie que son HELLO et un `eta` positif ou nul. Il réserve alors les segments de la trajectoire du VP. Un VP_ALERT répété pour un VP déjà annoncé ne change rien.
- Le VP envoie VP_FIN au moment où il quitte l'anneau. Le serveur lève sa réservation et conserve la mesure de sa traversée : le temps entre son VP_ALERT et son VP_FIN, le temps passé sur l'anneau seul (depuis son premier POS reçu sur l'anneau), le mode de régulation en vigueur à l'annonce et la densité moyenne des branches pendant la traversée. La définition est la même que la régulation soit active ou non.
- Si la session d'un VP se ferme avant son VP_FIN, sa réservation est levée sans mesure. Après une reconnexion, le VP se réannonce tant qu'il n'a pas quitté l'anneau.

## Régulation (NOTIF et REGLAGE)

À chaque cadence, le régulateur du serveur décide de la consigne de chaque usager et n'envoie une NOTIF que si elle change. Quand un VP traverse, ses segments réservés qu'il n'a pas encore quittés doivent rester libres :

1. un usager sur l'anneau qui est, ou va passer, sur un de ces segments reçoit DEGAGEZ : il passe sur la voie extérieure, puis ralentit. Le VP roule sur la voie intérieure, qui se libère ; un usager déjà sur la voie extérieure ne fait que ralentir ;
2. un usager devant un VP en approche, sur la même chaussée d'entrée, reçoit CHANGEZ_VOIE : il se range au bord droit de sa chaussée, sans accélérer, puis s'immobilise et attend que le VP l'ait dépassé. Il ne franchit pas sa ligne d'entrée. Le VP, qui roule sur la gauche de sa chaussée (0,8 m à gauche du milieu), le double sans ralentir : rangé à 1,9 m à droite du milieu, l'usager n'est pas sur sa file, et 0,6 m sépare leurs flancs à l'écran. L'usager garde CHANGEZ_VOIE jusqu'à ce que l'avant du VP le devance de 8 m (la longueur du VP et une marge), pour ne pas reprendre sa voie contre son flanc ;
3. un usager en approche dont le trajet passe par un segment réservé reçoit ATTENDEZ (il s'arrête sur sa ligne d'entrée) et le garde jusqu'au VP_FIN, même si le VP a déjà quitté ce segment. C'est le cas des usagers qui roulent derrière le VP sur sa branche, et de ceux qu'il vient de dépasser : ils reprennent le milieu de leur chaussée et avancent jusqu'à leur ligne ;
4. un piéton qui attend devant le passage de la branche d'entrée ou de sortie d'un VP reçoit ATTENDEZ (« attendez pour traverser »).

Sans VP, le régulateur dose les entrées : si une branche est en densité forte, la moins chargée des autres entrées occupées, si elle n'est pas elle-même en densité forte, reçoit ATTENDEZ. Dans tous les autres cas, l'usager circule librement : s'il avait une consigne, il reçoit OK_PASSER. Le VP ne reçoit jamais de consigne.

Le champ `message` d'une NOTIF explique la consigne en une phrase (par exemple « Véhicule prioritaire en approche : attendez pour traverser. »).

Quand la session d'un usager se ferme, le régulateur oublie sa consigne : après une reconnexion, la consigne qui vaut encore lui est renvoyée à la cadence suivante.

REGLAGE n'est accepté que d'une session de supervision abonnée, avec `regulation` booléen. Régulation coupée, le régulateur envoie une seule fois OK_PASSER à ceux qui avaient une consigne, sans quoi ils attendraient pour toujours, puis plus aucune NOTIF : c'est la référence pour mesurer ce qu'apporte la régulation. DEVANT continue de partir, puisqu'il simule ce que voient les conducteurs.

## Sessions et heartbeat

- Chaque connexion TCP ouvre une session. Elle devient celle d'un usager quand son HELLO est accepté, ou celle d'une supervision après un ABONNEMENT.
- Un HELLO est refusé, avec la raison dans le HELLO_ACK, si la session est déjà enregistrée, si l'identifiant est déjà connecté sur une autre session, s'il manque un champ, si la catégorie ou une branche est inconnue, ou si un piéton donne une sortie différente de son entrée.
- Le champ `reessayer` du refus dit au client si un nouvel essai peut réussir. Il ne vaut `true` que pour un identifiant déjà connecté : l'autre session a pu disparaître sans prévenir, et elle expirera au bout de `timeout_client`. Tous les autres refus sont définitifs.
- Après le HELLO, tous les messages de la session doivent porter l'identifiant de son usager. Un message au nom d'un autre est refusé.
- Toute session, usager ou supervision, doit donner des nouvelles : le client envoie un PING toutes les 2 s (`intervalle_ping`) et le serveur répond PONG. Seuls les messages TCP comptent ; les POS reçus en UDP ne maintiennent pas la session.
- Après 6 s sans message (`timeout_client`), le serveur ferme la socket et retire l'usager du registre. Il fait de même après un BYE, une déconnexion ou une coupure brutale.
- Toutes les 0,2 s (`intervalle_etat`), le serveur envoie un STATE à chaque supervision abonnée, et à elles seules.

## Côté client

- Le client ouvre la connexion TCP, envoie son HELLO et attend le HELLO_ACK au plus `timeout_client` secondes.
- Une fois inscrit, il avance d'un pas toutes les `intervalle_position` secondes et envoie aussitôt sa position en UDP. Il envoie un PING toutes les `intervalle_ping` secondes.
- Si le serveur ne donne aucune nouvelle pendant `timeout_client` secondes, alors qu'il répond normalement à chaque PING, le client considère la connexion perdue, même si TCP ne l'a pas encore signalé.
- Après une coupure, ou un refus avec `reessayer` à `true`, le client attend `backoff_initial` secondes, puis un délai qui double à chaque échec (1, 2, 4, 8 s), plafonné à `backoff_max` (10 s). Il renvoie un HELLO à chaque reconnexion. Un refus définitif l'arrête.
- Une nouvelle session repart sans consigne : le serveur renvoie celles qui s'appliquent encore.
- À la fin de son trajet, ou quand on l'arrête, le client envoie un BYE : le serveur le retire du registre sans attendre le timeout.

## Côté supervision

- La supervision ouvre une connexion TCP et envoie un ABONNEMENT, au nom de `supervision`. Le serveur ne l'accuse pas : la session reçoit ensuite un STATE à chaque cadence.
- Comme un client, elle envoie un PING toutes les `intervalle_ping` secondes, sans quoi le serveur la retirerait au bout de `timeout_client`. Si elle ne reçoit ni PONG ni STATE pendant `timeout_client` secondes, elle considère la connexion perdue, se reconnecte avec le même backoff que les clients, puis se réabonne.
- Elle envoie un REGLAGE à chaque clic sur l'interrupteur de régulation. Le serveur ne répond pas : l'effet se lit dans le champ `regulation` des STATE suivants, et c'est ce champ que la supervision affiche. Un réglage demandé pendant une coupure est abandonné ; à la reconnexion, l'interrupteur reprend l'état du serveur.
- Un STATE auquel il manque un champ est journalisé puis ignoré.
- Elle envoie un STATS_DEMANDE quand on ouvre l'onglet « Statistiques » ou qu'on clique sur « Actualiser ». Plusieurs demandes faites avant l'envoi n'en font qu'une ; pendant une coupure, la demande part à la reconnexion.
- À la fermeture de la fenêtre, la supervision envoie un BYE.

## Historique et statistiques

Seul le serveur accède à la base MariaDB. Il y écrit son historique par un thread à part, qui reçoit les enregistrements par une file : la boucle `select` n'attend jamais la base.

- À chaque VP_FIN, la mesure de la traversée (début, fin, durée, durée sur l'anneau, régulation, densité moyenne) part dans la table `passage_vp`.
- Toutes les `intervalle_releves` secondes (section `[bdd]`), la densité de chaque branche part dans `releve_densite`.
- Chaque HELLO accepté et chaque session d'usager fermée (avec sa raison : BYE, silence, coupure) part dans `evenement_connexion`.

Si la base est injoignable, le serveur continue de fonctionner : les enregistrements attendent en mémoire, jusqu'à 10 000 par table (les plus anciens sont oubliés au-delà), et le thread réessaie de se connecter toutes les `delai_reessai` secondes. La panne est journalisée une fois, puis le retour de la base.

STATS_DEMANDE n'est accepté que d'une session de supervision abonnée ; venu d'un usager, il est refusé comme une trame invalide. Le serveur lit en base les 200 dernières traversées et les 2 000 derniers relevés de densité, puis répond par un STATS_REPONSE à la cadence suivante. Avant de lire, il écrit ce qui attend, traversée tout juste terminée comprise.

```json
{"disponible": true,
 "passages": [{"vp": "vp_1", "entree": "nations_sud", "sortie": "nations_nord", "debut": "2026-11-17T15:31:14.512000",
               "duree": 9.2, "duree_anneau": 3.1, "regulation": true, "densite_moyenne": 0.31}],
 "densites": [{"instant": "2026-11-17T15:31:15.004000", "branche": "nations_sud", "densite": 0.375}]}
```

Les listes vont du plus ancien au plus récent, les dates en ISO 8601. Base injoignable, la réponse vaut `{"disponible": false, "raison": "base injoignable (10.0.0.2:3306)"}` et la supervision affiche la raison. Comme toutes les trames, STATS_DEMANDE et STATS_REPONSE sont signés par HMAC et soumis à l'anti-rejeu.

## Positions en UDP

Le serveur ne répond pas aux POS. Il n'accepte une position que si son émetteur a une session TCP ouverte, où son HELLO a été accepté : c'est le contrôle d'identité. Il vérifie aussi que `x` et `y` sont des nombres finis, que `cap` est un nombre compris entre 0 (inclus) et 360 (exclu), que `vitesse` reste entre 0 et la vitesse maximale de la catégorie, et que `segment` est le nom d'un segment de l'anneau, ou `null` hors de l'anneau.

Le champ `etape` dit où en est l'usager sur son trajet : `approche` (sur la chaussée d'entrée de sa branche, jusqu'à la ligne au bord de l'anneau), `anneau`, `traversee` (piéton sur le passage, d'un trottoir à l'autre) ou `sortie`. Le serveur s'en sert pour savoir qui attend en file sur chaque branche. Un `segment` n'est accepté qu'avec l'étape `anneau`, et l'étape `anneau` exige un segment.

## Trames refusées

À la réception, une trame passe trois contrôles dans cet ordre : lecture de l'enveloppe, vérification du HMAC, contrôle anti-rejeu (détails dans [securite.md](securite.md)). Chaque échec lève une exception dédiée, fille de `CherryPieError` : `TrameInvalideError`, `SignatureInvalideError` ou `RejeuDetecteError`, et `UsagerInconnuError` pour une position sans session TCP. La trame est alors journalisée puis ignorée, sans interrompre le serveur. Seule exception : sur TCP, une longueur annoncée de plus de 1 Mio ferme la connexion, puisque le flux ne peut plus être resynchronisé.
