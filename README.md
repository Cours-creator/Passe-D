# Passe D · Prototype de régie football

Passe D est un assistant éditorial qui fournit aux commentateurs des faits vérifiables pendant une rencontre. L'outil rejoue un match et affiche jusqu'à trois suggestions classées par des règles simples. Il ne remplace pas le commentateur.

Deux modes de données existent :

- **Données réelles, en local** : après l'import décrit ci-dessous, l'outil rejoue un vrai match (par défaut la finale de la Coupe du monde 2022) avec des faits calculés depuis StatsBomb Open Data et Wikidata.
- **Démonstration fictive** : sans import, et sur GitHub Pages, l'outil utilise un petit jeu de données inventé, signalé comme tel à l'écran.

## Installation

Python 3.10 ou plus récent est nécessaire. Node.js 18 ou plus récent est requis pour la suite de tests JavaScript de préparation.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Importer les données réelles

```bash
python -m app.real_data.build
```

L'import ne demande ni clé d'API ni compte payant. Il télécharge les Coupes du monde 2018 et 2022 depuis StatsBomb Open Data, interroge Wikidata pour les joueurs et le stade de la rencontre, puis écrit le résultat dans `app/data/local/`. Compter quelques minutes au premier lancement. Le serveur utilise ces données dès qu'elles existent : le redémarrer après un import.

Options utiles :

- `--match 3857300` rejoue une autre rencontre des saisons importées.
- `--season 43:106` choisit les saisons, au format `compétition:saison` de `competitions.json`. L'option est répétable.
- `--no-wikidata` n'interroge pas Wikidata.

## Lancement

À la racine du projet :

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Ouvrir ensuite `http://localhost:8000` dans le navigateur. Dans Codespaces, ouvrir le port 8000 depuis l’onglet **Ports**. L’onglet **Direct** rejoue la rencontre, à raison d'environ une seconde par minute de jeu; l’onglet **Préparation** permet de rechercher puis d’épingler des faits avant la rencontre.

## Publication sur GitHub Pages

Le fichier `index.html` à la racine fournit une version statique autonome, limitée à la démonstration fictive, car les données StatsBomb ne doivent pas être publiées (voir **Licences et conditions**). Dans **Settings > Pages**, choisir **GitHub Actions** comme source de déploiement. Le workflow `.github/workflows/nextjs.yml` publie la page et ses données à chaque push sur `main`. Cette version lit les fichiers JSON et rejoue les événements dans le navigateur; elle ne nécessite pas le serveur FastAPI.

## Tests

```bash
python -m pytest -q
node --test tests/test_preparation.js
```

Les tests de `tests/test_real_data.py` fonctionnent sans connexion, avec des données synthétiques. Ils couvrent la conversion des événements, l'exclusion de la rencontre rejouée et des matchs ultérieurs, la portée des statistiques, les homonymes Wikidata et l'indisponibilité de Wikidata.

Les tests Python couvrent l’anecdote historique au bon stade, l’absence de suggestion sans correspondance, les informations de temps calme, la limite de trois résultats et les deux joueurs d’un remplacement. Les tests Node couvrent les recherches de préparation, les faits croisés, les choix d’équipe à domicile et à l’extérieur, les combinaisons sans fait croisé, les entrées inconnues et l’affichage d’un fait épinglé dans les deux vues.

## Fonctionnement

- `app/real_data/` contient l'import : `statsbomb.py` télécharge et normalise, `wikidata.py` rapproche les fiches, `facts.py` calcule les faits et les événements, `build.py` enchaîne le tout.
- `app/data/local/` reçoit la base réelle générée. Ce dossier et le cache `.cache/` sont exclus de Git.
- `app/data/demo_data.json` contient, pour la démonstration fictive, la rencontre, les championnats, les équipes, les joueurs, les stades et les fiches factuelles. Chaque fait affiché indique l’identifiant et le libellé de sa source.
- `app/data/match_events.json` définit les événements horodatés. `delay_seconds` règle leur délai de rejeu en temps réel; une pause de contexte est envoyée au milieu des délais d’au moins trois secondes.
- `app/selector.py` est le moteur déterministe isolé. Il filtre par déclencheur et identifiants ciblés, puis classe par priorité et spécificité. Il retourne zéro à trois faits existants avec leur source.
- `app/static/preparation.js` contient les règles de recherche par entité, le classement des faits et la persistance des épingles dans le stockage local du navigateur.
- `app/main.py` expose l’API FastAPI et diffuse les instants du match au navigateur par Server-Sent Events (SSE).
- `app/static/` contient l’interface en HTML, CSS et JavaScript natifs.
- `tests/test_selector.py` teste les règles sans dépendre du serveur.

Les événements `temps_mort` et les interruptions de jeu calme sont des ressorts de simulation pour la démonstration; le temps mort n’est pas une règle standard du football.

## Règles sur les faits réels

- Un fait ne repose que sur les matchs joués avant la date de la rencontre rejouée, pour ne rien dévoiler de la suite du match.
- Chaque statistique annonce sa portée (« sur les matchs disponibles… ») et chaque fait indique sa source : les matchs StatsBomb concernés ou la fiche Wikidata.
- Les tirs au but ne comptent ni dans les buts ni dans les bilans. Une rencontre décidée aux tirs au but compte comme un nul.
- L'outil n'écrit jamais « record » ou « première fois », car les données sont partielles.
- Une fiche Wikidata n'est retenue que si elle est la seule à correspondre au nom, au métier de footballeur et au pays. Sinon, aucun fait n'est produit et le cas est indiqué à la fin de l'import.
- L'import compare les buts relevés au score officiel de chaque match et signale tout écart.

## Licences et conditions

- **StatsBomb Open Data** : son [contrat d'utilisation](https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf) interdit notamment de distribuer les données à des tiers et de les exploiter commercialement, ainsi que les analyses qui en découlent. Il demande de créditer StatsBomb avec son logo, que l'interface affiche, et invite chaque utilisateur à s'enregistrer sur le site de StatsBomb. **Ne jamais committer `app/data/local/`, `.cache/` ni un extrait de ces fichiers dans ce dépôt public.** Chaque personne génère ses données avec l'import.
- **Wikidata** : les données structurées sont publiées sous licence CC0.

Passe D ne peut donc pas être vendu avec les données StatsBomb sans accord écrit de StatsBomb ou changement de fournisseur.

## Limites

Les données réelles portent sur des matchs passés, sans flux en direct. Les faits sont des statistiques calculées, pas des anecdotes rédigées, et ils se limitent aux compétitions importées. Les noms de joueurs sont ceux de StatsBomb, parfois abrégés ou sans accent. Une carte ou une minute peuvent différer d'autres sources, et les temps additionnels s'affichent en minutes continues (par exemple 51’ pour 45+6).

La démonstration fictive reste petite, statique et écrite à la main. Les épingles sont conservées dans le stockage local du navigateur. Les règles sont à valider avec des commentateurs avant toute utilisation réelle.
