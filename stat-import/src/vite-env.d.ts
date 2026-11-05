/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Where the question endpoint lives. Default http://localhost:8100. */
  readonly VITE_API_BASE_URL?: string;
  /** Where manifest.json, players.json and the Parquet shards live. Default `${VITE_API_BASE_URL}/data`. */
  readonly VITE_DATA_BASE_URL?: string;
}
