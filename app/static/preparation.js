(function (root) {
  const fields = [
    { key: 'player_id', input: 'player', collection: 'players', category: 'player', label: 'Joueur', missing: 'Aucun joueur' },
    { key: 'competition_id', input: 'competition', collection: 'competitions', category: 'competition', label: 'Championnat', missing: 'Aucun championnat' },
    { key: 'stadium_id', input: 'stadium', collection: 'stadiums', category: 'stadium', label: 'Stade', missing: 'Aucun stade' },
    { key: 'home_team_id', input: 'homeTeam', collection: 'teams', category: 'team', label: 'Équipe à domicile', missing: 'Aucune équipe à domicile' },
    { key: 'away_team_id', input: 'awayTeam', collection: 'teams', category: 'team', label: 'Équipe à l’extérieur', missing: 'Aucune équipe à l’extérieur' },
  ];
  const categories = [
    { id: 'cross', label: 'Faits croisés' },
    { id: 'player', label: 'Joueur' },
    { id: 'competition', label: 'Championnat' },
    { id: 'stadium', label: 'Stade' },
    { id: 'team', label: 'Équipe' },
  ];
  const interestOrder = { record: 0, performance: 1, statistic: 2 };
  const storageKey = 'passe-d-preparation-pins-v1';

  function normalize(value) {
    return value.trim().normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('fr');
  }

  function searchPreparation(criteria, database) {
    const entered = fields.filter(({ input }) => String(criteria[input] || '').trim());
    if (!entered.length) {
      return { error: 'Renseignez au moins un champ pour lancer la recherche.', groups: [] };
    }

    const selected = {};
    const selectedCategories = [];
    for (const field of fields) {
      const value = String(criteria[field.input] || '').trim();
      if (!value) continue;

      const entity = (database[field.collection] || []).find((item) => normalize(item.name) === normalize(value));
      if (!entity) {
        return { error: `${field.missing} de la base ne correspond à « ${value} ».`, groups: [] };
      }
      selected[field.key] = entity.id;
      if (field.collection === 'teams') {
        selected.team_ids = [...(selected.team_ids || []), entity.id];
      }
      selectedCategories.push(field.category);
    }

    const matches = (database.records || []).filter((record) => {
      const preparation = record.preparation;
      if (!preparation) return false;
      const targets = Object.entries(preparation.targets || {});
      if (!targets.length) return false;
      if (preparation.category === 'cross' && targets.length < 2) return false;
      return targets.every(([key, value]) => key === 'team_id'
        ? (selected.team_ids || []).includes(value)
        : selected[key] === value);
    });

    const sorted = matches.slice().sort((left, right) => {
      const leftCategory = categories.findIndex((category) => category.id === left.preparation.category);
      const rightCategory = categories.findIndex((category) => category.id === right.preparation.category);
      const leftInterest = interestOrder[left.preparation.interest] ?? 3;
      const rightInterest = interestOrder[right.preparation.interest] ?? 3;
      return leftCategory - rightCategory
        || leftInterest - rightInterest
        || (right.preparation.priority || 0) - (left.preparation.priority || 0)
        || left.id.localeCompare(right.id);
    });

    const groupIds = [...new Set(selectedCategories)];
    if (selectedCategories.length > 1) groupIds.unshift('cross');
    const groups = groupIds.map((id) => {
      const category = categories.find((item) => item.id === id);
      const facts = sorted
        .filter((record) => record.preparation.category === id)
        .map((record) => ({
          id: record.id,
          title: record.title,
          fact: record.fact,
          source_id: record.id,
          source_label: record.source_label || record.id,
          category: id,
          interest: record.preparation.interest,
        }));
      return {
        id,
        label: category.label,
        facts,
        message: facts.length ? '' : `Aucun fait disponible dans cette catégorie pour cette sélection.`,
      };
    });

    return {
      error: '',
      groups,
      selectedCount: selectedCategories.length,
      factCount: groups.reduce((count, group) => count + group.facts.length, 0),
    };
  }

  function readPinnedFacts(storage) {
    try {
      const target = storage || root.localStorage;
      const facts = JSON.parse(target.getItem(storageKey) || '[]');
      return Array.isArray(facts) ? facts : [];
    } catch {
      return [];
    }
  }

  function togglePinnedFact(fact, storage) {
    try {
      const target = storage || root.localStorage;
      const current = readPinnedFacts(target);
      const exists = current.some((item) => item.source_id === fact.source_id);
      const facts = exists
        ? current.filter((item) => item.source_id !== fact.source_id)
        : [...current, fact];
      target.setItem(storageKey, JSON.stringify(facts));
      return { pinned: !exists, facts };
    } catch {
      return { pinned: false, facts: [], error: 'Le stockage local est indisponible.' };
    }
  }

  function renderPinnedFacts(container, facts, renderFact) {
    container.replaceChildren();
    for (const fact of facts) container.append(renderFact(fact));
    return facts.length;
  }

  root.PasseDPreparation = { searchPreparation, readPinnedFacts, togglePinnedFact, renderPinnedFacts };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.PasseDPreparation;
})(typeof window !== 'undefined' ? window : globalThis);