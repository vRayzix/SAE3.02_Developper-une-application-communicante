# Sécurité des échanges

## Ce qui est garanti

| Propriété | Moyen |
| --- | --- |
| Authenticité : le message vient d'un programme qui connaît la clé | HMAC-SHA256 avec une clé partagée |
| Intégrité : le message n'a pas été modifié en route | le HMAC couvre tous les champs de l'enveloppe |
| Fraîcheur : un message capturé ne peut pas être rejoué | horodatage et nonce, contrôlés par `GardeAntiRejeu` |

Ces protections s'appliquent à toutes les trames, TCP comme UDP. Le code se trouve dans `src/cherrypie/commun/securite.py`.

## Signature HMAC

- La clé est partagée par le serveur et tous les clients. Elle vient de la variable d'environnement `CHERRYPIE_CLE`, sinon d'une saisie masquée au lancement ; jamais d'une option de la ligne de commande, que `ps` montre à tous les utilisateurs de la machine, ni de `config.ini`, qui refuse de la contenir.
- Le HMAC est calculé sur l'enveloppe privée de son champ `hmac`, sérialisée de façon canonique : `json.dumps(contenu, sort_keys=True, separators=(",", ":"))`. L'émetteur et le récepteur signent ainsi exactement les mêmes octets, quel que soit l'ordre dans lequel les champs ont été reçus.
- La vérification recalcule le HMAC et le compare avec `hmac.compare_digest`. Cette comparaison prend le même temps quelle que soit la position de la première différence : mesurer le temps de réponse ne permet pas de deviner la signature octet par octet.
- Le champ `id` fait partie du contenu signé : sans la clé, impossible de se faire passer pour un autre usager.

## Anti-rejeu

Une trame capturée sur le réseau garde une signature valide. Sans autre protection, un attaquant pourrait la renvoyer telle quelle, par exemple un VP_ALERT pour bloquer les entrées du rond-point. Deux contrôles l'en empêchent :

1. **Horodatage** : la trame est refusée si `|maintenant - ts|` dépasse la fenêtre anti-rejeu, 5 s par défaut (`HorodatageHorsFenetreError`).
2. **Nonce** : chaque message porte un nonce de 16 caractères hexadécimaux tiré avec `secrets.token_hex(8)`. Le récepteur retient les nonces reçus et refuse une trame dont le nonce a déjà été vu.

Le cache des nonces est borné : un nonce est oublié dès que son horodatage sort de la fenêtre, puisque sa trame serait de toute façon refusée par le premier contrôle. Sa taille dépend donc du trafic reçu pendant une fenêtre, pas de la durée de fonctionnement du serveur. Seules les trames correctement signées y entrent : sans la clé, un attaquant ne peut pas le remplir.

## Fenêtre anti-rejeu et horloges décalées

La fenêtre se règle sans toucher au code : `--fenetre-anti-rejeu`, sinon `CHERRYPIE_FENETRE_ANTI_REJEU`, sinon `[securite] fenetre_anti_rejeu` dans `config.ini`, sinon 5 s. Le serveur et la supervision la lisent ; les clients lancés par la supervision prennent la sienne.

Elle sert à dépanner une recette où les horloges des machines ne sont pas parfaitement synchronisées : avec 34 s d'écart entre le poste et la VM code, toutes les trames étaient refusées, dans les deux sens. Chaque récepteur compare l'horodatage à sa propre horloge : il faut donc donner la même valeur au serveur et à la supervision. La vraie correction reste de synchroniser les horloges (README, « Avant de lancer : les horloges ») ; la fenêtre élargie est un pis-aller.

Le compromis : une fenêtre plus large laisse plus de temps pour rejouer une trame capturée. Le cache des nonces empêche de la rejouer deux fois au même récepteur, mais pas de la rejouer après un redémarrage de ce récepteur, dont le cache est en mémoire, ni à un autre récepteur qui ne l'a jamais vue, par exemple une NOTIF destinée à un usager renvoyée à un autre. Avec 5 s, cette ouverture est courte ; avec 60 s, elle dure une minute, et le cache des nonces grandit d'autant. On élargit donc la fenêtre le temps d'une recette, jamais par défaut.

Quand les trames sont refusées, chaque programme le dit une fois, avec ce qu'il faut vérifier (horloges, `CHERRYPIE_CLE` identique, `--fenetre-anti-rejeu`) : le client après 3 HELLO de suite sans HELLO_ACK, la supervision après 3 abonnements sans aucune trame, le serveur au premier refus pour l'horodatage ou la signature. Le serveur garde en plus un WARNING par trame refusée.

## Ordre des contrôles à la réception

1. `Enveloppe.depuis_octets()` : JSON UTF-8 bien formé, champs présents et bien typés, horodatage fini. Sinon `TrameInvalideError`.
2. `Signataire.verifier()` : HMAC correct. Sinon `SignatureInvalideError`.
3. `GardeAntiRejeu.controler()` : horodatage dans la fenêtre, sinon `HorodatageHorsFenetreError` ; nonce jamais reçu, sinon `RejeuDetecteError` (mère de la précédente).

Le contrôle anti-rejeu vient après la signature : tant que le HMAC n'est pas vérifié, l'horodatage et le nonce ont pu être choisis par l'attaquant. Toutes ces erreurs héritent de `CherryPieError` ; la trame fautive est journalisée puis ignorée, sans interrompre le serveur.

## Accès à la base

- Seul le serveur, sur la VM code, se connecte à MariaDB. La supervision demande les statistiques au serveur par STATS_DEMANDE, une trame signée comme les autres et acceptée seulement d'une session de supervision abonnée : les identifiants de la base ne quittent pas la VM code.
- L'utilisateur MariaDB `cherrypie` n'a de droits que sur la base `cherrypie`, et seulement depuis l'adresse de la VM code (`'cherrypie'@'<adresse de la VM code>'`). Si un pare-feu tourne sur la VM bdd, il n'ouvre le port 3306 qu'à cette adresse.
- Le mot de passe de la base vient de `CHERRYPIE_BDD_MDP` ou d'une saisie masquée, comme la clé. Sur la VM bdd, il ne passe que par une variable du shell, effacée (`unset`) une fois l'utilisateur créé.
- Le README donne des secrets d'exemple fixes (`cherrypie_test`, `cherrypie_cle_test`), pour qu'un déploiement de recette se fasse par copier-coller. Ils sont publics : en production, on les remplace, le mot de passe à l'identique dans `CREATE USER` et `CHERRYPIE_BDD_MDP`, la clé par `secrets.token_hex(32)`. Le code n'en contient aucun.
- Toutes les requêtes sont paramétrées (`%s`) : aucune valeur reçue du réseau n'est collée dans le texte SQL.

## Limites assumées

- **Pas de confidentialité** : les trames circulent en clair. Quelqu'un qui écoute le réseau peut lire les positions et les consignes, mais pas les modifier ni en fabriquer. Chiffrer demanderait une bibliothèque de cryptographie externe, que la stack imposée n'autorise pas, et un chiffrement écrit à la main serait plus dangereux qu'utile.
- **Clé partagée** : tous les programmes utilisent la même clé. Un client compromis pourrait donc signer des messages au nom d'un autre usager. Le serveur n'accepte une position UDP que pour un identifiant enregistré par une session TCP active, ce qui limite l'usurpation sans l'empêcher.
- **Horloges** : le contrôle d'horodatage suppose des horloges à moins de 5 s d'écart. C'est automatique sur une seule machine ; sur plusieurs, il faut les synchroniser (NTP, ou l'heure de l'hôte sous VMware), sinon élargir la fenêtre, au prix décrit plus haut.
- **Secrets dans l'environnement** : `CHERRYPIE_CLE` et `CHERRYPIE_BDD_MDP` restent lisibles par l'utilisateur qui lance le programme (et par root), dans `/proc/<pid>/environ`. C'est moins exposé qu'une option ou un fichier, sans être un coffre-fort ; la saisie masquée évite même cette trace.
- **Connexion à MariaDB en clair** : mysql-connector-python peut chiffrer la connexion (TLS), mais cela demande des certificats sur la VM bdd. Sur le réseau privé des deux VM, la connexion reste en clair ; le mot de passe de la base n'est donné qu'à la VM code.
