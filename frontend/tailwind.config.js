/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        app: "var(--color-app)",
        surface: "var(--color-surface)",
        ink: "var(--color-ink)",
        "ink-muted": "var(--color-ink-muted)",
        border: "var(--color-border)",
        primary: "var(--color-primary)",
        accent: "var(--color-accent)",
        "accent-muted": "var(--color-accent-muted)",
        "accent-subtle": "var(--color-accent-subtle)",
        danger: "var(--color-danger)",
        "danger-fg": "var(--color-danger-fg)",
        input: "var(--color-input)",
        "warn-fg": "var(--color-warn-fg)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
