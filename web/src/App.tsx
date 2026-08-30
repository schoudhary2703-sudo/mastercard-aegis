import { Route, HashRouter, Routes } from "react-router-dom";
import { useWarmup } from "./api/useWarmup";
import { AppShell } from "./components/layout/AppShell";
import { AttackStudioPage } from "./pages/AttackStudioPage";
import { AttackTaxonomyPage } from "./pages/AttackTaxonomyPage";
import { CoEvolutionPage } from "./pages/CoEvolutionPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { FinalBenchmarkPage } from "./pages/FinalBenchmarkPage";
import { LiveDetectionPage } from "./pages/LiveDetectionPage";
import { AttackLabPage } from "./pages/AttackLabPage";
import { MissionControlPage } from "./pages/MissionControlPage";
import { LoopProvider } from "./state/LoopContext";

export default function App() {
  useWarmup();
  return (
    <LoopProvider>
      <HashRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<MissionControlPage />} />
            <Route path="attack-lab" element={<AttackLabPage />} />
            <Route path="attack-studio" element={<AttackStudioPage />} />
            <Route path="live-detection" element={<LiveDetectionPage />} />
            <Route path="co-evolution" element={<CoEvolutionPage />} />
            <Route path="attack-taxonomy" element={<AttackTaxonomyPage />} />
            <Route path="evaluation" element={<EvaluationPage />} />
            <Route path="final-benchmark" element={<FinalBenchmarkPage />} />
          </Route>
        </Routes>
      </HashRouter>
    </LoopProvider>
  );
}
