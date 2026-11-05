"""Génère la base réelle en local : python -m app.real_data.build

Les données produites restent sur la machine (dossiers exclus de Git), car le contrat
StatsBomb interdit de les redistribuer.
"""

import argparse
import json
from pathlib import Path

from app.real_data import statsbomb
from app.real_data.facts import build_database
from app.real_data.wikidata import WikidataClient

ROOT = Path(__file__).parents[2]
CACHE_DIR = ROOT / ".cache"
OUTPUT_DIR = ROOT / "app" / "data" / "local"
WORLD_CUP = 43
DEFAULT_SEASONS = [(WORLD_CUP, 3), (WORLD_CUP, 106)]  # Coupes du monde 2018 et 2022


def parse_season(value):
    competition_id, season_id = value.split(":")
    return int(competition_id), int(season_id)


def choose_target(summaries, match_id=None):
    """La rencontre demandée, sinon la dernière finale disponible."""
    if match_id is not None:
        for summary in summaries:
            if summary["id"] == match_id:
                return summary
        raise SystemExit(f"Le match {match_id} n'est pas dans les saisons importées.")
    finals = [summary for summary in summaries if summary["stage"] == "Final"]
    return max(finals or summaries, key=lambda summary: summary["date"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=parse_season, action="append",
                        help="Compétition et saison StatsBomb, par exemple 43:106. Répétable.")
    parser.add_argument("--match", type=int, help="Identifiant StatsBomb de la rencontre à rejouer.")
    parser.add_argument("--no-wikidata", action="store_true", help="N'interroge pas Wikidata.")
    args = parser.parse_args(argv)

    seasons = args.season or DEFAULT_SEASONS
    print(f"Import StatsBomb : {len(seasons)} saison(s)…")
    summaries = statsbomb.load_summaries(seasons, CACHE_DIR / "statsbomb")
    warnings = [warning for summary in summaries for warning in statsbomb.score_warnings(summary)]
    for warning in warnings:
        print(f"Attention, score incohérent. {warning}")

    target = choose_target(summaries, args.match)
    if not target["stadium"]:
        raise SystemExit("StatsBomb n'indique pas de stade pour cette rencontre, choisis-en une autre.")

    client = None if args.no_wikidata else WikidataClient(CACHE_DIR / "wikidata")
    database, events = build_database(summaries, target, client)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "database.json").write_text(json.dumps(database, ensure_ascii=False), encoding="utf-8")
    (OUTPUT_DIR / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding="utf-8")
    logo = OUTPUT_DIR / "statsbomb-logo.png"
    if not logo.exists():
        logo.write_bytes(statsbomb.download(statsbomb.LOGO_URL))

    print(f"{len(summaries)} matchs lus, {len(database['records'])} faits et {len(events)} événements générés.")
    print(f"Rencontre rejouée : {database['match']['competition']}, match {target['id']}.")
    print(f"Fichiers écrits dans {OUTPUT_DIR} (exclu de Git).")


if __name__ == "__main__":
    main()
