// Intensity -> color ramp: cool amber for quiet events up to hot red-orange
// for high-buzz ones. Returns rgba() so marker opacity can ride along.
export function intensityColor(intensity, alpha = 0.85) {
  const t = Math.max(0, Math.min(1, intensity));
  const r = Math.round(255);
  const g = Math.round(200 - 160 * t);
  const b = Math.round(80 - 80 * t);
  return `rgba(${r},${g},${b},${alpha})`;
}

// GDELT AvgTone (roughly -10..+10) -> diverging sentiment scale:
// negative = red, neutral = slate, positive = green.
export function toneColor(tone, alpha = 0.85) {
  if (tone == null) return `rgba(150,150,160,${alpha})`;
  const t = Math.max(-1, Math.min(1, tone / 8)); // clamp to [-1, 1]
  let r;
  let g;
  let b;
  if (t < 0) {
    // slate -> red
    r = Math.round(130 + 125 * -t);
    g = Math.round(135 - 85 * -t);
    b = Math.round(150 - 90 * -t);
  } else {
    // slate -> green
    r = Math.round(130 - 90 * t);
    g = Math.round(135 + 100 * t);
    b = Math.round(150 - 50 * t);
  }
  return `rgba(${r},${g},${b},${alpha})`;
}
