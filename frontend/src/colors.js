// Intensity -> color ramp: cool amber for quiet events up to hot red-orange
// for high-buzz ones. Returns rgba() so marker opacity can ride along.
export function intensityColor(intensity, alpha = 0.85) {
  const t = Math.max(0, Math.min(1, intensity));
  const r = Math.round(255);
  const g = Math.round(200 - 160 * t);
  const b = Math.round(80 - 80 * t);
  return `rgba(${r},${g},${b},${alpha})`;
}

// GDELT AvgTone (roughly -10..+10) -> diverging sentiment scale.
// Color-blind-safe red<->blue (ColorBrewer RdBu endpoints): negative = red,
// neutral = pale slate, positive = blue. Avoids red-green confusion while
// keeping the "warm = negative" convention.
const TONE_NEG = [214, 47, 39]; // #d62f27
const TONE_MID = [190, 195, 205]; // pale slate (readable on the dark globe)
const TONE_POS = [33, 102, 172]; // #2166ac

function lerp3(a, b, t) {
  return a.map((v, i) => Math.round(v + (b[i] - v) * t));
}

export function toneColor(tone, alpha = 0.85) {
  if (tone == null) return `rgba(150,150,160,${alpha})`;
  const t = Math.max(-1, Math.min(1, tone / 8)); // clamp to [-1, 1]
  const [r, g, b] =
    t < 0 ? lerp3(TONE_MID, TONE_NEG, -t) : lerp3(TONE_MID, TONE_POS, t);
  return `rgba(${r},${g},${b},${alpha})`;
}
