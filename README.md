# Passe D · Prototype de régie football

Passe D est un assistant éditorial qui fournit aux commentateurs des faits vérifiables pendant une rencontre. La démonstration rejoue un match fictif et affiche jusqu'à trois suggestions classées par des règles simples. Elle ne génère pas de faits et ne remplace pas le commentateur.

## Installation

Python 3.10 ou plus récent est nécessaire.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Lancement

À la racine du projet :

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Ouvrir ensuite `http://localhost:8000` dans le navigateur. Dans Codespaces, ouvrir le port 8000 depuis l’onglet **Ports**. Cliquer sur **Lancer le direct** pour rejouer la séquence; **Arrêter** ferme le flux en cours.

## Publication sur GitHub Pages

Le fichier `index.html` à la racine fournit une version statique autonome. Dans **Settings > Pages**, choisir **GitHub Actions** comme source de déploiement. Le workflow `.github/workflows/nextjs.yml` publie la page et ses données à chaque push sur `main`. Cette version lit les fichiers JSON et rejoue les événements dans le navigateur; elle ne nécessite pas le serveur FastAPI.

## Tests

```bash
python -m pytest -q
```

Les tests couvrent l’anecdote historique au bon stade, l’absence de suggestion sans correspondance, les informations de temps calme, la limite de trois résultats et les deux joueurs d’un remplacement.

## Fonctionnement

- `app/data/demo_data.json` contient la rencontre, les équipes, les joueurs, le stade et les fiches factuelles. Chaque fiche possède un identifiant source, des déclencheurs, des cibles et une priorité.
- `app/data/match_events.json` définit les événements horodatés. `delay_seconds` règle leur délai de rejeu en temps réel; une pause de contexte est envoyée au milieu des délais d’au moins trois secondes.
- `app/selector.py` est le moteur déterministe isolé. Il filtre par déclencheur et identifiants ciblés, puis classe par priorité et spécificité. Il retourne zéro à trois faits existants avec leur source.
- `app/main.py` expose l’API FastAPI et diffuse les instants du match au navigateur par Server-Sent Events (SSE).
- `app/static/` contient l’interface en HTML, CSS et JavaScript natifs.
- `tests/test_selector.py` teste les règles sans dépendre du serveur.

Les événements `temps_mort` et les interruptions de jeu calme sont des ressorts de simulation pour la démonstration; le temps mort n’est pas une règle standard du football.

## Limites

Toutes les personnes, équipes, rencontres, statistiques et anecdotes sont fictives. Les données sont petites, statiques et écrites à la main; aucun fournisseur de données, service externe, modèle d’IA, compte utilisateur ou stockage persistant n’est utilisé. Les déclencheurs et poids sont des règles de démonstration, à valider avec des commentateurs et à enrichir avant toute utilisation réelle. Le chronomètre du match suit les horodatages du fichier et le score n’est mis à jour que sur les buts simulés.