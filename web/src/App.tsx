import { Navigate, Route, HashRouter, Routes } from "react-router-dom";
import { useWarmup } from "./api/useWarmup";
import { AppShell } from "./components/layout/AppShell";
import { AttackTaxonomyPage } from "./pages/AttackTaxonomyPage";
import { CoEvolutionPage } from "./pages/CoEvolutionPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { FinalBenchmarkPage } from "./pages/FinalBenchmarkPage";
import { LiveDetectionPage } from "./pages/LiveDetectionPage";
import { AttackLabPage } from "./pages/AttackLabPage";
import { MissionControlPage } from "./pages/MissionControlPage";
import { SandboxPage } from "./pages/SandboxPage";
import { LoopProvider } from "./state/LoopContext";

export default function App() {
  // Fire-and-forget /api/health ping at mount so a spun-down Render instance
  // starts waking before the reader navigates anywhere.
  useWarmup();
  return (
    <LoopProvider>
      <HashRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<MissionControlPage />} />
            <Route path="attack-lab" element={<AttackLabPage />} />
            <Route path="live-detection" element={<LiveDetectionPage />} />
            <Route path="co-evolution" element={<CoEvolutionPage />} />
            <Route path="attack-taxonomy" element={<AttackTaxonomyPage />} />
            <Route path="evaluation" element={<EvaluationPage />} />
            <Route path="final-benchmark" element={<FinalBenchmarkPage />} />
            <Route path="sandbox" element={<SandboxPage />} />
            {/* Kept as a redirect rather than deleted: /attack-studio is linked
                from docs/DEMO_FLOW.md and earlier deploy previews, and a dead
                link during judging is worse than a redirect. */}
            <Route path="attack-studio" element={<Navigate to="/sandbox" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </LoopProvider>
  );
}
