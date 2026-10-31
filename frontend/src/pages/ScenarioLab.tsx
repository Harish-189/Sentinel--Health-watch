import { Beaker } from "lucide-react";
import { EmptyState, Panel } from "../components/ui";

export default function ScenarioLab() {
  return (
    <Panel title="Scenario Lab" subtitle="Inject a scenario and watch the evidence change">
      <EmptyState icon={<Beaker size={18} />} title="No scenario injected" body="Pick a confounder (holiday, reporting change, lab backlog…) to see the evidence delta: tier before/after, changed signals and hypothesis movement." />
    </Panel>
  );
}
