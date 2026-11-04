import { create } from "zustand";

/**
 * Interface state only: the query string of the last Explore page, so the "Explore" tab returns to
 * it after a visit to Ask. The query itself lives in the URL.
 */
interface RouteMemory {
  exploreSearch: string;
  rememberExplore: (search: string) => void;
}

export const useRouteMemory = create<RouteMemory>((set) => ({
  exploreSearch: "",
  rememberExplore: (search) => set({ exploreSearch: search }),
}));
