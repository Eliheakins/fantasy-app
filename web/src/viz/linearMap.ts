/** A linear map from a domain onto a pixel range; inputs outside the domain clamp to the range ends. */
export function clampedLinear(domain: readonly [number, number], range: readonly [number, number]): (value: number) => number {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  // A zero-width domain has no scale; put everything mid-range instead of dividing by zero.
  if (d0 === d1) return () => (r0 + r1) / 2;
  return (value) => {
    const t = Math.min(1, Math.max(0, (value - d0) / (d1 - d0)));
    return r0 + t * (r1 - r0);
  };
}
