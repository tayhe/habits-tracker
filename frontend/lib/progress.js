// Progress bar / cat emoji tiers.
//
// Mirrors `backend/rules.py` (`progress_emoji`, `progress_bar`). There is no way
// to share one implementation between Python and JS without a round trip, so
// `scripts/parity_check.sh` asserts the two stay in sync instead.

export function progressEmoji(completed, total) {
  if (total === 0) return '😿';
  const rate = completed / total;
  if (rate >= 1.0) return '😺🎉';
  if (rate >= 0.75) return '😺';
  if (rate >= 0.5) return '😸';
  if (rate >= 0.25) return '😼';
  if (rate > 0) return '😾';
  return '😿';
}

export function progressBar(completed, total, maxLen = 15) {
  if (total === 0) return '░'.repeat(Math.min(4, maxLen));
  const len = Math.min(total, maxLen);
  const filled = Math.round((completed / total) * len);
  return '▓'.repeat(filled) + '░'.repeat(len - filled);
}
