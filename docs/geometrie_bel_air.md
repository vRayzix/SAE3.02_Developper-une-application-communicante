# Géométrie du rond-point de Bel Air

Proposition de géométrie pour la maquette, relevée sur deux vues aériennes du rond-point André Marie Talvas (Mulhouse), nord en haut. Les images ne sont pas versionnées.

## Méthode et précision

- Échelle de la vue rapprochée : environ 10 px par mètre, mesurée sur les voitures garées du parking à l'est (4,5 m de long, places de 2,5 m) et sur la largeur de l'allée. La vue large est à environ 5 px par mètre.
- Centre et rayons : cercles ajustés sur la bordure de l'îlot central et sur le bord extérieur de l'anneau.
- Caps : relevés en degrés depuis le nord, dans le sens des aiguilles d'une montre. Pour chaque branche, on a pris à la fois l'endroit où elle rejoint l'anneau (vu depuis le centre) et la direction de la chaussée sur ses 50 premiers mètres. Les deux vues donnent les mêmes valeurs à quelques degrés près.
- Précision attendue : environ 1 m sur les longueurs, 3 à 5° sur les caps. C'est suffisant pour une maquette, pas pour un plan.

## Ce que montrent les photos

| Élément | Mesure |
| --- | --- |
| Îlot central | rond, rayon d'environ 15,5 m, engazonné et planté |
| Anneau | largeur d'environ 9 m, bord extérieur à environ 24,5 m du centre |
| Marquage de l'anneau | aucun : pas de ligne entre deux voies, seulement la bordure de l'îlot |
| Sens de circulation | anti-horaire (flèches au sol à l'est et au sud de l'anneau) |
| Branches | 4, toutes en double chaussée : un sens d'entrée et un sens de sortie séparés par un terre-plein ou un îlot séparateur |

| Branche | Cap au raccordement | Cap de la chaussée | Chaussée d'entrée | Terre-plein | Chaussée de sortie | Passage piéton (depuis le bord de l'anneau) |
| --- | --- | --- | --- | --- | --- | --- |
| Boulevard des Nations, côté nord | 337° | 343 à 345° | 7,5 m | 8 m, engazonné | 6,5 m | environ 10 m |
| Rue Jean de la Bruyère | 57° | 58 à 62° | 4 m | 1 à 3 m | 4 m | environ 8 m |
| Boulevard des Nations, côté sud (axe du tram, vers l'arrêt Bel Air) | 146° | 144 à 150° | 5,5 m | 7,5 m, engazonné | 3,5 à 4 m | environ 6 m |
| Rue Albert Camus | 230° | 228 à 240° | 4 m | îlot de 3 à 5 m, puis les deux chaussées se rejoignent | 4 m | environ 8 m |

Les chaussées d'entrée et de sortie sont placées comme on l'attend en circulation à droite : en arrivant vers l'anneau, la chaussée d'entrée est à droite du terre-plein.

### Anneau : une ou deux voies ?

L'anneau ne porte aucun marquage de voies : c'est une seule chaussée large. Avec environ 9 m, il laisse en pratique la place à deux véhicules côte à côte (deux files de 4,5 m). La maquette peut donc le traiter comme un anneau à deux voies, intérieure et extérieure, en dessinant une ligne de séparation qui n'existe pas sur place, pour rendre les changements de voie lisibles.

### Ce que la maquette laisse de côté

- La bretelle de tourne-à-droite au nord de l'anneau, qui mène directement de la rue Jean de la Bruyère vers le boulevard des Nations. Dans la maquette, ce trafic passe par l'anneau.
- L'évasement des entrées près de l'anneau et la forme exacte des îlots séparateurs.
- Les pistes cyclables, les trottoirs et les arrêts de bus.
- Les branches qui ne rejoignent pas l'anneau dans l'axe de son centre : elles sont ramenées à des branches droites, dirigées vers le centre, au cap de leur raccordement.

## Géométrie proposée pour la maquette

### Paramètres

| Paramètre | Valeur | Commentaire |
| --- | --- | --- |
| Rayon de l'axe de l'anneau | 20 m | entre les deux voies ; même valeur qu'aujourd'hui |
| Voies de l'anneau | 2, de 4,5 m | intérieure, axe à 17,75 m du centre ; extérieure, axe à 22,25 m |
| Îlot central | rayon de 15,5 m | déduit du rayon et de la largeur de l'anneau |
| Bord extérieur de l'anneau | 24,5 m | idem |
| Chaussée de chaque sens | 5 m, une voie | une voiture peut s'y ranger à droite pour laisser passer le VP |
| Longueur des branches | 50 m depuis le bord de l'anneau | une file de 8 véhicules espacés de 6 m |
| Capacité par branche | 8 | inchangée |

| Identifiant | Libellé affiché | Cap | Terre-plein | Passage piéton |
| --- | --- | --- | --- | --- |
| `nations_nord` | Bd des Nations (nord) | 340° | 8 m | 10 m |
| `jean_de_la_bruyere` | Rue Jean de la Bruyère | 57° | 2,5 m | 8 m |
| `nations_sud` | Bd des Nations (sud) | 147° | 7,5 m | 6 m |
| `albert_camus` | Rue Albert Camus | 230° | 3 m | 8 m |

Les identifiants sont tirés des noms de rues, en minuscules et sans accents. Ce sont eux qui circulent dans le protocole (`entree`, `sortie`, densité, noms de segments) ; les libellés ne servent qu'à l'affichage. Le boulevard des Nations traverse le rond-point : ses deux côtés sont deux branches distinctes.

### Segments de l'anneau

Dans le sens de circulation, l'anneau passe par la rue Jean de la Bruyère, le boulevard des Nations côté nord, la rue Albert Camus, puis le boulevard des Nations côté sud. Les segments n'ont plus tous la même longueur :

| Segment | Ouverture | Longueur sur l'axe | Voie intérieure | Voie extérieure |
| --- | --- | --- | --- | --- |
| `jean_de_la_bruyere-nations_nord` | 77° | 26,9 m | 23,9 m | 29,9 m |
| `nations_nord-albert_camus` | 110° | 38,4 m | 34,1 m | 42,7 m |
| `albert_camus-nations_sud` | 83° | 29,0 m | 25,7 m | 32,2 m |
| `nations_sud-jean_de_la_bruyere` | 90° | 31,4 m | 27,9 m | 35,0 m |

### Configuration

Une section par branche, avec son libellé et son cap. Le cap se lit comme sur une carte ; le modèle le convertit en angle mathématique (angle = 90° moins le cap).

```ini
[rond_point]
branches = nations_nord, jean_de_la_bruyere, nations_sud, albert_camus
rayon = 20
largeur_voie_anneau = 4.5
largeur_chaussee = 5
longueur_branche = 50
capacite_par_branche = 8

[branche.nations_nord]
libelle = Bd des Nations (nord)
cap = 340
terre_plein = 8
passage_pieton = 10

[branche.jean_de_la_bruyere]
libelle = Rue Jean de la Bruyère
cap = 57
terre_plein = 2.5
passage_pieton = 8

[branche.nations_sud]
libelle = Bd des Nations (sud)
cap = 147
terre_plein = 7.5
passage_pieton = 6

[branche.albert_camus]
libelle = Rue Albert Camus
cap = 230
terre_plein = 3
passage_pieton = 8
```

La clé s'appelle `libelle` plutôt que `nom` : dans le code, le nom d'une branche reste son identifiant, celui du protocole.

Le tram n'est pas modélisé. Une section par branche permettra d'y ajouter plus tard une clé (par exemple `tram = oui` sur `nations_sud`, dont le terre-plein accueille la voie) sans changer le format ; d'ici là, aucune clé inutilisée n'est lue.

### Usage des voies

- Un usager qui sort à la première sortie roule sur la voie extérieure. Les autres roulent sur la voie intérieure et se rabattent sur la voie extérieure au début du segment qui mène à leur sortie.
- Le véhicule prioritaire roule sur la voie intérieure de bout en bout.
- DEGAGEZ : un usager sur la voie intérieure, devant le VP, passe sur la voie extérieure et ralentit. Le changement de voie se voit sur la scène.
- CHANGEZ_VOIE : dans la file d'entrée du VP, l'usager se range sur la droite de sa chaussée d'entrée pour laisser passer le VP à sa gauche.
- Deux usagers ne se gênent que s'ils sont sur la même voie, comme aujourd'hui avec la règle « même voie ». Un usager qui entre sur l'anneau traverse la voie extérieure : il cède le passage aux usagers des deux voies.
- Un piéton traverse toute la branche sur son passage piéton : chaussée d'entrée, terre-plein, chaussée de sortie. Pendant sa traversée, il bloque les deux chaussées de la branche, comme aujourd'hui.

## Décisions

- Géométrie, modèle à deux voies sur l'anneau et une voie par sens de branche, règle d'usage des voies : validés.
- La bretelle de tourne-à-droite vers le boulevard des Nations reste hors de la maquette.
- Le boulevard des Nations traverse le rond-point : le bras à 340° est son côté nord, celui à 147° son côté sud.
- La branche à 57° est la rue Jean de la Bruyère.
- Identifiants tirés des rues, libellés affichés avec les vrais noms.
