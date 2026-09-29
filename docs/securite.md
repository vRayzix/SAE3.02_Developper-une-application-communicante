# Sécurité des échanges

## Ce qui est garanti

| Propriété | Moyen |
| --- | --- |
| Authenticité : le message vient d'un programme qui connaît la clé | HMAC-SHA256 avec une clé partagée |
| Intégrité : le message n'a pas été modifié en route | le HMAC couvre tous les champs de l'enveloppe |
| Fraîcheur : un message capturé ne peut pas être rejoué | horodatage et nonce, contrôlés par `GardeAntiRejeu` |

Ces protections s'appliquent à toutes les trames, TCP comme UDP. Le code se trouve dans `src/cherrypie/commun/securite.py`.

## Signature HMAC

- La clé est partagée par le serveur et tous les clients. Elle est lue dans la section `[securite]` de `config.ini`, fichier qui n'est pas versionné.
- Le HMAC est calculé sur l'enveloppe privée de son champ `hmac`, sérialisée de façon canonique : `json.dumps(contenu, sort_keys=True, separators=(",", ":"))`. L'émetteur et le récepteur signent ainsi exactement les mêmes octets, quel que soit l'ordre dans lequel les champs ont été reçus.
- La vérification recalcule le HMAC et le compare avec `hmac.compare_digest`. Cette comparaison prend le même temps quelle que soit la position de la première différence : mesurer le temps de réponse ne permet pas de deviner la signature octet par octet.
- Le champ `id` fait partie du contenu signé : sans la clé, impossible de se faire passer pour un autre usager.

## Anti-rejeu

Une trame capturée sur le réseau garde une signature valide. Sans autre protection, un attaquant pourrait la renvoyer telle quelle, par exemple un VP_ALERT pour bloquer les entrées du rond-point. Deux contrôles l'en empêchent :

1. **Horodatage** : la trame est refusée si `|maintenant - ts|` dépasse 5 s (`fenetre_anti_rejeu` dans `config.ini`).
2. **Nonce** : chaque message porte un nonce de 16 caractères hexadécimaux tiré avec `secrets.token_hex(8)`. Le récepteur retient les nonces reçus et refuse une trame dont le nonce a déjà été vu.

Le cache des nonces est borné : un nonce est oublié dès que son horodatage sort de la fenêtre, puisque sa trame serait de toute façon refusée par le premier contrôle. Sa taille dépend donc du trafic reçu en 5 secondes, pas de la durée de fonctionnement du serveur. Seules les trames correctement signées y entrent : sans la clé, un attaquant ne peut pas le remplir.

## Ordre des contrôles à la réception

1. `Enveloppe.depuis_octets()` : JSON UTF-8 bien formé, champs présents et bien typés, horodatage fini. Sinon `TrameInvalideError`.
2. `Signataire.verifier()` : HMAC correct. Sinon `SignatureInvalideError`.
3. `GardeAntiRejeu.controler()` : horodatage dans la fenêtre, nonce jamais reçu. Sinon `RejeuDetecteError`.

Le contrôle anti-rejeu vient après la signature : tant que le HMAC n'est pas vérifié, l'horodatage et le nonce ont pu être choisis par l'attaquant. Toutes ces erreurs héritent de `CherryPieError` ; la trame fautive est journalisée puis ignorée, sans interrompre le serveur.

## Limites assumées

- **Pas de confidentialité** : les trames circulent en clair. Quelqu'un qui écoute le réseau peut lire les positions et les consignes, mais pas les modifier ni en fabriquer. Chiffrer demanderait une bibliothèque de cryptographie externe, que la stack imposée n'autorise pas, et un chiffrement écrit à la main serait plus dangereux qu'utile.
- **Clé partagée** : tous les programmes utilisent la même clé. Un client compromis pourrait donc signer des messages au nom d'un autre usager. Le serveur n'accepte une position UDP que pour un identifiant enregistré par une session TCP active, ce qui limite l'usurpation sans l'empêcher.
- **Horloges** : le contrôle d'horodatage suppose des horloges à moins de 5 s d'écart. C'est automatique sur une seule machine ; sur plusieurs, il faut les synchroniser par NTP.
- **Clé stockée en clair** dans `config.ini` : ce fichier ne doit être ni versionné ni partagé.
