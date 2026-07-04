import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Globe from 'react-globe.gl';
import { fetchEvents, fetchStats, fetchStories, fetchThemes } from './api';
import { clusterForZoom } from './clusterMarkers';
import { intensityColor, toneColor } from './colors';
import EventPopup from './components/EventPopup';
import FilterPanel from './components/FilterPanel';
import Legend from './components/Legend';
import SearchBox from './components/SearchBox';
import StatsBar from './components/StatsBar';
import TimeSlider, { STEP_MINUTES } from './components/TimeSlider';
import Tour, { TOUR_STEPS } from './components/Tour';

const REFRESH_MS = 5 * 60 * 1000; // matches GDELT's 15-min cadence comfortably
const IDLE_RESUME_MS = 10 * 1000;
const WINDOW_HOURS = 6; // events shown at slider position t: [t - 6h, t]
const SCRUB_DEBOUNCE_MS = 250;
const TOUR_KEY = 'nbg-tour-v1';
const HOME_POV = { lat: 20, lng: 10, altitude: 2.5 };

export default function App() {
  const globeRef = useRef();
  const idleTimer = useRef();
  const debounceTimer = useRef();
  const altitudeTimer = useRef();
  const [events, setEvents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [offsetSteps, setOffsetSteps] = useState(0); // 0 = live
  const [themes, setThemes] = useState({});
  const [activeThemes, setActiveThemes] = useState([]);
  const [viewMode, setViewMode] = useState('stories'); // 'stories' | 'events'
  const [colorMode, setColorMode] = useState('buzz'); // 'buzz' | 'tone'
  const [stats, setStats] = useState(null);
  const [altitude, setAltitude] = useState(HOME_POV.altitude);
  const [tourStep, setTourStep] = useState(() =>
    localStorage.getItem(TOUR_KEY) ? null : 0,
  );
  const [size, setSize] = useState({ w: window.innerWidth, h: window.innerHeight });

  // Theme filters only apply to raw events, and stories exist only for "now";
  // either condition switches the effective view to Events.
  const effectiveMode =
    offsetSteps === 0 && activeThemes.length === 0 ? viewMode : 'events';

  const loadEvents = useCallback(async (steps, themeKeys, mode) => {
    setIsLoading(true);
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
      // Floor to the 15-min data grid: GDELT only changes on that cadence,
      // and stable timestamps let the backend Redis cache actually hit.
      const stepMs = STEP_MINUTES * 60 * 1000;
      const t = new Date(Math.floor((Date.now() - steps * stepMs) / stepMs) * stepMs);
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
    } finally {
      setIsLoading(false);
      setHasLoadedOnce(true);
    }
  }, []);

  const loadStats = useCallback(() => {
    fetchStats().then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    fetchThemes().then(setThemes).catch(() => {});
    loadStats();
    const timer = setInterval(loadStats, REFRESH_MS);
    return () => clearInterval(timer);
  }, [loadStats]);

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
  // Also track camera altitude (throttled) to drive zoom-level clustering.
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
    const trackZoom = () => {
      clearTimeout(altitudeTimer.current);
      altitudeTimer.current = setTimeout(() => {
        const pov = globeRef.current?.pointOfView();
        if (pov) setAltitude(pov.altitude);
      }, 150);
    };
    controls.addEventListener('start', pause);
    controls.addEventListener('change', trackZoom);
    return () => {
      controls.removeEventListener('start', pause);
      controls.removeEventListener('change', trackZoom);
      clearTimeout(idleTimer.current);
      clearTimeout(altitudeTimer.current);
    };
  }, []);

  // Aggregate nearby markers while zoomed out; split apart when zoomed in.
  const displayed = useMemo(
    () => clusterForZoom(events, altitude),
    [events, altitude],
  );

  const handlePointClick = useCallback(
    (point) => {
      if (point.cluster_size > 1) {
        // Aggregate marker: zoom in to split it instead of opening a popup.
        globeRef.current?.pointOfView(
          { lat: point.lat, lng: point.lng, altitude: Math.max(0.5, altitude * 0.4) },
          800,
        );
        return;
      }
      setSelected(point);
      globeRef.current?.pointOfView({ lat: point.lat, lng: point.lng, altitude: 1.2 }, 800);
    },
    [altitude],
  );

  const handleFlyTo = useCallback(({ lat, lng, altitude: alt }) => {
    globeRef.current?.pointOfView({ lat, lng, altitude: alt }, 1200);
  }, []);

  const toggleTheme = useCallback((key) => {
    setActiveThemes((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }, []);

  const resetView = useCallback(() => {
    setActiveThemes([]);
    setOffsetSteps(0);
    setViewMode('stories');
    setColorMode('buzz');
    setSelected(null);
    globeRef.current?.pointOfView(HOME_POV, 1000);
  }, []);

  const closeTour = useCallback(() => {
    localStorage.setItem(TOUR_KEY, 'done');
    setTourStep(null);
  }, []);

  const sqrtI = (d) => Math.sqrt(Math.max(0, Math.min(1, d.intensity)));
  const clusterBoost = (d) =>
    d.cluster_size > 1 ? 1 + Math.min(0.6, 0.1 * Math.sqrt(d.cluster_size)) : 1;

  return (
    <div className="app">
      <Globe
        ref={globeRef}
        width={size.w}
        height={size.h}
        globeImageUrl="/textures/earth-night.jpg"
        bumpImageUrl="/textures/earth-topology.png"
        backgroundImageUrl="/textures/night-sky.png"
        pointsData={displayed}
        pointLat="lat"
        pointLng="lng"
        pointsTransitionDuration={600}
        pointAltitude={(d) => 0.01 + 0.32 * sqrtI(d) * clusterBoost(d)}
        pointRadius={(d) => (0.1 + 0.45 * sqrtI(d)) * clusterBoost(d)}
        pointColor={(d) =>
          colorMode === 'tone' ? toneColor(d.avg_tone) : intensityColor(d.intensity)
        }
        pointLabel={(d) =>
          `<div class="tooltip">${
            d.cluster_size > 1 ? `<span class="tt-count">${d.cluster_size}×</span> ` : ''
          }${escapeHtml(d.title || d.location || 'Event')}${
            d.cluster_size > 1 ? '<br/><small>click to zoom in</small>' : ''
          }</div>`
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
      <div className="toggles">
        <div className="view-toggle">
          <button
            className={effectiveMode === 'stories' ? 'seg-on' : ''}
            onClick={() => {
              setViewMode('stories');
              setActiveThemes([]);
              setOffsetSteps(0);
            }}
            title="Deduplicated stories with AI-generated headlines"
          >
            Stories
          </button>
          <button
            className={effectiveMode === 'events' ? 'seg-on' : ''}
            onClick={() => setViewMode('events')}
            title="Raw GDELT events"
          >
            Events
          </button>
        </div>
        <div className="view-toggle">
          <button
            className={colorMode === 'buzz' ? 'seg-on' : ''}
            onClick={() => setColorMode('buzz')}
            title="Color markers by buzz intensity"
          >
            🔥 Buzz
          </button>
          <button
            className={colorMode === 'tone' ? 'seg-on' : ''}
            onClick={() => setColorMode('tone')}
            title="Color markers by sentiment (GDELT AvgTone)"
          >
            ± Tone
          </button>
        </div>
        <button className="icon-btn" onClick={resetView} title="Reset view and filters">
          ⟲
        </button>
      </div>
      <div className="controls">
        <SearchBox events={events} onFlyTo={handleFlyTo} />
        <FilterPanel
          themes={themes}
          active={activeThemes}
          onToggle={toggleTheme}
          onClear={() => setActiveThemes([])}
          storiesMode={effectiveMode === 'stories'}
        />
      </div>
      {!hasLoadedOnce && (
        <div className="loading-overlay">
          <div className="spinner" />
          <p>Loading live GDELT data…</p>
        </div>
      )}
      {hasLoadedOnce && isLoading && (
        <div className="loading-pill">
          <div className="spinner spinner-sm" />
          Updating…
        </div>
      )}
      {hasLoadedOnce && !isLoading && !error && events.length === 0 && (
        <div className="empty-state">
          <p>No events match these filters in this time window.</p>
          <button onClick={resetView}>Clear filters & reset</button>
        </div>
      )}
      {error && <div className="error-toast">API unreachable: {error}</div>}
      <EventPopup event={selected} onClose={() => setSelected(null)} />
      <TimeSlider offsetSteps={offsetSteps} onChange={setOffsetSteps} />
      <div className="bottom-left">
        <StatsBar stats={stats} />
        <Legend colorMode={colorMode} />
      </div>
      <button
        className="icon-btn help-btn"
        onClick={() => setTourStep(0)}
        title="Show the tour again"
      >
        ?
      </button>
      <Tour
        step={tourStep}
        onNext={() => setTourStep((s) => Math.min(s + 1, TOUR_STEPS - 1))}
        onClose={closeTour}
      />
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
