import type { ReactNode } from "react";

/** A link that opens in a new tab; the icon is decoration and the screen-reader suffix says what the link does. */
export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-block py-3 text-caption text-focus underline underline-offset-2 hover:text-forest"
    >
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
      <span aria-hidden> ↗</span>
    </a>
  );
}
