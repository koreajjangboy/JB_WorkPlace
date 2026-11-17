import { BarController, BarElement, CategoryScale, Chart, LinearScale, Tooltip } from "chart.js";
import { useEffect, useRef } from "react";

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip);

export type OverviewBucket = { group: "month" | "week" | "day"; label: string; start: string; days: number };
export type OverviewSeries = { label: string; color: string; values: number[] };

const GROUP_NAME = { month: "월별 일평균", week: "주별 일평균", day: "일별" } as const;
const GROUP_SHORT = { month: "월 평균", week: "주 평균", day: "일별" } as const;

/**
 * 월(최근 3달) · 주(최근 4주) · 일(선택 기간) 막대를 한 차트에 그린다.
 * 묶음 사이에 빈 칸을 넣어 구분하고, 막대는 서비스별로 쌓는다. 값은 모두 '하루 비용'.
 */
export function OverviewChart({ buckets, series, height = 260 }: { buckets: OverviewBucket[]; series: OverviewSeries[]; height?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const chart = useRef<Chart | null>(null);

  useEffect(() => {
    if (!canvas.current) return;
    // 묶음이 바뀌는 곳에 빈 칸(값 없음)을 끼워 넣는다.
    const labels: string[] = [];
    const slots: (number | null)[] = []; // 원래 bucket 인덱스, 빈 칸은 null
    buckets.forEach((b, i) => {
      if (i > 0 && buckets[i - 1].group !== b.group) {
        labels.push("");
        slots.push(null);
      }
      labels.push(b.label);
      slots.push(i);
    });
    // 일별 막대가 많으면 날짜 글자를 건너뛰어 표시한다 (오늘은 항상 표시). 월·주 글자는 모두 표시.
    const dayCount = buckets.filter((b) => b.group === "day").length;
    const step = Math.max(1, Math.ceil(dayCount / 10));
    const tickText = slots.map((i, pos) => {
      if (i == null) return "";
      const b = buckets[i];
      if (b.group !== "day") return buckets.length > 20 ? labels[pos].replace(/^[MW] /, "") : labels[pos];
      const fromEnd = buckets.length - 1 - i;
      return fromEnd % step === 0 ? labels[pos] : "";
    });
    const datasets = series.map((s) => ({
      label: s.label,
      data: slots.map((i) => (i == null ? null : s.values[i] ?? 0)),
      backgroundColor: s.color,
      borderRadius: 2,
      maxBarThickness: 34,
      categoryPercentage: 0.8,
    }));

    chart.current?.destroy();
    chart.current = new Chart(canvas.current, {
      type: "bar",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            mode: "index",
            intersect: false,
            filter: (item) => (item.raw as number | null) != null && (item.raw as number) > 0,
            callbacks: {
              title: (items) => {
                const i = slots[items[0]?.dataIndex ?? 0];
                if (i == null) return "";
                const b = buckets[i];
                return b.group === "day" ? `${b.label} (일별)` : `${b.label} · ${GROUP_NAME[b.group]} (${b.days}일 기준)`;
              },
              label: (c) => `${c.dataset.label}: $${(c.raw as number).toFixed(2)} / 일`,
              footer: (items) => {
                const total = items.reduce((s, it) => s + ((it.raw as number) || 0), 0);
                return items.length > 1 ? `합계 $${total.toFixed(2)} / 일` : "";
              },
            },
          },
        },
        scales: {
          x: {
            stacked: true,
            grid: { display: false },
            ticks: {
              color: "#888780",
              font: { size: buckets.length > 20 ? 10 : 11 },
              maxRotation: 0,
              autoSkip: false,
              callback: (_value, index) => tickText[index] ?? "",
            },
          },
          y: {
            stacked: true,
            beginAtZero: true,
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
  }, [buckets, series]);

  // 묶음 이름을 차트 아래에 표시 (막대 위치에 맞춘 비율로)
  const groups = (["month", "week", "day"] as const)
    .map((g) => ({ g, n: buckets.filter((b) => b.group === g).length }))
    .filter((x) => x.n > 0);
  const totalSlots = buckets.length + groups.length - 1;

  return (
    <div>
      <div style={{ position: "relative", height }}>
        <canvas ref={canvas} role="img" aria-label="월별·주별 일평균과 일별 비용을 서비스별로 쌓은 막대 차트" />
      </div>
      <div className="mt-1 flex pl-10 text-[11px] text-zinc-500">
        {groups.map(({ g, n }, idx) => (
          <div key={g} style={{ flex: `${n + (idx < groups.length - 1 ? 1 : 0)} 0 0` }} className="truncate text-center">
            <span className="border-t border-zinc-300 px-1 pt-0.5 dark:border-zinc-700">{n >= 5 ? GROUP_NAME[g] : GROUP_SHORT[g]}</span>
          </div>
        ))}
        {totalSlots === 0 && null}
      </div>
    </div>
  );
}
