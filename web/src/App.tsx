import { Route, HashRouter, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { AttackStudioPage } from "./pages/AttackStudioPage";
import { AttackTaxonomyPage } from "./pages/AttackTaxonomyPage";
import { CoEvolutionPage } from "./pages/CoEvolutionPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { LiveDetectionPage } from "./pages/LiveDetectionPage";
import { OverviewPage } from "./pages/OverviewPage";
import { LoopProvider } from "./state/LoopContext";

export default function App() {
  return (
    <LoopProvider>
      <HashRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="attack-studio" element={<AttackStudioPage />} />
            <Route path="live-detection" element={<LiveDetectionPage />} />
            <Route path="co-evolution" element={<CoEvolutionPage />} />
            <Route path="attack-taxonomy" element={<AttackTaxonomyPage />} />
            <Route path="evaluation" element={<EvaluationPage />} />
          </Route>
        </Routes>
      </HashRouter>
    </LoopProvider>
  );
}
