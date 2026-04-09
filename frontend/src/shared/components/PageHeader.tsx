import type { ReactNode } from "react";

import { cn } from "@/shared/lib/utils";

export interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  className?: string;
  titleAs?: "h1" | "h2";
}

export function PageHeader({ eyebrow, title, description, className, titleAs = "h1" }: PageHeaderProps) {
  const TitleTag = titleAs;
  return (
    <header className={cn("space-y-1", className)}>
      {eyebrow ? (
        <p className="text-xs font-semibold uppercase tracking-widest text-accent-muted">{eyebrow}</p>
      ) : null}
      <TitleTag className="text-xl font-bold tracking-tight text-ink lg:text-2xl">{title}</TitleTag>
      {description ? <div className="max-w-2xl text-xs text-ink-muted lg:text-sm">{description}</div> : null}
    </header>
  );
}
