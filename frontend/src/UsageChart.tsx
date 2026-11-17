import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
  type ChartDataset,
} from "chart.js";
import { useEffect, useRef } from "react";
import { OTHER_COLOR, topProviders, type UsageProvider } from "./usage";

Chart.register(BarController, BarElement, LineController, LineElement, PointElement, CategoryScale, LinearScale, Tooltip);

/** 차트 위에 가로선으로 겹쳐 그리는 일평균 기준선 */
export type AverageLine = { label: string; value: number; color: string; dash?: number[] };

/** 일별 비용 누적 막대: 상위 5개 provider + 기타. averages가 있으면 가로 기준선을 함께 그린다. */
export function UsageChart({
  labels,
  providers,
  averages = [],
  height = 220,
}: {
  labels: string[];
  providers: UsageProvider[];
  averages?: AverageLine[];
  height?: number;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const chart = useRef<Chart | null>(null);

  useEffect(() => {
    if (!canvas.current) return;
    const { top, rest } = topProviders(providers);
    const datasets: ChartDataset<"bar" | "line", number[]>[] = top.map((p) => ({
      type: "bar" as const,
      label: p.display_name,
      data: p.series,
      backgroundColor: p.color!,
      borderRadius: 2,
      maxBarThickness: 28,
      stack: "cost",
      order: 1,
    }));
    if (rest.length) {
      datasets.push({
        type: "bar" as const,
        label: `기타 ${rest.length}개`,
        data: labels.map((_, i) => rest.reduce((s, p) => s + (p.series[i] ?? 0), 0)),
        backgroundColor: OTHER_COLOR,
        borderRadius: 2,
        maxBarThickness: 28,
        stack: "cost",
        order: 1,
      });
    }
    averages.forEach((a, i) => {
      datasets.push({
        type: "line" as const,
        label: a.label,
        data: labels.map(() => a.value),
        borderColor: a.color,
        backgroundColor: a.color,
        borderWidth: 1.5,
        borderDash: a.dash ?? [],
        pointRadius: 0,
        pointHoverRadius: 0,
        fill: false,
        stack: `avg${i}`, // 막대나 다른 기준선과 누적되지 않도록 각자 stack
        order: 0, // 막대 위에 그린다
      });
    });
    const short = labels.map((d) => {
      const [, m, day] = d.split("-");
      return `${Number(m)}/${Number(day)}`;
    });
    chart.current?.destroy();
    chart.current = new Chart(canvas.current, {
      type: "bar",
      data: { labels: short, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            mode: "index",
            intersect: false,
            filter: (item) => (item.raw as number) > 0,
            itemSort: (a, b) => a.datasetIndex - b.datasetIndex,
            callbacks: { label: (c) => `${c.dataset.label}: $${(c.raw as number).toFixed(2)}` },
          },
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { color: "#888780", font: { size: 11 }, maxRotation: 0, autoSkip: true } },
          y: {
            stacked: true,
            grid: { color: "rgba(136,135,128,0.18)" },
            border: { display: false },
            ticks: { color: "#888780", font: { size: 11 }, callback: (v) => `$${v}` },
          },
        },
      },
    });
    return () => {
      chart.current?.destroy();
      chart.current = null;
    };
  }, [labels, providers, averages]);

  return (
    <div style={{ position: "relative", height }}>
      <canvas ref={canvas} role="img" aria-label="provider별 일별 비용 누적 막대 차트" />
    </div>
  );
}

/** 작은 추이 그래프 */
export function Sparkline({ values, color }: { values: number[]; color: string }) {
  const max = Math.max(...values, 0.0001);
  const pts = values
    .map((v, i) => `${((i * 60) / Math.max(1, values.length - 1)).toFixed(1)},${(18 - (v / max) * 16).toFixed(1)}`)
    .join(" ");
  return (
    <svg width="60" height="20" viewBox="0 0 60 20" aria-hidden="true">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}
