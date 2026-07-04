const RANGE_HOURS = 48;
const STEP_MINUTES = 15;
const MAX_STEPS = (RANGE_HOURS * 60) / STEP_MINUTES;

// offsetSteps: 0 = live/now, positive = steps back into the past.
export default function TimeSlider({ offsetSteps, onChange }) {
  const isLive = offsetSteps === 0;
  const selected = new Date(Date.now() - offsetSteps * STEP_MINUTES * 60 * 1000);
  const label = isLive
    ? 'LIVE'
    : selected.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

  return (
    <div className="time-slider">
      <button
        className={`live-btn ${isLive ? 'live-on' : ''}`}
        onClick={() => onChange(0)}
        title="Jump to now"
      >
        ● LIVE
      </button>
      <input
        type="range"
        min={0}
        max={MAX_STEPS}
        step={1}
        // Range is drawn oldest -> newest, so invert the offset.
        value={MAX_STEPS - offsetSteps}
        onChange={(e) => onChange(MAX_STEPS - Number(e.target.value))}
        aria-label="Time slider"
      />
      <span className={`time-label ${isLive ? 'time-live' : ''}`}>{label}</span>
    </div>
  );
}

export { STEP_MINUTES };
