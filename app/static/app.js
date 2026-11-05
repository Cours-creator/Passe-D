const startButton = document.querySelector('#start-button');
const stopButton = document.querySelector('#stop-button');
const timeline = document.querySelector('#timeline');
const suggestions = document.querySelector('#suggestions');
const stateLabel = document.querySelector('#connection-state');
const eventCount = document.querySelector('#event-count');
const suggestionCount = document.querySelector('#suggestion-count');
const suggestionIntro = document.querySelector('#suggestion-intro');

let stream = null;
let score = { home: 0, away: 0 };
let receivedEvents = 0;
let totalEvents = 0;

const labels = {
  goal: 'But',
  yellow_card: 'Carton jaune',
  red_card: 'Carton rouge',
  substitution: 'Remplacement',
  temps_mort: 'Temps mort',
  calm: 'Temps calme',
};

function showStatus(text, active = false) {
  stateLabel.textContent = text;
  stateLabel.classList.toggle('is-active', active);
}

function resetView() {
  timeline.replaceChildren();
  suggestions.replaceChildren();
  score = { home: 0, away: 0 };
  receivedEvents = 0;
  document.querySelector('#home-score').textContent = '0';
  document.querySelector('#away-score').textContent = '0';
  document.querySelector('#clock').textContent = '--’';
  eventCount.textContent = `0 / ${totalEvents}`;
  suggestionCount.textContent = '0';
}

function addTimelineEntry(event, kind = 'event') {
  const empty = document.querySelector('#empty-timeline');
  if (empty) empty.remove();

  const item = document.createElement('li');
  item.className = 'timeline-entry';
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
  timeline.append(item);

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
    source.textContent = `SOURCE ${suggestion.source_id} · ${suggestion.source_label}`;
    card.append(title, fact, source);
    suggestions.append(card);
  }
}

async function loadMatch() {
  const response = await fetch('/api/demo');
  if (!response.ok) throw new Error('Données de rencontre indisponibles');
  const data = await response.json();
  document.querySelector('#home-team').textContent = data.home_team;
  document.querySelector('#away-team').textContent = data.away_team;
  document.querySelector('#stadium').textContent = data.stadium;
  document.querySelector('#competition').textContent = data.competition;
}

function startReplay() {
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
  if (stream) stream.close();
  stream = null;
  startButton.disabled = false;
  stopButton.disabled = true;
  showStatus('SIMULATION ARRÊTÉE');
}

startButton.addEventListener('click', startReplay);
stopButton.addEventListener('click', stopReplay);
loadMatch().catch(() => showStatus('SERVEUR INDISPONIBLE'));