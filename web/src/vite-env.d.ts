/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the stat app that player links open; defaults to http://localhost:3000. */
  readonly VITE_STAT_APP_URL?: string;
}
