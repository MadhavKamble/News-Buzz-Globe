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
