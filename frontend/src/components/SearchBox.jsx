import { useMemo, useState } from 'react';
import { COUNTRIES, REGIONS } from '../countries';

// Region/country search with camera fly-to. Also matches locations among the
// currently loaded events so city-level names present in the data work too.
export default function SearchBox({ events, onFlyTo }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const regionHits = REGIONS.filter((r) => r.name.toLowerCase().includes(q)).map(
      (r) => ({ ...r, kind: 'region' }),
    );
    const countryHits = COUNTRIES.filter((c) => c.name.toLowerCase().includes(q)).map(
      (c) => ({ ...c, kind: 'country', altitude: 1.4 }),
    );
    const seen = new Set();
    const eventHits = [];
    for (const e of events) {
      const loc = e.location || '';
      if (loc.toLowerCase().includes(q) && !seen.has(loc)) {
        seen.add(loc);
        eventHits.push({ name: loc, lat: e.lat, lng: e.lng, kind: 'place', altitude: 0.9 });
        if (eventHits.length >= 4) break;
      }
    }
    return [...regionHits, ...countryHits, ...eventHits].slice(0, 8);
  }, [query, events]);

  const pick = (m) => {
    onFlyTo({ lat: m.lat, lng: m.lng, altitude: m.altitude ?? 1.4 });
    setQuery(m.name);
    setOpen(false);
  };

  return (
    <div className="searchbox">
      <input
        type="search"
        placeholder="Search country or region…"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && matches.length > 0) pick(matches[0]);
          if (e.key === 'Escape') setOpen(false);
        }}
        aria-label="Search country or region"
      />
      {open && matches.length > 0 && (
        <ul className="search-results">
          {matches.map((m) => (
            <li key={`${m.kind}:${m.name}`}>
              <button onClick={() => pick(m)}>
                <span>{m.name}</span>
                <em>{m.kind}</em>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
