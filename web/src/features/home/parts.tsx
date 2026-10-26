import type { ReactNode } from "react";

export function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-caption text-muted">{label}</dt>
      <dd className="text-display">{value}</dd>
    </div>
  );
}

/** A captioned part of a league card; the h3 sits under the card's h2. */
export function Block({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section aria-label={title} className="mt-6">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-body font-semibold">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}
