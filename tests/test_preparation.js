const assert = require('node:assert/strict');
const test = require('node:test');

const database = require('../app/data/demo_data.json');
const {
  searchPreparation,
  readPinnedFacts,
  togglePinnedFact,
  renderPinnedFacts,
} = require('../app/static/preparation.js');

function createStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.get(key) || null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
  };
}

test('une recherche sur un seul joueur retourne ses faits propres', () => {
  const result = searchPreparation({ player: 'Inès Vela' }, database);

  assert.equal(result.error, '');
  assert(result.factCount >= 2);
  assert(result.groups.some((group) => group.id === 'player'));
});

test('chaque joueur et chaque championnat de démo ont plusieurs faits personnels', () => {
  for (const player of database.players) {
    const result = searchPreparation({ player: player.name }, database);
    assert(result.groups.find((group) => group.id === 'player').facts.length >= 2, player.name);
  }
  for (const competition of database.competitions) {
    const result = searchPreparation({ competition: competition.name }, database);
    assert(result.groups.find((group) => group.id === 'competition').facts.length >= 2, competition.name);
  }
});

test('joueurs, équipes et rencontre référencent des championnats connus', () => {
  const competitionIds = new Set(database.competitions.map((item) => item.id));
  assert(competitionIds.has(database.match.competition_id));
  for (const team of database.teams) {
    assert(team.competition_ids.every((id) => competitionIds.has(id)), team.name);
  }
  for (const player of database.players) {
    assert(player.competition_ids.every((id) => competitionIds.has(id)), player.name);
  }
});

test('trois champs renseignés font remonter des faits croisés', () => {
  const result = searchPreparation({
    player: 'Inès Vela',
    competition: 'Ligue des Rives',
    stadium: 'Parc des Brumes',
  }, database);

  const crossGroup = result.groups.find((group) => group.id === 'cross');
  assert(crossGroup);
  assert(crossGroup.facts.length > 0);
  assert(crossGroup.facts.every((fact) => fact.source_id && fact.source_label));
  const recordIndex = crossGroup.facts.findIndex((fact) => fact.source_id === 'prep-ines-ligue-brumes-01');
  const performanceIndex = crossGroup.facts.findIndex((fact) => fact.source_id === 'prep-ines-ligue-01');
  assert(recordIndex >= 0 && performanceIndex >= 0);
  assert(recordIndex < performanceIndex);
});

test('un élément inconnu affiche une erreur claire', () => {
  const result = searchPreparation({ player: 'Joueur introuvable' }, database);

  assert.match(result.error, /Aucun joueur de la base/);
  assert.equal(result.factCount, undefined);
});

test('une combinaison sans fait croisé conserve ses faits propres et le signale', () => {
  const result = searchPreparation({
    player: 'Noé Sorin',
    competition: 'Coupe des Rives',
    stadium: 'Stade du Canal',
  }, database);

  const crossGroup = result.groups.find((group) => group.id === 'cross');
  assert(crossGroup);
  assert.equal(crossGroup.facts.length, 0);
  assert.match(crossGroup.message, /Aucun fait disponible/);
  assert(result.factCount > 0);
});

test('un fait épinglé reste visible dans les fiches Préparation et Direct', () => {
  const storage = createStorage();
  const fact = {
    source_id: 'prep-ines-ligue-01',
    source_label: 'Historique fictif · Inès Vela',
    title: 'Bilan en championnat',
    fact: 'Inès Vela a inscrit 5 buts en 7 apparitions.',
  };
  const pin = togglePinnedFact(fact, storage);
  const liveCards = [];
  const preparationCards = [];
  const container = (cards) => ({
    replaceChildren() {
      cards.length = 0;
    },
    append(card) {
      cards.push(card);
    },
  });

  assert.equal(pin.pinned, true);
  const pinnedFacts = readPinnedFacts(storage);
  renderPinnedFacts(container(liveCards), pinnedFacts, (pinnedFact) => ({ text: pinnedFact.fact }));
  renderPinnedFacts(container(preparationCards), pinnedFacts, (pinnedFact) => ({ text: pinnedFact.fact }));

  assert.equal(liveCards[0].text, fact.fact);
  assert.equal(preparationCards[0].text, fact.fact);
});