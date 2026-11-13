import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { createAppQueryClient } from "@/api/queryClient";
import { LeagueProvider } from "@/lib/league";
import { router } from "@/routes";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/newsreader/500.css";
import "@fontsource/newsreader/600.css";
import "@fontsource/newsreader/500-italic.css";
import "./index.css";

const queryClient = createAppQueryClient();
const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <LeagueProvider>
        <RouterProvider router={router} />
      </LeagueProvider>
    </QueryClientProvider>
  </StrictMode>,
);
