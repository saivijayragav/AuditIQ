import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "./components/layout/AppShell";
import { DashboardPage } from "./pages/DashboardPage";
import { NewEngagementPage } from "./pages/NewEngagementPage";
import { OverviewPage } from "./pages/engagement/OverviewPage";
import { IngestTbPage } from "./pages/engagement/IngestTbPage";
import { TbLinesPage } from "./pages/engagement/TbLinesPage";
import { MappingPage } from "./pages/engagement/MappingPage";
import { IngestFsPage } from "./pages/engagement/IngestFsPage";
import { FsReviewPage } from "./pages/engagement/FsReviewPage";
import { MaterialityPage } from "./pages/engagement/MaterialityPage";
import { ReconPage } from "./pages/engagement/ReconPage";
import { ExceptionsPage } from "./pages/engagement/ExceptionsPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: (failureCount, error: any) => {
        // Do not retry 4xx errors
        if (error?.status >= 400 && error?.status < 500) return false;
        return failureCount < 2;
      },
      staleTime: 5_000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="engagements/new" element={<NewEngagementPage />} />
            <Route path="engagements/:id" element={<OverviewPage />} />
            <Route path="engagements/:id/ingest-tb" element={<IngestTbPage />} />
            <Route path="engagements/:id/tb-lines" element={<TbLinesPage />} />
            <Route path="engagements/:id/mapping" element={<MappingPage />} />
            <Route path="engagements/:id/ingest-fs" element={<IngestFsPage />} />
            <Route path="engagements/:id/fs-review" element={<FsReviewPage />} />
            <Route path="engagements/:id/materiality" element={<MaterialityPage />} />
            <Route path="engagements/:id/recon" element={<ReconPage />} />
            <Route path="engagements/:id/exceptions" element={<ExceptionsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
