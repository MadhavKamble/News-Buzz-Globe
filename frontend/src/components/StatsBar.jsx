export default function StatsBar({ stats }) {
  if (!stats) return null;
  const when = stats.last_ingestion_at
    ? new Date(stats.last_ingestion_at).toLocaleTimeString(undefined, {
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';
  return (
    <div className="statsbar" title="Live pipeline status">
      <span>
        <b>{stats.total_events.toLocaleString()}</b> events
      </span>
      <span>
        <b>{stats.total_stories.toLocaleString()}</b> stories
      </span>
      <span>
        ingested <b>{when}</b>
        {stats.last_ingestion_rows != null && ` (+${stats.last_ingestion_rows})`}
      </span>
    </div>
  );
}
