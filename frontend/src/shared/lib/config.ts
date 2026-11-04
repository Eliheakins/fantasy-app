const DEFAULT_API_BASE = "http://localhost:8100";

export const START_API_HINT = "Start it with: cd backend && uv run uvicorn main:app --port 8100";

interface BaseUrlEnv {
  VITE_API_BASE_URL?: string;
  VITE_DATA_BASE_URL?: string;
}

function readUrl(name: string, raw: string | undefined): string | undefined {
  if (raw === undefined || raw.trim() === "") {
    return undefined;
  }
  let url: URL;
  try {
    url = new URL(raw.trim());
  } catch {
    throw new Error(`${name} must be an http(s) URL, got "${raw}".`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`${name} must be an http(s) URL, got "${raw}".`);
  }
  return raw.trim().replace(/\/+$/, "");
}

/**
 * Where the app finds things. The data (manifest, players, Parquet shards) comes from one base
 * URL, so pointing it at a CDN needs no code change; the API only serves the question endpoint.
 */
export function resolveBaseUrls(env: BaseUrlEnv): { apiBase: string; dataBase: string } {
  const apiBase = readUrl("VITE_API_BASE_URL", env.VITE_API_BASE_URL) ?? DEFAULT_API_BASE;
  const dataBase = readUrl("VITE_DATA_BASE_URL", env.VITE_DATA_BASE_URL) ?? `${apiBase}/data`;
  return { apiBase, dataBase };
}

export function joinUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}

const urls = resolveBaseUrls(import.meta.env);

export const API_BASE = urls.apiBase;
export const DATA_BASE_URL = urls.dataBase;
