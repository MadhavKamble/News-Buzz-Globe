const STEPS = [
  {
    title: '🌍 Welcome to News Buzz Globe',
    body: 'Every marker is a real news story from the last few hours, sized by how much attention it is getting worldwide. Drag to rotate, scroll to zoom — it auto-rotates when idle.',
  },
  {
    title: '📌 Click a hotspot',
    body: 'Hover for the headline, click for full detail: articles, sources, sentiment, whether the story is rising or fading, and links to read it. Big markers with a count like "12×" are groups — zoom in to split them apart.',
  },
  {
    title: '⏪ Scrub through time',
    body: 'The slider at the bottom replays the last 48 hours in 15-minute steps. Watch stories appear, grow, and fade. Hit LIVE to jump back to now.',
  },
  {
    title: '🎛 Views and filters',
    body: 'Top-right: switch Stories (deduplicated, AI-labeled) vs raw Events, and color by Buzz or by Tone (red = negative coverage, blue = positive). Left: search places and filter by theme — theme filters apply to the Events view.',
  },
];

export default function Tour({ step, onNext, onClose }) {
  if (step == null) return null;
  const s = STEPS[step];
  const last = step === STEPS.length - 1;
  return (
    <div className="tour-backdrop" onClick={onClose}>
      <div className="tour-card" onClick={(e) => e.stopPropagation()}>
        <h3>{s.title}</h3>
        <p>{s.body}</p>
        <div className="tour-footer">
          <span className="tour-dots">
            {STEPS.map((_, i) => (
              <i key={i} className={i === step ? 'dot-on' : ''} />
            ))}
          </span>
          <span className="tour-actions">
            <button className="tour-skip" onClick={onClose}>
              Skip
            </button>
            <button className="tour-next" onClick={last ? onClose : onNext}>
              {last ? 'Start exploring' : 'Next'}
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}

export const TOUR_STEPS = STEPS.length;
