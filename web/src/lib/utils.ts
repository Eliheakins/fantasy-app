import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/** The theme's named font sizes (index.css); without them tailwind-merge reads `text-body` as a colour and drops `text-white`. */
const twMerge = extendTailwindMerge({
  extend: { theme: { text: ["h1", "section", "display", "title", "heading", "body", "caption"] } },
});

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
