import { useCallback, useEffect, useRef, useState } from 'react';
import Globe from 'react-globe.gl';
import { fetchEvents, fetchStories, fetchThemes } from './api';
import { intensityColor } from './colors';
import EventPopup from './components/EventPopup';
import FilterPanel from './components/FilterPanel';
import SearchBox from './components/SearchBox';
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
  const [themes, setThemes] = useState({});
  const [activeThemes, setActiveThemes] = useState([]);
  const [viewMode, setViewMode] = useState('stories'); // 'stories' | 'events'
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight });

  // Stories are computed for "now" only; scrubbing history uses raw events.
  const effectiveMode = offsetSteps === 0 ? viewMode : 'events';

  const loadEvents = useCallback(async (steps, themeKeys, mode) => {
    try {
      if (mode === 'stories') {
        const stories = await fetchStories();
        if (stories.length > 0) {
          setEvents(stories);
          setError(null);
          return;
        }
        // No clustering run yet — fall back to raw events silently.
      }
      const t = new Date(Date.now() - steps * STEP_MINUTES * 60 * 1000);
      const start = new Date(t.getTime() - WINDOW_HOURS * 60 * 60 * 1000);
      setEvents(
        await fetchEvents({
          start: start.toISOString(),
          end: t.toISOString(),
          at: t.toISOString(),
          themes: themeKeys,
          limit: 1000,
        }),
      );
      setError(null);
    } catch (err) {
      setError(String(err.message || err));
    }
  }, []);

  useEffect(() => {
    fetchThemes().then(setThemes).catch(() => {});
  }, []);

  // Fetch on slider/filter/view change (debounced); poll only while live.
  useEffect(() => {
    clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(
      () => loadEvents(offsetSteps, activeThemes, effectiveMode),
      SCRUB_DEBOUNCE_MS,
    );
    if (offsetSteps !== 0) return () => clearTimeout(debounceTimer.current);
    const timer = setInterval(
      () => loadEvents(0, activeThemes, effectiveMode),
      REFRESH_MS,
    );
    return () => {
      clearTimeout(debounceTimer.current);
      clearInterval(timer);
    };
  }, [offsetSteps, activeThemes, effectiveMode, loadEvents]);

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

  const handleFlyTo = useCallback(({ lat, lng, altitude }) => {
    globeRef.current?.pointOfView({ lat, lng, altitude }, 1200);
  }, []);

  const toggleTheme = useCallback((key) => {
    setActiveThemes((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
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
          {events.length} {effectiveMode === 'stories' ? 'stories' : 'hotspots'} ·{' '}
          {offsetSteps === 0 ? 'live' : 'historical'} · GDELT, updated every 15 min
        </p>
      </header>
      <div className="view-toggle">
        <button
          className={effectiveMode === 'stories' ? 'seg-on' : ''}
          onClick={() => {
            setViewMode('stories');
            setOffsetSteps(0);
          }}
        >
          Stories
        </button>
        <button
          className={effectiveMode === 'events' ? 'seg-on' : ''}
          onClick={() => setViewMode('events')}
        >
          Events
        </button>
      </div>
      {error && <div className="error-toast">API unreachable: {error}</div>}
      <div className="controls">
        <SearchBox events={events} onFlyTo={handleFlyTo} />
        <FilterPanel
          themes={themes}
          active={activeThemes}
          onToggle={toggleTheme}
          onClear={() => setActiveThemes([])}
        />
      </div>
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
