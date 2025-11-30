/**
 * Format cost for display.
 */
export function formatCost(cost) {
  if (cost === null || cost === undefined) return '$??';
  return `$${cost.toFixed(2)}`;
}

/**
 * Format stats (elapsed time and cost) for display.
 * Returns formatted string or null if no stats available.
 */
export function formatStats(elapsed_time, cost) {
  const costStr = formatCost(cost);
  const parts = [];
  if (elapsed_time) parts.push(`${elapsed_time}s`);
  if (costStr) parts.push(costStr);
  return parts.length > 0 ? parts.join(', ') : null;
}
