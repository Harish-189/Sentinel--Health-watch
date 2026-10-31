import { Gauge } from "lucide-react";
import { EmptyState, Panel } from "../components/ui";

export default function Evaluation() {
  return (
    <Panel title="Evaluation" subtitle="Sentinel vs a single-threshold baseline over 100 seeded simulations">
      <EmptyState icon={<Gauge size={18} />} title="Evaluation report not generated yet" body="Run the eval harness to compare sensitivity, false-alarm rate, lead time and calibration against the threshold baseline." />
    </Panel>
  );
}
