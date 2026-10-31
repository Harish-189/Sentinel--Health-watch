import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";
import { color, font } from "../theme";

echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  MarkAreaComponent,
  MarkPointComponent,
  SVGRenderer,
]);

export type Option = echarts.EChartsCoreOption;

const reduced = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Shared recessive axis styling. */
export const axis = {
  axisLine: { lineStyle: { color: color.borderStrong } },
  axisTick: { show: false },
  axisLabel: { color: color.textMuted, fontFamily: font.mono, fontSize: 10.5 },
  splitLine: { lineStyle: { color: color.grid } },
};

export const tooltip = {
  trigger: "axis" as const,
  backgroundColor: "rgba(255,252,250,0.97)",
  borderColor: color.borderStrong,
  borderWidth: 1,
  padding: [8, 10],
  textStyle: { color: color.text, fontFamily: font.sans, fontSize: 12 },
  axisPointer: { type: "line" as const, lineStyle: { color: "rgba(46,158,163,0.5)", width: 1 } },
  extraCssText: "border-radius:10px;box-shadow:0 10px 30px rgba(15,63,67,.18);backdrop-filter:blur(8px);",
};

export function EChart({ option, height = 220, onReady }: { option: Option; height?: number | string; onReady?: (c: echarts.ECharts) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current, undefined, { renderer: "svg" });
    chart.current = c;
    onReady?.(c);
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    chart.current?.setOption(
      { animation: !reduced(), animationDuration: 700, animationEasing: "cubicOut", textStyle: { fontFamily: font.sans }, ...option },
      { notMerge: true },
    );
  }, [option]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}
