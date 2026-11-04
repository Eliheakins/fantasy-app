/** One message for everything that can stop the workbench from starting, or null if nothing did. */
export function describeStartupError(
  manifestError: string | null,
  engineError: string | null,
): string | null {
  const parts = [manifestError, engineError ? `DuckDB failed to start: ${engineError}` : null];
  const message = parts.filter((p): p is string => p !== null).join(" ");
  return message === "" ? null : message;
}
