# Protocole de communication

Ce document décrit les messages échangés entre le serveur du rond-point, les clients usagers et la supervision. Il suit le code de `src/cherrypie/commun/` et doit être mis à jour à chaque changement du protocole.

## Transports

| Transport | Port | Usage |
| --- | --- | --- |
| TCP | 5000 | messages qui doivent arriver : HELLO, VP_ALERT, VP_FIN, BYE, PING, PONG, NOTIF, STATE, ABONNEMENT, REGLAGE |
| UDP | 5001 | positions (POS), environ toutes les 200 ms ; une position perdue est remplacée par la suivante |

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
{"type": "POS", "id": "voiture_12", "ts": 1727093000.512, "nonce": "9f2c1a0b7d3e4f56", "donnees": {"x": 3.5, "y": -1.0, "vitesse": 8.3, "segment": "N-O"}, "hmac": "5d41402abc4b2a76…"}
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
| HELLO | client → serveur | TCP | `{"categorie": "voiture", "entree": "N", "sortie": "E"}`, catégorie parmi `voiture`, `moto`, `trottinette`, `pieton`, `vp` |
| HELLO_ACK | serveur → client | TCP | `{"accepte": true}`, ou `{"accepte": false, "raison": "..."}` en cas de refus |
| POS | client → serveur | UDP | `{"x": 3.5, "y": -1.0, "vitesse": 8.3, "segment": "N-O"}` |
| VP_ALERT | client VP → serveur | TCP | `{"entree": "N", "sortie": "E", "eta": 8.0}` |
| VP_FIN | client VP → serveur | TCP | `{}` |
| NOTIF | serveur → client | TCP | `{"code": "DEGAGEZ", "message": "..."}`, code parmi `DEGAGEZ`, `CHANGEZ_VOIE`, `ATTENDEZ`, `OK_PASSER` |
| STATE | serveur → supervision | TCP | `{"usagers": [...]}`, voir plus bas |
| ABONNEMENT | supervision → serveur | TCP | `{}` : la connexion reçoit ensuite les STATE |
| REGLAGE | supervision → serveur | TCP | `{"regulation": false}` |
| PING | client → serveur | TCP | `{}` |
| PONG | serveur → client | TCP | `{}` |
| BYE | client → serveur | TCP | `{}` |

Chaque élément de la liste `usagers` d'un STATE décrit un usager connecté :

```json
{"id": "voiture_12", "categorie": "voiture", "entree": "S", "sortie": "N", "x": 0.0, "y": -20.0, "vitesse": 8.0, "segment": null, "consigne": null}
```

`x` et `y` valent `null` tant que le serveur n'a reçu aucune position de l'usager. Les champs `densite`, `vp_actif`, `entrees_bloquees` et `regulation` s'ajouteront au STATE avec la régulation.

## Sessions et heartbeat

- Chaque connexion TCP ouvre une session. Elle devient celle d'un usager quand son HELLO est accepté, ou celle d'une supervision après un ABONNEMENT.
- Un HELLO est refusé, avec la raison dans le HELLO_ACK, si la session est déjà enregistrée, si l'identifiant est déjà connecté sur une autre session, s'il manque un champ, si la catégorie ou une branche est inconnue, ou si un piéton donne une sortie différente de son entrée.
- Après le HELLO, tous les messages de la session doivent porter l'identifiant de son usager. Un message au nom d'un autre est refusé.
- Toute session, usager ou supervision, doit donner des nouvelles : le client envoie un PING toutes les 2 s (`intervalle_ping`) et le serveur répond PONG. Seuls les messages TCP comptent ; les POS reçus en UDP ne maintiennent pas la session.
- Après 6 s sans message (`timeout_client`), le serveur ferme la socket et retire l'usager du registre. Il fait de même après un BYE, une déconnexion ou une coupure brutale.
- Toutes les 0,2 s (`intervalle_etat`), le serveur envoie un STATE à chaque supervision abonnée, et à elles seules.

## Positions en UDP

Le serveur ne répond pas aux POS. Il n'accepte une position que si son émetteur a une session TCP ouverte, où son HELLO a été accepté : c'est le contrôle d'identité. Il vérifie aussi que `x` et `y` sont des nombres finis, que `vitesse` reste entre 0 et la vitesse maximale de la catégorie, et que `segment` est le nom d'un segment de l'anneau, ou `null` hors de l'anneau.

## Trames refusées

À la réception, une trame passe trois contrôles dans cet ordre : lecture de l'enveloppe, vérification du HMAC, contrôle anti-rejeu (détails dans [securite.md](securite.md)). Chaque échec lève une exception dédiée, fille de `CherryPieError` : `TrameInvalideError`, `SignatureInvalideError` ou `RejeuDetecteError`, et `UsagerInconnuError` pour une position sans session TCP. La trame est alors journalisée puis ignorée, sans interrompre le serveur. Seule exception : sur TCP, une longueur annoncée de plus de 1 Mio ferme la connexion, puisque le flux ne peut plus être resynchronisé.
