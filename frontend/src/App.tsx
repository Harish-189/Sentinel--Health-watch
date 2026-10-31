import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { EvidenceDrawer, Onboarding } from "./components/Overlays";
import { Footer, Sidebar, TopBar } from "./components/Shell";
import { LoadingBlock } from "./components/ui";
import { useAnalysis, useCaseFile } from "./lib/api";
import { useEvidence } from "./lib/evidence";
import { useApp, type Page } from "./lib/state";
import ActionQueue from "./pages/ActionQueue";
import Capacity from "./pages/Capacity";
import CommandCenter from "./pages/CommandCenter";
import Evaluation from "./pages/Evaluation";
import Investigation from "./pages/Investigation";
import ScenarioLab from "./pages/ScenarioLab";
import SignalExplorer from "./pages/SignalExplorer";

const TITLES: Record<Page, string> = {
  command: "Command Center",
  signals: "Signal Explorer",
  investigation: "Investigation",
  capacity: "Capacity Forecast",
  actions: "Action Queue",
  evaluation: "Evaluation",
  lab: "Scenario Lab",
};

const ONBOARD_KEY = "sentinel.onboarded.v1";

/** Keeps the evidence drawer able to resolve IDs from whatever has been loaded. */
function EvidenceSync() {
  const { register } = useEvidence();
  const a = useAnalysis();
  const c = useCaseFile();
  useEffect(() => {
    if (a.data) register(a.data.evidence);
  }, [a.data, register]);
  useEffect(() => {
    if (c.data) register(c.data.evidence);
  }, [c.data, register]);
  return null;
}

export default function App() {
  const { page, ready } = useApp();
  const [help, setHelp] = useState(() => !localStorage.getItem(ONBOARD_KEY) && !window.location.search.includes("skipOnboarding"));
  const Body = { command: CommandCenter, signals: SignalExplorer, investigation: Investigation, capacity: Capacity, actions: ActionQueue, evaluation: Evaluation, lab: ScenarioLab }[page];

  return (
    <>
      <div className="backdrop" />
      <EvidenceSync />
      <div className="relative z-10 mx-auto flex min-h-full max-w-[1920px] gap-3 p-3">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <TopBar title={TITLES[page]} onHelp={() => setHelp(true)} />
          <AnimatePresence mode="wait">
            <motion.main key={page} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }} className="min-w-0 flex-1">
              {ready ? (
                <Body />
              ) : (
                <div className="glass p-6">
                  <LoadingBlock label="Connecting to the Sentinel API" rows={6} />
                </div>
              )}
            </motion.main>
          </AnimatePresence>
          <Footer />
        </div>
      </div>
      <EvidenceDrawer />
      <Onboarding
        open={help}
        onClose={() => {
          localStorage.setItem(ONBOARD_KEY, "1");
          setHelp(false);
        }}
      />
    </>
  );
}
