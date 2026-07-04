// Theme filter chips. Theme definitions come from GET /themes (single source
// of truth in the backend); empty selection = all events.
export default function FilterPanel({ themes, active, onToggle, onClear }) {
  const keys = Object.keys(themes);
  if (keys.length === 0) return null;
  return (
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
  );
}
