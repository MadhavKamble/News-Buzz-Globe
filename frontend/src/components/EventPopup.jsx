export default function EventPopup({ event, onClose }) {
  if (!event) return null;
  const when = new Date(event.date_added).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
  return (
    <aside className="popup">
      <button className="popup-close" onClick={onClose} aria-label="Close">
        ×
      </button>
      <h2 className="popup-title">{event.title || describeEvent(event)}</h2>
      <p className="popup-meta">
        {event.location || 'Unknown location'} · {when}
      </p>
      <dl className="popup-stats">
        <div>
          <dt>Buzz</dt>
          <dd>{Math.round(event.intensity * 100)}</dd>
        </div>
        <div>
          <dt>Articles</dt>
          <dd>{event.num_articles ?? '–'}</dd>
        </div>
        <div>
          <dt>Sources</dt>
          <dd>{event.num_sources ?? '–'}</dd>
        </div>
        <div>
          <dt>Tone</dt>
          <dd>{event.avg_tone != null ? event.avg_tone.toFixed(1) : '–'}</dd>
        </div>
      </dl>
      {event.member_count > 1 && (
        <p className="popup-merged">
          ✦ {event.member_count} reports merged · AI-generated headline
        </p>
      )}
      {(event.source_urls || (event.source_url ? [event.source_url] : []))
        .slice(0, 3)
        .map((url, i) => (
          <a
            key={url}
            className="popup-link"
            href={url}
            target="_blank"
            rel="noreferrer"
          >
            Read article{i > 0 ? ` ${i + 1}` : ''} ↗
          </a>
        ))}
    </aside>
  );
}

function describeEvent(event) {
  const actors = [event.actor1, event.actor2].filter(Boolean).join(' – ');
  return actors || `Event ${event.id}`;
}
