// Amounts are integer cents everywhere in code; dollars exist only in
// rendering (018). Both helpers work on strings and integers so no
// amount ever passes through floating point.

export function formatUsd(cents) {
  const whole = Math.trunc(cents / 100);
  const fraction = String(Math.abs(cents % 100)).padStart(2, "0");
  return `$${whole.toLocaleString()}.${fraction}`;
}

// Plain editable text for a price input: 4990 -> "49.90".
export function centsToDollarsText(cents) {
  return `${Math.trunc(cents / 100)}.${String(cents % 100).padStart(2, "0")}`;
}

// "49", "49.9", "$49.90" -> 4990; anything else -> null.
export function dollarsToCents(text) {
  const match = /^\s*\$?\s*(\d+)(?:\.(\d{1,2}))?\s*$/.exec(text);
  if (!match) return null;
  return Number(match[1]) * 100 + Number((match[2] || "0").padEnd(2, "0"));
}
