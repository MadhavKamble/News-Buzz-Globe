// Zoom-level marker aggregation (view-side sibling of the Phase 8 story
// clustering): when zoomed out, nearby markers collapse into one aggregate
// so the globe stays readable; zooming in splits them apart again.
//
// Grid-based: bucket points into lat/lng cells whose size grows with camera
// altitude, keep the highest-intensity member as the representative.

export function cellSizeForAltitude(altitude) {
  if (altitude >= 2.0) return 8; // far out: 8-degree cells
  if (altitude >= 1.2) return 4;
  if (altitude >= 0.7) return 2;
  return 0; // close in: no aggregation
}

export function clusterForZoom(points, altitude) {
  const cell = cellSizeForAltitude(altitude);
  if (cell === 0 || points.length === 0) return points;
  const buckets = new Map();
  for (const p of points) {
    const key = `${Math.floor(p.lat / cell)}:${Math.floor(p.lng / cell)}`;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(p);
    else buckets.set(key, [p]);
  }
  const out = [];
  for (const members of buckets.values()) {
    if (members.length === 1) {
      out.push(members[0]);
      continue;
    }
    const rep = members.reduce((a, b) => (b.intensity > a.intensity ? b : a));
    out.push({
      ...rep,
      cluster_size: members.length,
      intensity: Math.max(...members.map((m) => m.intensity)),
      num_articles: members.reduce((s, m) => s + (m.num_articles || 0), 0),
      num_sources: members.reduce((s, m) => s + (m.num_sources || 0), 0),
    });
  }
  return out;
}
