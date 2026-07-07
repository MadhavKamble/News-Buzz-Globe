import { useState } from 'react';
import { postChat } from '../api';

// RAG "chat with the news" panel. Auth is silent (App fetches a guest token
// on load and passes it down) — this component only owns the ask/answer
// interaction, not the token lifecycle.
export default function ChatPanel({ open, token, onClose }) {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [asked, setAsked] = useState(false);
  const [answer, setAnswer] = useState(null);
  const [sources, setSources] = useState([]);
  const [error, setError] = useState(null);

  if (!open) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    const q = query.trim();
    if (!q || loading) return;
    if (!token) {
      setAsked(true);
      setAnswer(null);
      setError('Chat is unavailable right now — could not authenticate.');
      return;
    }
    setLoading(true);
    setAsked(true);
    setError(null);
    try {
      const result = await postChat(q, token);
      setAnswer(result.answer);
      setSources(result.sources || []);
      if (result.answer == null) {
        setError('No answer available right now — try again shortly.');
      }
    } catch (err) {
      setAnswer(null);
      setSources([]);
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <aside className="chat-panel">
      <button className="popup-close" onClick={onClose} aria-label="Close chat">
        ×
      </button>
      <h2 className="popup-title">Chat with the news</h2>
      <form className="chat-form" onSubmit={handleSubmit}>
        <input
          type="text"
          className="chat-input"
          placeholder="Ask about current events…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={loading}
          aria-label="Ask a question about current events"
        />
        <button type="submit" className="chat-submit" disabled={loading || !query.trim()}>
          Ask
        </button>
      </form>
      {loading && (
        <div className="chat-loading">
          <div className="spinner spinner-sm" />
          Thinking…
        </div>
      )}
      {!loading && error && <p className="chat-error">{error}</p>}
      {!loading && !error && asked && answer && (
        <div className="chat-answer">
          <p>{answer}</p>
          {sources.length > 0 && (
            <ul className="chat-sources">
              {sources.map((s, i) => (
                <li key={`${i}-${s.source_url || s.title}`}>
                  {s.source_url ? (
                    <a
                      className="popup-link"
                      href={s.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {s.title || 'Source'} ↗
                    </a>
                  ) : (
                    <span>{s.title || 'Source'}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </aside>
  );
}
