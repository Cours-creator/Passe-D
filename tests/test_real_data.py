"""Tests de l'import réel, sans connexion.

Toutes les données ci-dessous sont synthétiques : le contrat StatsBomb interdit de
redistribuer ses fichiers, même sous forme d'extraits dans ce dépôt public.
"""

import json
import re
from pathlib import Path

from app.main import load_data
from app.real_data import statsbomb, wikidata
from app.real_data.facts import build_database, build_events
from app.selector import select_suggestions


def raw_event(index, kind, period=1, minute=10, team=1, player=None, **extra):
    event = {
        "index": index,
        "type": {"name": kind},
        "period": period,
        "minute": minute,
        "second": 0,
        "team": {"id": team},
        **extra,
    }
    if player:
        event["player"] = {"id": player, "name": f"Joueur {player}"}
    return event


def goal(index, player, team=1, period=1, minute=10, penalty=False):
    shot = {"outcome": {"name": "Goal"}, "type": {"name": "Penalty" if penalty else "Open Play"}}
    return raw_event(index, "Shot", period, minute, team, player, shot=shot)


def summary(match_id, date, home_score, away_score, events, stadium=(10, "Stade Test"), home=(1, "France"),
            away=(2, "Argentina"), season=(106, "2022"), stage="Group Stage"):
    players = {
        "100": {"id": 100, "name": "Joueur Cent", "team_id": home[0], "country": "France", "number": 9},
        "200": {"id": 200, "name": "Joueur Deux", "team_id": away[0], "country": "Argentina", "number": 10},
    }
    return {
        "id": match_id,
        "competition_id": 43,
        "competition_name": "FIFA World Cup",
        "season_id": season[0],
        "season_name": season[1],
        "date": date,
        "stage": stage,
        "home": {"id": home[0], "name": home[1]},
        "away": {"id": away[0], "name": away[1]},
        "home_score": home_score,
        "away_score": away_score,
        "stadium": {"id": stadium[0], "name": stadium[1], "country": "Qatar"},
        "players": players,
        "appearances": [100, 200],
        "key_events": statsbomb.extract_key_events(events),
    }


def sample_summaries():
    past = summary(1, "2018-06-30", 2, 1, [goal(1, 100), goal(2, 100, penalty=True), goal(3, 200, team=2)],
                   season=(3, "2018"), stage="Round of 16")
    target = summary(2, "2022-12-18", 1, 0, [goal(1, 100)], stage="Final")
    return [past, target], target


def find_record(database, record_id):
    return next(record for record in database["records"] if record["id"] == record_id)


def test_tirs_au_but_et_buts_contre_son_camp_sont_distingues():
    events = statsbomb.extract_key_events([
        goal(1, 100),
        raw_event(2, "Own Goal For", team=2),
        raw_event(3, "Own Goal Against", team=1, player=100),
        goal(4, 200, team=2, period=statsbomb.SHOOTOUT_PERIOD),
    ])

    assert [event["kind"] for event in events] == ["goal", "own_goal", "shootout"]
    assert events[1]["player_id"] is None


def test_cartons_remplacements_et_periodes_sont_normalises():
    events = statsbomb.extract_key_events([
        raw_event(1, "Half Start", team=1),
        raw_event(2, "Half Start", team=2),
        raw_event(3, "Foul Committed", player=100, foul_committed={"card": {"name": "Yellow Card"}}),
        raw_event(4, "Bad Behaviour", player=200, bad_behaviour={"card": {"name": "Second Yellow"}}),
        raw_event(5, "Foul Committed", player=100, foul_committed={}),
        raw_event(6, "Substitution", player=100, substitution={"replacement": {"id": 101, "name": "Entrant"}}),
    ])

    assert [event["kind"] for event in events] == ["period_start", "yellow_card", "red_card", "substitution"]
    assert events[3]["player_in_id"] == 101


def test_un_score_incoherent_est_signale():
    good, target = sample_summaries()[0][0], sample_summaries()[1]
    wrong = {**target, "home_score": 5}

    assert statsbomb.score_warnings(good) == []
    assert "5-0 annoncé" in statsbomb.score_warnings(wrong)[0]


def test_la_rencontre_rejouee_n_alimente_pas_les_faits():
    summaries, target = sample_summaries()
    database, _ = build_database(summaries, target)

    fact = find_record(database, "sb-player-100")["fact"]
    assert "2 buts (dont 1 sur penalty) en 1 match " in fact


def test_un_match_futur_est_ignore():
    summaries, target = sample_summaries()
    future = summary(3, "2023-01-01", 9, 0, [goal(index, 100) for index in range(9)])
    database, _ = build_database([*summaries, future], target)

    assert "2 buts" in find_record(database, "sb-player-100")["fact"]


def test_le_but_au_bon_stade_remonte_en_premier():
    summaries, target = sample_summaries()
    database, _ = build_database(summaries, target)

    suggestions = select_suggestions(
        {"type": "goal", "player_id": "player-100", "stadium_id": "stadium-10", "match_id": 2, "team_id": "team-1"},
        database,
    )

    assert suggestions[0]["source_id"] == "sb-player-100-stadium-10"
    assert "StatsBomb Open Data · match 1" == suggestions[0]["source_label"]
    assert len(suggestions) == 3


def test_chaque_fait_a_une_source_une_portee_et_aucune_formule_absolue():
    summaries, target = sample_summaries()
    database, _ = build_database(summaries, target)

    assert database["records"]
    for record in database["records"]:
        assert record["source_label"].startswith("StatsBomb Open Data")
        assert "disponibles" in record["fact"] or "avant cette rencontre" in record["fact"]
        assert not re.search(r"record|première fois|histoire|meilleur", record["fact"], re.IGNORECASE)


def test_la_confrontation_directe_est_trouvable_dans_les_deux_sens():
    summaries, target = sample_summaries()
    database, _ = build_database(summaries, target)

    first = find_record(database, "sb-duel-1-2")
    second = find_record(database, "sb-duel-2-1")
    assert first["fact"] == second["fact"]
    assert "France 2-1 Argentine" in first["fact"]
    assert "8e de finale" in first["fact"]


def test_les_homonymes_restent_distincts():
    summaries, target = sample_summaries()
    for item in summaries:
        item["players"]["200"]["name"] = "Joueur Cent"
    database, _ = build_database(summaries, target)

    assert {player["name"] for player in database["players"]} == {"Joueur Cent (France)", "Joueur Cent (Argentina)"}


def test_les_evenements_rejouables_gardent_le_bon_score():
    target = summary(2, "2022-12-18", 1, 1, [
        raw_event(1, "Half Start", team=1),
        goal(2, 100, minute=20),
        raw_event(3, "Own Goal For", team=2, minute=21),
        raw_event(4, "Substitution", team=1, player=100, minute=60,
                  substitution={"replacement": {"id": 200, "name": "Entrant"}}),
        goal(5, 200, team=2, period=statsbomb.SHOOTOUT_PERIOD, minute=120),
        raw_event(6, "Half End", team=1, period=statsbomb.SHOOTOUT_PERIOD, minute=121),
    ])
    players = {100: {"name": "Joueur Cent"}, 200: {"name": "Joueur Deux"}}

    events = build_events(target, players)

    goals = [event for event in events if event["type"] == "goal"]
    assert [event["team_id"] for event in goals] == ["team-1", "team-2"]
    assert "contre son camp" in goals[1]["description"]
    assert next(event for event in events if event["type"] == "shootout")["description"].endswith("France 0-1 Argentine.")
    assert events[-1]["description"] == "Fin du match."
    assert next(event for event in events if event["type"] == "substitution")["player_in_id"] == "player-200"
    assert all(1 <= event["delay_seconds"] <= 8 for event in events)


class FakeClient:
    """Imite Wikidata : `people` associe un nom aux fiches candidates."""

    def __init__(self, people, labels=None, broken=False):
        self.people = people
        self.labels = labels or {}
        self.broken = broken

    def search(self, name):
        if self.broken:
            raise OSError("Wikidata ne répond pas")
        return list(self.people.get(name, {}))

    def entities(self, ids):
        everything = {key: value for group in self.people.values() for key, value in group.items()}
        everything.update({key: {"labels": {"en": {"value": value}, "fr": {"value": value}}} for key, value in self.labels.items()})
        return {key: everything[key] for key in ids if key in everything}


def claim(value):
    return {"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": value}}}


def player_entity(country_id, born="+1998-12-20T00:00:00Z", precision=11):
    return {
        "claims": {
            "P31": [claim({"id": wikidata.HUMAN})],
            "P106": [claim({"id": wikidata.FOOTBALLER})],
            "P27": [claim({"id": country_id})],
            "P569": [claim({"time": born, "precision": precision})],
        },
    }


LABELS = {"Q142": "France", "Q414": "Argentina"}


def test_un_seul_footballeur_du_bon_pays_est_accepte():
    client = FakeClient({"Joueur Cent": {"Q1": player_entity("Q142"), "Q2": player_entity("Q414")}}, LABELS)

    found = wikidata.resolve_player(client, "Joueur Cent", "France")

    assert found[0] == "Q1"
    assert wikidata.birth_date(found[1]).isoformat() == "1998-12-20"


def test_deux_homonymes_du_meme_pays_sont_ecartes():
    client = FakeClient({"Joueur Cent": {"Q1": player_entity("Q142"), "Q2": player_entity("Q142")}}, LABELS)

    assert wikidata.resolve_player(client, "Joueur Cent", "France") is None


def test_une_fiche_du_mauvais_pays_ou_qui_n_est_pas_un_footballeur_est_ecartee():
    other_job = player_entity("Q142")
    other_job["claims"]["P106"] = [claim({"id": "Q33999"})]
    client = FakeClient({"Joueur Cent": {"Q1": player_entity("Q414"), "Q2": other_job}}, LABELS)

    assert wikidata.resolve_player(client, "Joueur Cent", "France") is None


def test_une_date_imprecise_n_est_pas_utilisee():
    assert wikidata.birth_date(player_entity("Q142", precision=9)) is None


def test_un_rapprochement_incertain_ne_produit_aucun_fait_wikidata():
    summaries, target = sample_summaries()
    client = FakeClient({"Joueur Cent": {"Q1": player_entity("Q142"), "Q2": player_entity("Q142")}}, LABELS)
    messages = []

    database, _ = build_database(summaries, target, client, messages.append)

    assert not [record for record in database["records"] if record["id"].startswith("wd-")]
    assert "Joueur Cent" in messages[0]


def test_un_rapprochement_sur_produit_un_fait_avec_sa_source():
    summaries, target = sample_summaries()
    client = FakeClient({"Joueur Cent": {"Q1": player_entity("Q142")}}, LABELS)

    database, _ = build_database(summaries, target, client, lambda _: None)

    record = find_record(database, "wd-Q1-birth")
    assert record["source_label"] == "Wikidata · Q1"
    assert "20 décembre 1998" in record["fact"]
    assert "23 ans" in record["fact"]


def test_wikidata_indisponible_n_empeche_pas_l_import():
    summaries, target = sample_summaries()
    messages = []

    database, _ = build_database(summaries, target, FakeClient({}, broken=True), messages.append)

    assert database["records"]
    assert "indisponible" in messages[0]


def test_le_serveur_prefere_les_donnees_reelles_si_elles_existent(tmp_path):
    (tmp_path / "demo_data.json").write_text(json.dumps({"origine": "demo"}), encoding="utf-8")
    (tmp_path / "match_events.json").write_text("[]", encoding="utf-8")
    local = tmp_path / "local"

    assert load_data(tmp_path, local)[0]["origine"] == "demo"

    local.mkdir()
    (local / "database.json").write_text(json.dumps({"origine": "reel"}), encoding="utf-8")
    assert load_data(tmp_path, local)[0]["origine"] == "demo", "une base sans événements est incomplète"

    (local / "events.json").write_text("[]", encoding="utf-8")
    assert load_data(tmp_path, local)[0]["origine"] == "reel"


def test_un_fait_deja_propose_peut_etre_exclu():
    database = {"records": [
        {"id": "a", "title": "A", "fact": "A", "triggers": ["calm"], "targets": {}, "priority": 2},
        {"id": "b", "title": "B", "fact": "B", "triggers": ["calm"], "targets": {}, "priority": 1},
    ]}

    assert [item["source_id"] for item in select_suggestions({"type": "calm"}, database, exclude={"a"})] == ["b"]


def test_les_donnees_reelles_sont_exclues_de_git():
    rules = (Path(__file__).parents[1] / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "app/data/local/" in rules
    assert ".cache/" in rules
