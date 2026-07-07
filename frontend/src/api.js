// API client. In dev, Vite proxies /api -> FastAPI; in production builds,
// set VITE_API_URL to the deployed API origin.
const API_BASE = import.meta.env.VITE_API_URL || '/api';

export async function fetchEvents(params = {}) {
  const query = new URLSearchParams();
  if (params.bbox) query.set('bbox', params.bbox);
  if (params.start) query.set('start', params.start);
  if (params.end) query.set('end', params.end);
  if (params.at) query.set('at', params.at);
  (params.categories || []).forEach((c) => query.append('category', c));
  (params.themes || []).forEach((t) => query.append('theme', t));
  query.set('limit', params.limit ?? 1000);

  const resp = await fetch(`${API_BASE}/events?${query}`);
  if (!resp.ok) throw new Error(`API error ${resp.status}`);
  const geojson = await resp.json();
  // Flatten GeoJSON features into the point objects react-globe.gl expects.
  return geojson.features.map((f) => ({
    lng: f.geometry.coordinates[0],
    lat: f.geometry.coordinates[1],
    ...f.properties,
  }));
}

export async function fetchThemes() {
  const resp = await fetch(`${API_BASE}/themes`);
  if (!resp.ok) throw new Error(`API error ${resp.status}`);
  return resp.json();
}

export async function fetchStats() {
  const resp = await fetch(`${API_BASE}/stats`);
  if (!resp.ok) throw new Error(`API error ${resp.status}`);
  return resp.json();
}

// Deduplicated story clusters (Phase 8) from the latest clustering run.
export async function fetchStories(limit = 800) {
  const resp = await fetch(`${API_BASE}/stories?limit=${limit}`);
  if (!resp.ok) throw new Error(`API error ${resp.status}`);
  const geojson = await resp.json();
  return geojson.features.map((f) => ({
    lng: f.geometry.coordinates[0],
    lat: f.geometry.coordinates[1],
    title: f.properties.summary,
    num_articles: f.properties.total_articles,
    num_sources: f.properties.total_sources,
    date_added: f.properties.latest,
    source_url: f.properties.source_urls[0] || null,
    ...f.properties,
  }));
}

// Demo JWT flow (no password) — issues a token for the RAG chat feature.
export async function fetchChatToken(userId) {
  const resp = await fetch(`${API_BASE}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!resp.ok) throw new Error(`API error ${resp.status}`);
  return resp.json();
}

// Ask a natural-language question, answered from indexed news stories.
export async function postChat(query, token) {
  const resp = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ query }),
  });
  if (!resp.ok) throw new Error(`API error ${resp.status}`);
  return resp.json();
}
