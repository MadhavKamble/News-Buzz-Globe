// Intensity -> color ramp: cool amber for quiet events up to hot red-orange
// for high-buzz ones. Returns rgba() so marker opacity can ride along.
export function intensityColor(intensity, alpha = 0.85) {
  const t = Math.max(0, Math.min(1, intensity));
  const r = Math.round(255);
  const g = Math.round(200 - 160 * t);
  const b = Math.round(80 - 80 * t);
  return `rgba(${r},${g},${b},${alpha})`;
}
