// Theme filter chips. Theme definitions come from GET /themes (single source
// of truth in the backend); empty selection = all events. Stories aggregate
// events across CAMEO codes, so activating a filter switches to Events view —
// the hint below makes that explicit instead of silently ignoring clicks.
export default function FilterPanel({ themes, active, onToggle, onClear, storiesMode }) {
  const keys = Object.keys(themes);
  if (keys.length === 0) return null;
  return (
    <div className="filter-panel-wrap">
      <div className="filter-panel">
        {keys.map((key) => (
          <button
            key={key}
            className={`chip ${active.includes(key) ? 'chip-on' : ''}`}
            onClick={() => onToggle(key)}
          >
            {themes[key].label}
          </button>
        ))}
        {active.length > 0 && (
          <button className="chip chip-clear" onClick={onClear}>
            ✕ Clear
          </button>
        )}
      </div>
      {storiesMode && (
        <p className="filter-hint">Theme filters show raw Events (stories span themes)</p>
      )}
    </div>
  );
}
