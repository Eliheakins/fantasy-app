import { useState } from "react";

/** TEMPORARY comparison tool: delete this file, its TopBar line and the other two token sets once a theme is chosen. */
const THEMES = [
  { id: "a", name: "Graphite", page: "#131417", surface: "#1c1e23", accent: "#8ab4f8" },
  { id: "b", name: "Copper", page: "#151210", surface: "#1f1a17", accent: "#d28e62" },
  { id: "c", name: "Terminal", page: "#090d13", surface: "#0f1520", accent: "#2ec4b6" },
] as const;

function currentTheme(): string {
  return document.documentElement.getAttribute("data-theme") ?? "a";
}

export function ThemeSwitcher() {
  const [active, setActive] = useState(currentTheme);

  const choose = (id: string) => {
    document.documentElement.setAttribute("data-theme", id);
    try {
      localStorage.setItem("fantasy-theme", id);
    } catch {
      // storage blocked: the choice lasts until reload
    }
    setActive(id);
  };

  return (
    <div role="group" aria-label="Theme comparison (temporary)" className="flex items-center gap-1.5">
      <span className="hidden text-caption text-muted md:inline">Theme (temp)</span>
      {THEMES.map((t) => (
        <button
          key={t.id}
          type="button"
          aria-label={`Theme ${t.id.toUpperCase()}: ${t.name}`}
          aria-pressed={active === t.id}
          title={`${t.id.toUpperCase()}: ${t.name}`}
          onClick={() => choose(t.id)}
          className="size-7 rounded-full border border-[#808690] p-0.5 aria-pressed:ring-2 aria-pressed:ring-ring aria-pressed:ring-offset-2 aria-pressed:ring-offset-page"
          style={{ background: `conic-gradient(${t.accent} 0 33%, ${t.surface} 33% 66%, ${t.page} 66% 100%)` }}
        />
      ))}
    </div>
  );
}
