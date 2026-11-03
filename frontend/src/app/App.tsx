import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { QueryBuilderPanel } from "@/features/explore/QueryBuilderPanel";
import { AskPage } from "@/app/pages/AskPage";
import { HomePage } from "@/app/pages/HomePage";
import { RootLayout } from "@/app/layouts/RootLayout";
import { WorkbenchLayout } from "@/app/layouts/WorkbenchLayout";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<RootLayout />}>
          <Route index element={<HomePage />} />
          <Route element={<WorkbenchLayout />}>
            <Route path="explore" element={<QueryBuilderPanel />} />
            <Route path="ask" element={<AskPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
