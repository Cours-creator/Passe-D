"""Calcul des faits à partir des matchs réels, au format de la base de Passe D.

Règles :
- un fait ne repose que sur les matchs joués avant la rencontre rejouée ;
- chaque statistique annonce sa portée ;
- les tirs au but ne comptent ni dans les buts ni dans les bilans ;
- aucune formule absolue (« record », « première fois ») n'est produite.
"""

from collections import defaultdict
from datetime import date

from app.real_data import wikidata as wd
from app.real_data.statsbomb import SHOOTOUT_PERIOD

TEAM_NAMES = {
    "Argentina": "Argentine", "Australia": "Australie", "Belgium": "Belgique", "Brazil": "Brésil",
    "Cameroon": "Cameroun", "Canada": "Canada", "Colombia": "Colombie", "Costa Rica": "Costa Rica",
    "Croatia": "Croatie", "Denmark": "Danemark", "Ecuador": "Équateur", "Egypt": "Égypte",
    "England": "Angleterre", "France": "France", "Germany": "Allemagne", "Ghana": "Ghana",
    "Iceland": "Islande", "Iran": "Iran", "Japan": "Japon", "Mexico": "Mexique", "Morocco": "Maroc",
    "Netherlands": "Pays-Bas", "Nigeria": "Nigeria", "Panama": "Panama", "Peru": "Pérou",
    "Poland": "Pologne", "Portugal": "Portugal", "Qatar": "Qatar", "Russia": "Russie",
    "Saudi Arabia": "Arabie saoudite", "Senegal": "Sénégal", "Serbia": "Serbie",
    "South Korea": "Corée du Sud", "Spain": "Espagne", "Sweden": "Suède", "Switzerland": "Suisse",
    "Tunisia": "Tunisie", "United States": "États-Unis", "Uruguay": "Uruguay", "Wales": "Pays de Galles",
}
STAGE_NAMES = {
    "Group Stage": "phase de groupes", "Round of 16": "8e de finale", "Quarter-finals": "quart de finale",
    "Semi-finals": "demi-finale", "3rd Place Final": "match pour la 3e place", "Final": "finale",
}
COMPETITION_NAMES = {"FIFA World Cup": "Coupe du monde"}
PLAYER_TRIGGERS = ["goal", "substitution", "yellow_card", "red_card", "shootout"]
CONTEXT_TRIGGERS = ["calm", "timeout"]


def plural(count, singular, plural_form=None):
    return f"{count} {singular if count in (0, 1) else (plural_form or singular + 's')}"


def team_name(name):
    return TEAM_NAMES.get(name, name)


def stage_name(stage):
    return STAGE_NAMES.get(stage, stage or "phase inconnue")


def competition_id(summary):
    return f"comp-{summary['competition_id']}-{summary['season_id']}"


def competition_name(summary):
    name = COMPETITION_NAMES.get(summary["competition_name"], summary["competition_name"])
    return f"{name} {summary['season_name']}"


def player_ref(player_id):
    return f"player-{player_id}"


def team_ref(team_id):
    return f"team-{team_id}"


def stadium_ref(stadium_id):
    return f"stadium-{stadium_id}"


def match_goals(summary):
    """Buts du match, hors tirs au but."""
    return [
        event for event in summary["key_events"]
        if event["kind"] in ("goal", "own_goal") and event["period"] != SHOOTOUT_PERIOD
    ]


def statsbomb_source(match_ids):
    match_ids = sorted(set(match_ids))
    shown = ", ".join(str(item) for item in match_ids[:4])
    suffix = f" et {len(match_ids) - 4} autres" if len(match_ids) > 4 else ""
    label = "match" if len(match_ids) == 1 else "matchs"
    return f"StatsBomb Open Data · {label} {shown}{suffix}"


class FactBuilder:
    """Accumule les fiches au format attendu par le sélecteur et la préparation."""

    def __init__(self):
        self.records = []

    def add(self, record_id, source, title, fact, category, prep_targets, interest="statistic",
            triggers=None, targets=None, priority=0):
        self.records.append({
            "id": record_id,
            "source_label": source,
            "title": title,
            "fact": fact,
            "triggers": triggers or [],
            "targets": targets or {},
            "priority": priority,
            "preparation": {"category": category, "interest": interest, "targets": prep_targets},
        })


def _history(summaries, target):
    """Matchs joués strictement avant la rencontre rejouée."""
    return [
        summary for summary in summaries
        if summary["date"] < target["date"]
    ]


def _player_stats(matches):
    stats = defaultdict(lambda: {"matches": [], "goals": 0, "penalties": 0, "goal_matches": []})
    for summary in matches:
        for player_id in summary["appearances"]:
            stats[player_id]["matches"].append(summary)
        for event in match_goals(summary):
            if event["kind"] == "goal" and event["player_id"]:
                entry = stats[event["player_id"]]
                entry["goals"] += 1
                entry["penalties"] += 1 if event.get("penalty") else 0
                entry["goal_matches"].append(summary)
    return stats


def _goals_text(goals, penalties):
    text = plural(goals, "but")
    return f"{text} (dont {penalties} sur penalty)" if penalties else text


def _team_record(team_id, matches):
    wins = draws = losses = scored = conceded = 0
    for summary in matches:
        at_home = summary["home"]["id"] == team_id
        own = summary["home_score"] if at_home else summary["away_score"]
        other = summary["away_score"] if at_home else summary["home_score"]
        scored += own
        conceded += other
        wins += own > other
        draws += own == other
        losses += own < other
    return (
        f"{plural(len(matches), 'match', 'matchs')}, {plural(wins, 'victoire')}, {plural(draws, 'nul')}, "
        f"{plural(losses, 'défaite')}, {plural(scored, 'but marqué', 'buts marqués')}, "
        f"{plural(conceded, 'but encaissé', 'buts encaissés')}"
    )


def build_database(summaries, target, wikidata_client=None, log=print):
    """Construit la base et les événements de la rencontre rejouée."""
    history = _history(summaries, target)
    scoped = sorted({competition_name(item) for item in history})
    target_comp = competition_id(target)
    before = "avant cette rencontre"
    target_players = {int(key) for key in target["players"]}
    target_teams = {target["home"]["id"], target["away"]["id"]}
    target_stadium = target["stadium"]["id"]
    scope = f"sur les matchs disponibles de {' et '.join(scoped)}, {before}"
    builder = FactBuilder()

    players, teams, stadiums, competitions = {}, {}, {}, {}
    for summary in [*history, target]:
        comp = competitions.setdefault(competition_id(summary), {
            "id": competition_id(summary), "name": competition_name(summary),
            "season": summary["season_name"], "team_ids": set(),
        })
        for side in ("home", "away"):
            teams.setdefault(summary[side]["id"], {
                "id": team_ref(summary[side]["id"]), "name": team_name(summary[side]["name"]),
                "competition_ids": set(),
            })["competition_ids"].add(comp["id"])
            comp["team_ids"].add(team_ref(summary[side]["id"]))
        if summary["stadium"]:
            stadiums.setdefault(summary["stadium"]["id"], {
                "id": stadium_ref(summary["stadium"]["id"]), "name": summary["stadium"]["name"],
                "country": summary["stadium"]["country"],
            })
        for player in summary["players"].values():
            entry = players.setdefault(player["id"], {
                "id": player_ref(player["id"]), "name": player["name"], "country": player["country"],
                "team_id": team_ref(player["team_id"]), "number": player["number"], "competition_ids": set(),
            })
            entry["competition_ids"].add(comp["id"])
            if summary["id"] == target["id"]:
                entry.update(team_id=team_ref(player["team_id"]), number=player["number"])

    # Deux joueurs homonymes restent distincts dans l'autocomplétion.
    by_name = defaultdict(list)
    for player in players.values():
        by_name[player["name"]].append(player)
    for homonyms in by_name.values():
        if len(homonyms) > 1:
            for player in homonyms:
                player["name"] = f"{player['name']} ({player['country']})"

    def player_triggers(player_id):
        return PLAYER_TRIGGERS if player_id in target_players else []

    # Joueurs : bilan global, par compétition, par stade et par adversaire.
    overall = _player_stats(history)
    for player_id, stat in overall.items():
        player = players.get(player_id)
        if not player or not stat["matches"]:
            continue
        ref = player["id"]
        name = player["name"]
        builder.add(
            f"sb-player-{player_id}", statsbomb_source(item["id"] for item in stat["matches"]),
            "Bilan du joueur",
            f"{name} : {_goals_text(stat['goals'], stat['penalties'])} en "
            f"{plural(len(stat['matches']), 'match', 'matchs')} {scope}.",
            "player", {"player_id": ref}, "performance",
            player_triggers(player_id), {"player_id": ref}, 30,
        )

        by_competition = defaultdict(list)
        by_stadium = defaultdict(list)
        by_opponent = defaultdict(list)
        for summary in stat["matches"]:
            by_competition[competition_id(summary)].append(summary)
            if summary["stadium"]:
                by_stadium[summary["stadium"]["id"]].append(summary)
            team_id = summary["players"][str(player_id)]["team_id"]
            opponent = summary["away"] if summary["home"]["id"] == team_id else summary["home"]
            by_opponent[opponent["id"]].append(summary)

        def goals_in(matches):
            ids = {item["id"] for item in matches}
            goals = [item for item in stat["goal_matches"] if item["id"] in ids]
            penalties = sum(
                1 for item in matches for event in match_goals(item)
                if event["kind"] == "goal" and event["player_id"] == player_id and event.get("penalty")
            )
            return len(goals), penalties

        for comp_id, matches in by_competition.items():
            goals, penalties = goals_in(matches)
            comp_name = competitions[comp_id]["name"]
            suffix = f", {before}" if comp_id == target_comp else ""
            is_live = comp_id == target_comp and player_id in target_players
            builder.add(
                f"sb-player-{player_id}-{comp_id}", statsbomb_source(item["id"] for item in matches),
                f"Bilan en {comp_name}",
                f"{name} : {_goals_text(goals, penalties)} en {plural(len(matches), 'match', 'matchs')} "
                f"sur les matchs disponibles de {comp_name}{suffix}.",
                "cross", {"player_id": ref, "competition_id": comp_id}, "performance",
                PLAYER_TRIGGERS if is_live else [], {"player_id": ref} if is_live else {}, 50,
            )

        for stadium_id, matches in by_stadium.items():
            goals, penalties = goals_in(matches)
            stadium = stadiums[stadium_id]
            is_live = stadium_id == target_stadium and player_id in target_players
            verb = f"y a marqué {_goals_text(goals, penalties)}" if goals else "n'y a pas marqué"
            builder.add(
                f"sb-player-{player_id}-stadium-{stadium_id}", statsbomb_source(item["id"] for item in matches),
                "Un stade qui lui réussit" if goals else "Déjà joué dans ce stade",
                f"{before.capitalize()}, {name} a disputé {plural(len(matches), 'match', 'matchs')} à "
                f"{stadium['name']} et {verb}, {scope.split(', ')[0]}.",
                "cross", {"player_id": ref, "stadium_id": stadium["id"]}, "record" if goals else "statistic",
                PLAYER_TRIGGERS if is_live else [],
                {"player_id": ref, "stadium_id": stadium["id"]} if is_live else {},
                100 if goals else 40,
            )

        for opponent_id, matches in by_opponent.items():
            goals, penalties = goals_in(matches)
            is_target_duel = opponent_id in target_teams and player_id in target_players
            if not goals and not is_target_duel:
                continue
            opponent = teams[opponent_id]
            is_live = is_target_duel and summary_team(player_id, target) != opponent_id
            builder.add(
                f"sb-player-{player_id}-vs-{opponent_id}", statsbomb_source(item["id"] for item in matches),
                "Face à cet adversaire",
                f"Adversaire {opponent['name']} : {name} compte {plural(len(matches), 'match', 'matchs')} et "
                f"{_goals_text(goals, penalties)} {scope}.",
                "cross", {"player_id": ref, "team_id": opponent["id"]}, "record" if goals else "statistic",
                PLAYER_TRIGGERS if is_live else [],
                {"player_id": ref, "match_id": target["id"]} if is_live else {},
                90 if goals else 45,
            )

    # Équipes : bilan global, par compétition et par stade.
    team_matches = defaultdict(list)
    for summary in history:
        team_matches[summary["home"]["id"]].append(summary)
        team_matches[summary["away"]["id"]].append(summary)
    note = "Les tirs au but ne sont pas comptés."
    for team_id, matches in team_matches.items():
        team = teams[team_id]
        is_target = team_id in target_teams
        builder.add(
            f"sb-team-{team_id}", statsbomb_source(item["id"] for item in matches),
            "Bilan de l'équipe",
            f"{team['name']} : {_team_record(team_id, matches)} {scope}. {note}",
            "team", {"team_id": team["id"]}, "performance",
            CONTEXT_TRIGGERS if is_target else [], {"team_id": team["id"]} if is_target else {}, 20,
        )
        per_comp = defaultdict(list)
        per_stadium = defaultdict(list)
        for summary in matches:
            per_comp[competition_id(summary)].append(summary)
            if summary["stadium"]:
                per_stadium[summary["stadium"]["id"]].append(summary)
        for comp_id, group in per_comp.items():
            comp_name = competitions[comp_id]["name"]
            suffix = f", {before}" if comp_id == target_comp else ""
            live = is_target and comp_id == target_comp
            builder.add(
                f"sb-team-{team_id}-{comp_id}", statsbomb_source(item["id"] for item in group),
                "Son parcours" if live else f"Bilan en {comp_name}",
                f"{team['name']} sur les matchs disponibles de {comp_name}{suffix} : {_team_record(team_id, group)}. {note}",
                "cross", {"team_id": team["id"], "competition_id": comp_id}, "performance",
                CONTEXT_TRIGGERS if live else [], {"team_id": team["id"]} if live else {}, 40,
            )
        for stadium_id, group in per_stadium.items():
            stadium = stadiums[stadium_id]
            live = is_target and stadium_id == target_stadium
            builder.add(
                f"sb-team-{team_id}-stadium-{stadium_id}", statsbomb_source(item["id"] for item in group),
                "Déjà passée par ce stade",
                f"{team['name']} à {stadium['name']}, {before} : {_team_record(team_id, group)}. {note}",
                "cross", {"team_id": team["id"], "stadium_id": stadium["id"]}, "record",
                CONTEXT_TRIGGERS if live else [],
                {"team_id": team["id"], "stadium_id": stadium["id"]} if live else {}, 60,
            )

    # Confrontations directes, dans les deux sens pour les champs domicile et extérieur.
    duels = defaultdict(list)
    for summary in history:
        duels[frozenset((summary["home"]["id"], summary["away"]["id"]))].append(summary)
    for pair, matches in duels.items():
        first, second = sorted(pair)
        details = "; ".join(
            f"{stage_name(item['stage'])} de {competition_name(item)} : {team_name(item['home']['name'])} "
            f"{item['home_score']}-{item['away_score']} {team_name(item['away']['name'])}"
            for item in sorted(matches, key=lambda value: value["date"])
        )
        is_target = pair == frozenset(target_teams)
        fact = f"{plural(len(matches), 'confrontation')} {scope} : {details}."
        for home_id, away_id in ((first, second), (second, first)):
            live = is_target and home_id == target["home"]["id"]
            builder.add(
                f"sb-duel-{home_id}-{away_id}", statsbomb_source(item["id"] for item in matches),
                "Déjà vu entre ces deux équipes", fact, "cross",
                {"home_team_id": team_ref(home_id), "away_team_id": team_ref(away_id)}, "record",
                [*CONTEXT_TRIGGERS, "goal"] if live else [], {"match_id": target["id"]} if live else {}, 70,
            )

    # Stades et compétitions.
    stadium_matches = defaultdict(list)
    for summary in history:
        if summary["stadium"]:
            stadium_matches[summary["stadium"]["id"]].append(summary)
    for stadium_id, matches in stadium_matches.items():
        stadium = stadiums[stadium_id]
        live = stadium_id == target_stadium
        goals = sum(len(match_goals(item)) for item in matches)
        builder.add(
            f"sb-stadium-{stadium_id}", statsbomb_source(item["id"] for item in matches),
            "Le stade en chiffres",
            f"{stadium['name']} : {plural(len(matches), 'match', 'matchs')} et {plural(goals, 'but')} {scope}.",
            "stadium", {"stadium_id": stadium["id"]}, "performance",
            CONTEXT_TRIGGERS if live else [], {"stadium_id": stadium["id"]} if live else {}, 35,
        )

    comp_matches = defaultdict(list)
    for summary in history:
        comp_matches[competition_id(summary)].append(summary)
    for comp_id, matches in comp_matches.items():
        comp = competitions[comp_id]
        live = comp_id == target_comp
        suffix = f", {before}" if comp_id == target_comp else ""
        goals = sum(len(match_goals(item)) for item in matches)
        builder.add(
            f"sb-comp-{comp_id}", statsbomb_source(item["id"] for item in matches),
            "La compétition en chiffres",
            f"{comp['name']} : {plural(len(matches), 'match', 'matchs')} et {plural(goals, 'but')}"
            f" sur les matchs disponibles{suffix}.",
            "competition", {"competition_id": comp_id}, "performance",
            CONTEXT_TRIGGERS if live else [], {"match_id": target["id"]} if live else {}, 30,
        )
        scorers = defaultdict(int)
        for summary in matches:
            for event in match_goals(summary):
                if event["kind"] == "goal" and event["player_id"]:
                    scorers[event["player_id"]] += 1
        if scorers:
            best = max(scorers.values())
            names = sorted(players[player_id]["name"] for player_id, goals in scorers.items() if goals == best)
            builder.add(
                f"sb-comp-{comp_id}-scorers", statsbomb_source(item["id"] for item in matches),
                "Les buteurs de la compétition",
                f"{comp['name']} : {' et '.join(names)} en tête avec {plural(best, 'but')} "
                f"sur les matchs disponibles{suffix}, penalties compris et tirs au but exclus.",
                "competition", {"competition_id": comp_id}, "record",
                CONTEXT_TRIGGERS if live else [], {"match_id": target["id"]} if live else {}, 45,
            )

    if wikidata_client:
        _add_wikidata_facts(builder, wikidata_client, players, stadiums, target, target_players, target_stadium, log)

    match_day = date.fromisoformat(target["date"])
    database = {
        "meta": {
            "mode": "real",
            "attribution": "Données : StatsBomb Open Data et Wikidata",
            "scope": scope,
            "match_date": match_day.isoformat(),
            "examples": {
                "player": _example_player(target, players),
                "competition": competitions[target_comp]["name"],
                "stadium": stadiums[target_stadium]["name"],
                "home_team": teams[target["home"]["id"]]["name"],
                "away_team": teams[target["away"]["id"]]["name"],
            },
        },
        "match": {
            "id": target["id"],
            "competition": f"{competitions[target_comp]['name']} · {stage_name(target['stage'])}",
            "competition_id": target_comp,
            "home_team_id": team_ref(target["home"]["id"]),
            "away_team_id": team_ref(target["away"]["id"]),
            "stadium_id": stadium_ref(target_stadium),
            "date": target["date"],
        },
        "competitions": [{**item, "team_ids": sorted(item["team_ids"])} for item in competitions.values()],
        "teams": [{**item, "competition_ids": sorted(item["competition_ids"])} for item in teams.values()],
        "players": sorted(
            ({**item, "competition_ids": sorted(item["competition_ids"])} for item in players.values()),
            key=lambda item: item["name"],
        ),
        "stadiums": list(stadiums.values()),
        "records": builder.records,
    }
    return database, build_events(target, players)


def summary_team(player_id, summary):
    return summary["players"][str(player_id)]["team_id"]


def _example_player(target, players):
    scorers = [event["player_id"] for event in match_goals(target) if event["kind"] == "goal"]
    candidate = scorers[0] if scorers else target["appearances"][0]
    return players[candidate]["name"]


def _add_wikidata_facts(builder, client, players, stadiums, target, target_players, target_stadium, log):
    """Complète avec Wikidata pour les joueurs et le stade de la rencontre."""
    match_day = date.fromisoformat(target["date"])
    unresolved = []
    try:
        for player_id in sorted(target_players):
            player = players[player_id]
            found = wd.resolve_player(client, player["name"].split(" (")[0], player["country"])
            if not found:
                unresolved.append(player["name"])
                continue
            qid, entity = found
            born = wd.birth_date(entity)
            if not born:
                continue
            place = wd.single_place_label(client, entity, "P19")
            where = f" à {place}" if place else ""
            builder.add(
                f"wd-{qid}-birth", f"Wikidata · {qid}", "Repère sur le joueur",
                f"{player['name']} : naissance le {wd.format_date(born)}{where}, "
                f"{wd.age_on(born, match_day)} ans le jour de cette rencontre.",
                "player", {"player_id": player["id"]}, "statistic",
                PLAYER_TRIGGERS, {"player_id": player["id"]}, 25,
            )

        stadium = stadiums[target_stadium]
        found = wd.resolve_stadium(client, stadium["name"], stadium["country"])
        if not found:
            unresolved.append(stadium["name"])
        else:
            qid, entity = found
            capacity = wd.single_quantity(entity, "P1083")
            opened = wd.single_year(entity, "P1619") or wd.single_year(entity, "P571")
            parts = []
            if capacity:
                parts.append(f"une capacité de {capacity:,} places".replace(",", " "))
            if opened:
                parts.append(f"une ouverture ou une création en {opened}")
            if parts:
                builder.add(
                    f"wd-{qid}-stadium", f"Wikidata · {qid}", "Repère sur le stade",
                    f"Wikidata indique pour {stadium['name']} {' et '.join(parts)}.",
                    "stadium", {"stadium_id": stadium["id"]}, "statistic",
                    CONTEXT_TRIGGERS, {"stadium_id": stadium["id"]}, 30,
                )
    except OSError as error:
        log(f"Wikidata indisponible, import poursuivi sans ses dernières fiches : {error}")
    if unresolved:
        log(f"Rapprochement Wikidata écarté (incertain) pour : {', '.join(unresolved)}")


PERIOD_STARTS = {1: "Coup d'envoi.", 2: "Reprise du jeu.", 3: "Début de la prolongation.",
                 4: "Reprise de la prolongation.", 5: "Début de la séance de tirs au but."}
PERIOD_ENDS = {1: "Mi-temps.", 2: "Fin du temps réglementaire.", 3: "Fin de la première période de prolongation.",
               4: "Fin de la prolongation.", 5: "Fin de la séance de tirs au but."}


def build_events(target, players):
    """Convertit le match en événements rejouables, avec un délai compressé."""
    home_id, away_id = target["home"]["id"], target["away"]["id"]
    names = {home_id: team_name(target["home"]["name"]), away_id: team_name(target["away"]["name"])}
    shootout = {home_id: 0, away_id: 0}
    key_events = target["key_events"]
    last_periods = [event["period"] for event in key_events if event["kind"] == "period_end"]
    final_period = max(last_periods) if last_periods else None

    def player_name(player_id, fallback=None):
        player = players.get(player_id)
        return player["name"] if player else (fallback or "Joueur inconnu")

    events = []
    previous = None
    for event in key_events:
        kind = event["kind"]
        team = names.get(event["team_id"], "")
        player = player_name(event["player_id"], event.get("player_name")) if event.get("player_id") else None
        item = {
            "id": f"evt-{len(events) + 1:03d}",
            "minute": event["minute"],
            "second": event["second"],
            "type": kind,
        }
        if event["team_id"]:
            item["team_id"] = team_ref(event["team_id"])
        if event.get("player_id"):
            item["player_id"] = player_ref(event["player_id"])

        if kind == "goal":
            suffix = " sur penalty" if event.get("penalty") else ""
            item["description"] = f"But de {player} ({team}){suffix}."
        elif kind == "own_goal":
            item["type"] = "goal"
            item["description"] = f"But contre son camp, en faveur de {team}."
        elif kind in ("yellow_card", "red_card"):
            item["description"] = f"{event['card_label']} pour {player} ({team})."
        elif kind == "substitution":
            player_in = player_name(event["player_in_id"], event.get("player_in_name"))
            item["player_out_id"] = player_ref(event["player_id"])
            item["player_in_id"] = player_ref(event["player_in_id"])
            item.pop("player_id", None)
            item["description"] = f"Remplacement pour {team} : {player_in} entre à la place de {player}."
        elif kind == "shootout":
            shootout[event["team_id"]] += 1 if event.get("scored") else 0
            outcome = "réussi" if event.get("scored") else "manqué"
            tally = f"{names[home_id]} {shootout[home_id]}-{shootout[away_id]} {names[away_id]}"
            item["description"] = f"Tir au but {outcome} par {player} ({team}). Séance : {tally}."
        elif kind == "period_start":
            item["description"] = PERIOD_STARTS.get(event["period"], "Reprise du jeu.")
        elif kind == "period_end":
            ended = "Fin du match." if event["period"] == final_period else PERIOD_ENDS.get(event["period"], "Pause.")
            item["description"] = ended

        item["delay_seconds"] = _replay_delay(previous, event)
        previous = event
        events.append(item)
    return events


def _replay_delay(previous, event):
    """Une minute de match dure une seconde de rejeu, entre 1 et 8 secondes."""
    if previous is None:
        return 2
    if previous["period"] != event["period"]:
        return 3
    gap = (event["minute"] * 60 + event["second"]) - (previous["minute"] * 60 + previous["second"])
    return round(min(8, max(1, gap / 60)), 1)
