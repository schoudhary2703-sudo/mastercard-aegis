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

/**
 * Routes follow `nav/journey.ts`: Overview, then the four numbered loop
 * steps, then Results.
 *
 * `/attack-studio` is kept as a redirect rather than deleted -- it is linked
 * from docs/DEMO_FLOW.md and from earlier deploy previews, and a dead link
 * during judging is worse than a redirect. `/evaluation` stays reachable
 * (Results links into it for the full per-model metric set) but is out of the
 * nav, because its headline comparison is already Evidence 1 on Results.
 */
export default function App() {
  useWarmup();
  return (
    <LoopProvider>
      <HashRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<MissionControlPage />} />
            <Route path="attack-taxonomy" element={<AttackTaxonomyPage />} />
            <Route path="attack-lab" element={<AttackLabPage />} />
            <Route path="live-detection" element={<LiveDetectionPage />} />
            <Route path="co-evolution" element={<CoEvolutionPage />} />
            <Route path="final-benchmark" element={<FinalBenchmarkPage />} />
            <Route path="evaluation" element={<EvaluationPage />} />
            <Route path="sandbox" element={<SandboxPage />} />
            <Route path="attack-studio" element={<Navigate to="/sandbox" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </LoopProvider>
  );
}
