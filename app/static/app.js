const startButton = document.querySelector('#start-button');
const stopButton = document.querySelector('#stop-button');
const timeline = document.querySelector('#timeline');
const suggestions = document.querySelector('#suggestions');
const stateLabel = document.querySelector('#connection-state');
const eventCount = document.querySelector('#event-count');
const suggestionCount = document.querySelector('#suggestion-count');
const suggestionIntro = document.querySelector('#suggestion-intro');
const staticMode = document.documentElement.dataset.mode === 'static';
const liveView = document.querySelector('#live-view');
const preparationView = document.querySelector('#preparation-view');
const liveTab = document.querySelector('#live-tab');
const preparationTab = document.querySelector('#preparation-tab');
const preparationForm = document.querySelector('#preparation-form');
const preparationStatus = document.querySelector('#preparation-status');
const preparationResults = document.querySelector('#preparation-results');
const pinnedSection = document.querySelector('#pinned-section');
const pinnedList = document.querySelector('#pinned-list');
const pinnedCount = document.querySelector('#pinned-count');
const preparationPinnedSection = document.querySelector('#preparation-pinned-section');
const preparationPinnedList = document.querySelector('#preparation-pinned-list');
const preparationPinCount = document.querySelector('#preparation-pin-count');

let stream = null;
let demoDatabase = null;
let demoEvents = [];
let score = { home: 0, away: 0 };
let receivedEvents = 0;
let totalEvents = 0;
let replayCancelled = false;
let replayTimer = null;
let cancelDelay = null;
let lastPreparationResult = null;

const labels = {
  goal: 'But',
  yellow_card: 'Carton jaune',
  red_card: 'Carton rouge',
  substitution: 'Remplacement',
  temps_mort: 'Temps mort',
  whistle: 'Coup de sifflet',
  penalty: 'Tir au but',
  penalty_shootout: 'Tir au but',
  calm: 'Temps calme',
};

function showStatus(text, active = false) {
  stateLabel.textContent = text;
  stateLabel.classList.toggle('is-active', active);
}

function resetView() {
  timeline.replaceChildren();
  suggestions.replaceChildren();
  const emptyTimeline = document.createElement('li');
  emptyTimeline.className = 'empty-timeline';
  emptyTimeline.id = 'empty-timeline';
  emptyTimeline.textContent = 'Le fil apparaîtra au lancement de la simulation.';
  timeline.append(emptyTimeline);
  const emptySuggestions = document.createElement('div');
  emptySuggestions.className = 'empty-suggestions';
  emptySuggestions.id = 'empty-suggestions';
  emptySuggestions.textContent = 'En attente du premier temps fort.';
  suggestions.append(emptySuggestions);
  score = { home: 0, away: 0 };
  receivedEvents = 0;
  document.querySelector('#home-score').textContent = '0';
  document.querySelector('#away-score').textContent = '0';
  document.querySelector('#clock').textContent = '--’';
  eventCount.textContent = `0 / ${totalEvents}`;
  suggestionCount.textContent = '0';
  suggestionIntro.textContent = 'Les informations vérifiées apparaîtront ici au fil du jeu.';
}

function addTimelineEntry(event, kind = 'event') {
  const empty = document.querySelector('#empty-timeline');
  if (empty) empty.remove();

  const item = document.createElement('li');
  item.className = 'timeline-entry';
  item.classList.add('is-latest');
  const time = document.createElement('span');
  time.className = 'event-time';
  time.textContent = `${event.minute}’${String(event.second).padStart(2, '0')}`;
  const copy = document.createElement('div');
  copy.className = 'event-copy';
  const type = document.createElement('span');
  type.className = `event-type ${event.type}`;
  type.textContent = labels[event.type] || event.type;
  const text = document.createElement('p');
  text.textContent = event.description;
  copy.append(type, text);
  item.append(time, copy);
  timeline.prepend(item);
  timeline.scrollTop = 0;
  window.setTimeout(() => item.classList.remove('is-latest'), 1700);

  if (event.type === 'goal') {
    if (event.team_id === 'fc-aster') score.home += 1;
    if (event.team_id === 'etoile-nord') score.away += 1;
    document.querySelector('#home-score').textContent = score.home;
    document.querySelector('#away-score').textContent = score.away;
  }
  document.querySelector('#clock').textContent = `${event.minute}’`;
}

function renderSuggestions(items, kind) {
  suggestions.replaceChildren();
  suggestionCount.textContent = String(items.length);
  suggestionIntro.textContent = kind === 'calm'
    ? 'Repères de contexte pour meubler le jeu sans ballon.'
    : 'Faits associés à cet événement, classés par pertinence.';

  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-suggestions';
    empty.textContent = 'Aucun fait vérifié pertinent pour cet instant.';
    suggestions.append(empty);
    return;
  }

  for (const suggestion of items.slice(0, 3)) {
    const card = document.createElement('article');
    card.className = 'suggestion-card';
    const title = document.createElement('h3');
    title.className = 'suggestion-title';
    title.textContent = suggestion.title;
    const fact = document.createElement('p');
    fact.className = 'suggestion-fact';
    fact.textContent = suggestion.fact;
    const source = document.createElement('span');
    source.className = 'suggestion-source';
    source.textContent = `Source : ${suggestion.source_label}`;
    const details = document.createElement('details');
    details.className = 'source-details';
    const summary = document.createElement('summary');
    summary.textContent = 'Détails de vérification';
    const identifier = document.createElement('code');
    identifier.textContent = suggestion.source_id;
    details.append(summary, identifier);
    card.append(title, fact, source, details);
    suggestions.append(card);
  }
}

function setView(view) {
  const showPreparation = view === 'preparation';
  document.body.classList.toggle('preparation-active', showPreparation);
  liveView.hidden = showPreparation;
  preparationView.hidden = !showPreparation;
  liveTab.classList.toggle('is-active', !showPreparation);
  preparationTab.classList.toggle('is-active', showPreparation);
  liveTab.setAttribute('aria-selected', String(!showPreparation));
  preparationTab.setAttribute('aria-selected', String(showPreparation));
}

function populateOptions(listId, items) {
  const list = document.querySelector(`#${listId}`);
  list.replaceChildren();
  for (const item of items) {
    const option = document.createElement('option');
    option.value = item.name;
    list.append(option);
  }
}

function createPreparationCard(fact, pinned = false) {
  const card = document.createElement('article');
  card.className = 'preparation-fact';
  const title = document.createElement('h3');
  title.className = 'preparation-fact-title';
  title.textContent = fact.title;
  const copy = document.createElement('p');
  copy.className = 'preparation-fact-copy';
  copy.textContent = fact.fact;
  const source = document.createElement('span');
  source.className = 'preparation-fact-source';
  source.textContent = `Source : ${fact.source_label}`;
  const details = document.createElement('details');
  details.className = 'source-details';
  const summary = document.createElement('summary');
  summary.textContent = 'Détails de vérification';
  const identifier = document.createElement('code');
  identifier.textContent = fact.source_id;
  details.append(summary, identifier);
  const button = document.createElement('button');
  button.className = 'pin-button';
  button.type = 'button';
  button.setAttribute('aria-pressed', String(pinned));
  button.textContent = pinned ? 'Retirer de la fiche' : 'Épingler pour le match';
  button.addEventListener('click', () => toggleFactPin(fact));
  card.append(title, copy, source, details, button);
  return card;
}

function renderPinnedFacts() {
  const facts = window.PasseDPreparation.readPinnedFacts();
  pinnedSection.hidden = facts.length === 0;
  document.querySelector('#preparation-pin-empty').hidden = facts.length > 0;
  pinnedCount.textContent = String(facts.length);
  preparationPinnedSection.hidden = facts.length === 0;
  preparationPinCount.textContent = `${facts.length} FAIT${facts.length === 1 ? '' : 'S'}`;
  window.PasseDPreparation.renderPinnedFacts(
    pinnedList,
    facts,
    (fact) => createPreparationCard(fact, true),
  );
  window.PasseDPreparation.renderPinnedFacts(
    preparationPinnedList,
    facts,
    (fact) => createPreparationCard(fact, true),
  );
}

function renderPreparationResult(result) {
  preparationResults.replaceChildren();
  preparationStatus.classList.toggle('is-error', Boolean(result.error));
  if (result.error) {
    preparationStatus.textContent = result.error;
    return;
  }

  preparationStatus.textContent = result.factCount
    ? `${result.factCount} fait${result.factCount === 1 ? '' : 's'} trouvé${result.factCount === 1 ? '' : 's'} dans la base.`
    : 'Aucun fait disponible pour cette sélection.';

  const pinnedIds = new Set(window.PasseDPreparation.readPinnedFacts().map((fact) => fact.source_id));
  for (const group of result.groups) {
    const section = document.createElement('section');
    section.className = 'preparation-group';
    const heading = document.createElement('div');
    heading.className = 'preparation-group-head';
    const title = document.createElement('h2');
    title.textContent = group.label;
    const count = document.createElement('span');
    count.className = 'preparation-group-count';
    count.textContent = `${group.facts.length} FAIT${group.facts.length === 1 ? '' : 'S'}`;
    heading.append(title, count);
    section.append(heading);

    if (group.facts.length) {
      const cards = document.createElement('div');
      cards.className = 'preparation-facts';
      for (const fact of group.facts) cards.append(createPreparationCard(fact, pinnedIds.has(fact.source_id)));
      section.append(cards);
    } else {
      const empty = document.createElement('p');
      empty.className = 'preparation-empty';
      empty.textContent = group.message;
      section.append(empty);
    }
    preparationResults.append(section);
  }
}

function toggleFactPin(fact) {
  const result = window.PasseDPreparation.togglePinnedFact(fact);
  if (result.error) {
    preparationStatus.textContent = result.error;
    preparationStatus.classList.add('is-error');
    return;
  }
  renderPinnedFacts();
  if (lastPreparationResult && !lastPreparationResult.error) renderPreparationResult(lastPreparationResult);
}

function searchPreparation(event) {
  event.preventDefault();
  if (!demoDatabase) {
    preparationStatus.textContent = 'La base de démonstration n’est pas encore chargée.';
    preparationStatus.classList.add('is-error');
    return;
  }
  lastPreparationResult = window.PasseDPreparation.searchPreparation({
    player: document.querySelector('#player-input').value,
    competition: document.querySelector('#competition-input').value,
    stadium: document.querySelector('#stadium-input').value,
    homeTeam: document.querySelector('#home-team-input').value,
    awayTeam: document.querySelector('#away-team-input').value,
  }, demoDatabase);
  renderPreparationResult(lastPreparationResult);
}

async function loadMatch() {
  let homeTeam;
  let awayTeam;
  let stadium;
  let competition;

  if (staticMode) {
    const dataUrl = new URL('app/data/demo_data.json', document.baseURI);
    const eventsUrl = new URL('app/data/match_events.json', document.baseURI);
    const [dataResponse, eventsResponse] = await Promise.all([fetch(dataUrl), fetch(eventsUrl)]);
    if (!dataResponse.ok || !eventsResponse.ok) throw new Error('Données de démonstration indisponibles');
    demoDatabase = await dataResponse.json();
    demoEvents = await eventsResponse.json();
    const match = demoDatabase.match;
    homeTeam = demoDatabase.teams.find((team) => team.id === match.home_team_id).name;
    awayTeam = demoDatabase.teams.find((team) => team.id === match.away_team_id).name;
    stadium = demoDatabase.stadiums.find((item) => item.id === match.stadium_id).name;
    competition = match.competition;
    totalEvents = demoEvents.length;
    eventCount.textContent = `0 / ${totalEvents}`;
  } else {
    const [response, databaseResponse] = await Promise.all([fetch('/api/demo'), fetch('/data/demo_data.json')]);
    if (!response.ok || !databaseResponse.ok) throw new Error('Données de rencontre indisponibles');
    const data = await response.json();
    demoDatabase = await databaseResponse.json();
    homeTeam = data.home_team;
    awayTeam = data.away_team;
    stadium = data.stadium;
    competition = data.competition;
  }

  document.querySelector('#home-team').textContent = homeTeam;
  document.querySelector('#away-team').textContent = awayTeam;
  document.querySelector('#stadium').textContent = stadium;
  document.querySelector('#competition').textContent = competition;
  populateOptions('player-options', demoDatabase.players);
  populateOptions('competition-options', demoDatabase.competitions);
  populateOptions('stadium-options', demoDatabase.stadiums);
  populateOptions('team-options', demoDatabase.teams);
  renderPinnedFacts();
}

function waitForReplay(milliseconds) {
  return new Promise((resolve) => {
    cancelDelay = resolve;
    replayTimer = window.setTimeout(() => {
      replayTimer = null;
      cancelDelay = null;
      resolve();
    }, milliseconds);
  });
}

function cancelReplayWait() {
  if (replayTimer !== null) window.clearTimeout(replayTimer);
  replayTimer = null;
  if (cancelDelay) cancelDelay();
  cancelDelay = null;
}

async function playStaticReplay() {
  for (const event of demoEvents) {
    const delay = Math.max(0, Number(event.delay_seconds ?? 1));
    if (delay >= 3) {
      await waitForReplay(delay * 500);
      if (replayCancelled) return;
      renderSuggestions(
        window.PasseDSelector.selectSuggestions({ type: 'calm', team_id: event.team_id }, demoDatabase),
        'calm',
      );
      await waitForReplay(delay * 500);
    } else {
      await waitForReplay(delay * 1000);
    }
    if (replayCancelled) return;

    const context = { ...event, match_id: demoDatabase.match.id, stadium_id: demoDatabase.match.stadium_id };
    if (event.type === 'substitution') {
      context.player_ids = [event.player_out_id, event.player_in_id];
    }
    addTimelineEntry(event);
    receivedEvents += 1;
    eventCount.textContent = `${receivedEvents} / ${totalEvents}`;
    renderSuggestions(window.PasseDSelector.selectSuggestions(context, demoDatabase), 'event');
  }

  if (replayCancelled) return;
  startButton.disabled = false;
  stopButton.disabled = true;
  showStatus('SIMULATION TERMINÉE');
}

function startReplay() {
  if (staticMode) {
    resetView();
    replayCancelled = false;
    startButton.disabled = true;
    stopButton.disabled = false;
    showStatus('DIRECT EN COURS', true);
    playStaticReplay();
    return;
  }

  if (stream) stream.close();
  resetView();
  startButton.disabled = true;
  stopButton.disabled = false;
  showStatus('CONNEXION…');
  stream = new EventSource('/api/replay');

  stream.addEventListener('started', (message) => {
    totalEvents = JSON.parse(message.data).total;
    eventCount.textContent = `0 / ${totalEvents}`;
    showStatus('DIRECT EN COURS', true);
  });

  stream.addEventListener('moment', (message) => {
    const moment = JSON.parse(message.data);
    if (moment.kind === 'calm') {
      renderSuggestions(moment.suggestions, 'calm');
      return;
    }
    addTimelineEntry(moment.event);
    receivedEvents += 1;
    eventCount.textContent = `${receivedEvents} / ${totalEvents}`;
    renderSuggestions(moment.suggestions, 'event');
  });

  stream.addEventListener('finished', () => {
    stream.close();
    stream = null;
    startButton.disabled = false;
    stopButton.disabled = true;
    showStatus('SIMULATION TERMINÉE');
  });

  stream.onerror = () => {
    if (!stream) return;
    stream.close();
    stream = null;
    startButton.disabled = false;
    stopButton.disabled = true;
    showStatus('CONNEXION INTERROMPUE');
  };
}

function stopReplay() {
  replayCancelled = true;
  cancelReplayWait();
  if (stream) stream.close();
  stream = null;
  startButton.disabled = false;
  stopButton.disabled = true;
  showStatus('SIMULATION ARRÊTÉE');
}

startButton.addEventListener('click', startReplay);
stopButton.addEventListener('click', stopReplay);
liveTab.addEventListener('click', () => setView('live'));
preparationTab.addEventListener('click', () => setView('preparation'));
preparationForm.addEventListener('submit', searchPreparation);
loadMatch()
  .then(() => {
    startButton.disabled = false;
  })
  .catch(() => showStatus('SERVEUR INDISPONIBLE'));