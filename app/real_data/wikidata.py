"""Rapprochement prudent avec Wikidata.

Une fiche n'est retenue que si elle est la seule à correspondre sur plusieurs indices.
En cas de doute, ou si Wikidata ne répond pas, aucun fait n'est produit.
"""

import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from app.real_data.statsbomb import USER_AGENT

API_URL = "https://www.wikidata.org/w/api.php"
FOOTBALLER = "Q937857"
HUMAN = "Q5"
MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
    "août", "septembre", "octobre", "novembre", "décembre",
]


class WikidataClient:
    def __init__(self, cache_dir, pause=0.2):
        self.cache_dir = Path(cache_dir)
        self.pause = pause

    def get(self, params):
        query = urllib.parse.urlencode({**params, "format": "json"}, doseq=True)
        cached = self.cache_dir / f"{hashlib.sha256(query.encode()).hexdigest()}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        request = urllib.request.Request(f"{API_URL}?{query}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
        time.sleep(self.pause)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(payload)
        return json.loads(payload)

    def search(self, name):
        data = self.get({"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 10})
        return [item["id"] for item in data.get("search", [])]

    def entities(self, ids):
        found = {}
        ids = list(dict.fromkeys(ids))
        for start in range(0, len(ids), 50):
            data = self.get({
                "action": "wbgetentities",
                "ids": "|".join(ids[start:start + 50]),
                "props": "claims|labels",
                "languages": "fr|en",
            })
            found.update(data.get("entities", {}))
        return found


def _claims(entity, prop):
    """Valeurs du meilleur rang, sans les valeurs dépréciées."""
    claims = [claim for claim in entity.get("claims", {}).get(prop, []) if claim.get("rank") != "deprecated"]
    preferred = [claim for claim in claims if claim.get("rank") == "preferred"]
    values = []
    for claim in preferred or claims:
        snak = claim.get("mainsnak", {})
        if snak.get("snaktype") == "value":
            values.append(snak["datavalue"]["value"])
    return values


def _item_ids(entity, prop):
    return [value["id"] for value in _claims(entity, prop) if isinstance(value, dict) and "id" in value]


def _label(entity, language="en"):
    return entity.get("labels", {}).get(language, {}).get("value", "")


def _country_matches(country, label):
    country, label = country.lower(), label.lower()
    return bool(country and label) and (country in label or label in country)


def _safe_candidates(client, name):
    ids = client.search(name)
    return client.entities(ids) if ids else {}


def resolve_player(client, name, country):
    """Retourne (qid, fiche) si un seul footballeur correspond au nom et au pays."""
    if not country:
        return None
    candidates = _safe_candidates(client, name)
    plausible = {
        qid: entity for qid, entity in candidates.items()
        if HUMAN in _item_ids(entity, "P31") and FOOTBALLER in _item_ids(entity, "P106")
    }
    linked_ids = [
        linked for entity in plausible.values()
        for prop in ("P27", "P1532", "P54")
        for linked in _item_ids(entity, prop)
    ]
    labels = client.entities(linked_ids) if linked_ids else {}

    accepted = []
    for qid, entity in plausible.items():
        national = [_label(labels.get(item, {})) for prop in ("P27", "P1532") for item in _item_ids(entity, prop)]
        teams = [_label(labels.get(item, {})) for item in _item_ids(entity, "P54")]
        if any(_country_matches(country, label) for label in national) or any(
            "national" in label.lower() and _country_matches(country, label) for label in teams
        ):
            accepted.append((qid, entity))
    return accepted[0] if len(accepted) == 1 else None


def resolve_stadium(client, name, country):
    """Retourne (qid, fiche) si un seul stade correspond au nom et au pays."""
    if not country:
        return None
    candidates = _safe_candidates(client, name)
    linked_ids = [item for entity in candidates.values() for prop in ("P31", "P17") for item in _item_ids(entity, prop)]
    labels = client.entities(linked_ids) if linked_ids else {}

    accepted = []
    for qid, entity in candidates.items():
        kinds = [_label(labels.get(item, {})).lower() for item in _item_ids(entity, "P31")]
        countries = [_label(labels.get(item, {})) for item in _item_ids(entity, "P17")]
        if any("stadium" in kind or "arena" in kind for kind in kinds) and any(
            _country_matches(country, label) for label in countries
        ):
            accepted.append((qid, entity))
    return accepted[0] if len(accepted) == 1 else None


def birth_date(entity):
    """Date de naissance, seulement si elle est unique et précise au jour près."""
    values = _claims(entity, "P569")
    if len(values) != 1 or values[0].get("precision") != 11:
        return None
    return date.fromisoformat(values[0]["time"].lstrip("+")[:10])


def format_date(value):
    day = "1er" if value.day == 1 else str(value.day)
    return f"{day} {MONTHS[value.month - 1]} {value.year}"


def age_on(born, day):
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


def single_place_label(client, entity, prop):
    """Libellé français d'un lieu, seulement s'il est unique."""
    ids = _item_ids(entity, prop)
    if len(ids) != 1:
        return None
    place = client.entities(ids).get(ids[0], {})
    return _label(place, "fr") or None


def single_quantity(entity, prop):
    """Valeur numérique unique, par exemple une capacité."""
    values = _claims(entity, prop)
    if len(values) != 1:
        return None
    return int(float(values[0]["amount"]))


def single_year(entity, prop):
    values = _claims(entity, prop)
    if len(values) != 1 or values[0].get("precision", 0) < 9:
        return None
    return int(values[0]["time"].lstrip("+")[:4])
