import { intensityColor, toneColor } from '../colors';

export default function Legend({ colorMode }) {
  const stops = [0.1, 0.35, 0.6, 0.85];
  const tones = [-8, -4, 0, 4, 8];
  return (
    <div className="legend">
      <div className="legend-row">
        <span className="legend-title">Size / height</span>
        <span className="legend-note">buzz intensity (√ scale)</span>
      </div>
      <div className="legend-row">
        <span className="legend-title">Color</span>
        {colorMode === 'buzz' ? (
          <span className="legend-swatches" title="Low to high buzz">
            {stops.map((s) => (
              <i key={s} style={{ background: intensityColor(s, 1) }} />
            ))}
            <span className="legend-note">quiet → viral</span>
          </span>
        ) : (
          <span className="legend-swatches" title="Negative to positive tone">
            {tones.map((t) => (
              <i key={t} style={{ background: toneColor(t, 1) }} />
            ))}
            <span className="legend-note">negative → positive tone</span>
          </span>
        )}
      </div>
      <div className="legend-row">
        <span className="legend-title">◎ n×</span>
        <span className="legend-note">markers grouped while zoomed out — zoom in to split</span>
      </div>
    </div>
  );
}
