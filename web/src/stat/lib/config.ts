/** The stat routes are served by the fantasy API itself, so every URL is relative to the page's origin. */
export const API_BASE = "/api/stat";
export const DATA_BASE_URL = `${API_BASE}/data`;

export const BUILD_DATA_HINT = "Build the data with: make stat-data";
export const START_API_HINT = "Start it with: make serve";
/** For a failed shard read, which is either an unbuilt file or a server that is down. */
export const DATA_READ_HINT = `${BUILD_DATA_HINT}, and start the app with: make serve`;

export function joinUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}
