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
| HELLO_ACK | serveur → client | TCP | `{"accepte": true}` |
| POS | client → serveur | UDP | `{"x": 3.5, "y": -1.0, "vitesse": 8.3, "segment": "N-O"}` |
| VP_ALERT | client VP → serveur | TCP | `{"entree": "N", "sortie": "E", "eta": 8.0}` |
| VP_FIN | client VP → serveur | TCP | `{}` |
| NOTIF | serveur → client | TCP | `{"code": "DEGAGEZ", "message": "..."}`, code parmi `DEGAGEZ`, `CHANGEZ_VOIE`, `ATTENDEZ`, `OK_PASSER` |
| STATE | serveur → supervision | TCP | `{"usagers": [...], "densite": {"N": 0.7, ...}, "vp_actif": true, "entrees_bloquees": ["S"], "regulation": true}` |
| ABONNEMENT | supervision → serveur | TCP | `{}` : la connexion reçoit ensuite les STATE |
| REGLAGE | supervision → serveur | TCP | `{"regulation": false}` |
| PING | client → serveur | TCP | `{}` |
| PONG | serveur → client | TCP | `{}` |
| BYE | client → serveur | TCP | `{}` |

## Trames refusées

À la réception, une trame passe trois contrôles dans cet ordre : lecture de l'enveloppe, vérification du HMAC, contrôle anti-rejeu (détails dans [securite.md](securite.md)). Chaque échec lève une exception dédiée, fille de `CherryPieError` : `TrameInvalideError`, `SignatureInvalideError` ou `RejeuDetecteError`. La trame est alors journalisée puis ignorée.
