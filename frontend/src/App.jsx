import { useCallback, useEffect, useRef, useState } from 'react';
import Globe from 'react-globe.gl';
import { fetchEvents } from './api';
import { intensityColor } from './colors';
import EventPopup from './components/EventPopup';
import TimeSlider, { STEP_MINUTES } from './components/TimeSlider';

const REFRESH_MS = 5 * 60 * 1000; // matches GDELT's 15-min cadence comfortably
const IDLE_RESUME_MS = 10 * 1000;
const WINDOW_HOURS = 6; // events shown at slider position t: [t - 6h, t]
const SCRUB_DEBOUNCE_MS = 250;

export default function App() {
  const globeRef = useRef();
  const idleTimer = useRef();
  const debounceTimer = useRef();
  const [events, setEvents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);
  const [offsetSteps, setOffsetSteps] = useState(0); // 0 = live
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight });

  const loadEvents = useCallback(async (steps) => {
    try {
      const t = new Date(Date.now() - steps * STEP_MINUTES * 60 * 1000);
      const start = new Date(t.getTime() - WINDOW_HOURS * 60 * 60 * 1000);
      setEvents(
        await fetchEvents({
          start: start.toISOString(),
          end: t.toISOString(),
          at: t.toISOString(),
          limit: 1000,
        }),
      );
      setError(null);
    } catch (err) {
      setError(String(err.message || err));
    }
  }, []);

  // Fetch on slider move (debounced); poll only while live.
  useEffect(() => {
    clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => loadEvents(offsetSteps), SCRUB_DEBOUNCE_MS);
    if (offsetSteps !== 0) return () => clearTimeout(debounceTimer.current);
    const timer = setInterval(() => loadEvents(0), REFRESH_MS);
    return () => {
      clearTimeout(debounceTimer.current);
      clearInterval(timer);
    };
  }, [offsetSteps, loadEvents]);

  useEffect(() => {
    const onResize = () => setSize({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Auto-rotate when idle; pause while the user is interacting.
  useEffect(() => {
    const controls = globeRef.current?.controls();
    if (!controls) return;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.6;
    const pause = () => {
      controls.autoRotate = false;
      clearTimeout(idleTimer.current);
      idleTimer.current = setTimeout(() => {
        controls.autoRotate = true;
      }, IDLE_RESUME_MS);
    };
    controls.addEventListener('start', pause);
    return () => {
      controls.removeEventListener('start', pause);
      clearTimeout(idleTimer.current);
    };
  }, []);

  const handlePointClick = useCallback((point) => {
    setSelected(point);
    globeRef.current?.pointOfView(
      { lat: point.lat, lng: point.lng, altitude: 1.2 },
      800,
    );
  }, []);

  return (
    <div className="app">
      <Globe
        ref={globeRef}
        width={size.w}
        height={size.h}
        globeImageUrl="/textures/earth-night.jpg"
        bumpImageUrl="/textures/earth-topology.png"
        backgroundImageUrl="/textures/night-sky.png"
        pointsData={events}
        pointLat="lat"
        pointLng="lng"
        pointsTransitionDuration={600}
        pointAltitude={(d) => 0.01 + d.intensity * 0.35}
        pointRadius={(d) => 0.12 + d.intensity * 0.5}
        pointColor={(d) => intensityColor(d.intensity)}
        pointLabel={(d) =>
          `<div class="tooltip"><b>${escapeHtml(d.title || d.location || 'Event')}</b><br/>` +
          `buzz ${Math.round(d.intensity * 100)} · ${d.num_articles ?? '?'} articles</div>`
        }
        onPointClick={handlePointClick}
        onGlobeClick={() => setSelected(null)}
        atmosphereColor="#88aaff"
        atmosphereAltitude={0.18}
      />
      <header className="banner">
        <h1>News Buzz Globe</h1>
        <p>
          {events.length} hotspots · {offsetSteps === 0 ? 'live' : 'historical'} · GDELT,
          updated every 15 min
        </p>
      </header>
      {error && <div className="error-toast">API unreachable: {error}</div>}
      <EventPopup event={selected} onClose={() => setSelected(null)} />
      <TimeSlider offsetSteps={offsetSteps} onChange={setOffsetSteps} />
    </div>
  );
}

function escapeHtml(text) {
  return String(text).replace(
    /[&<>"']/g,
    (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
}
