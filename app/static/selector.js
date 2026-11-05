(function (root) {
  function selectSuggestions(event, database, limit = 3) {
    const type = event.type || 'calm';
    const trigger = type === 'temps_mort' ? 'timeout' : type;
    const playerIds = event.player_ids || [];
    const context = {
      player_id: event.player_id,
      player_ids: playerIds,
      team_id: event.team_id,
      stadium_id: event.stadium_id,
      match_id: event.match_id,
    };
    const candidates = [];

    for (const record of database.records || []) {
      const triggers = record.triggers || [];
      if (!triggers.includes(trigger) && !triggers.includes('any')) continue;

      const targets = record.targets || {};
      const matches = Object.entries(targets).every(([key, value]) => {
        if (key === 'player_id' && playerIds.length) return playerIds.includes(value);
        return context[key] === value;
      });
      if (!matches) continue;

      let relevance = record.priority || 0;
      relevance += triggers.includes(trigger) ? 60 : 0;
      relevance += targets.player_id ? 40 : 0;
      relevance += targets.team_id ? 25 : 0;
      relevance += targets.stadium_id ? 20 : 0;
      relevance += targets.match_id ? 10 : 0;
      candidates.push({ record, relevance });
    }

    candidates.sort((left, right) => right.relevance - left.relevance || left.record.id.localeCompare(right.record.id));
    return candidates.slice(0, Math.max(0, limit)).map(({ record, relevance }) => ({
      title: record.title,
      fact: record.fact,
      source_id: record.id,
      source_label: record.source_label || record.id,
      relevance,
    }));
  }

  root.PasseDSelector = { selectSuggestions };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.PasseDSelector;
})(typeof window !== 'undefined' ? window : globalThis);