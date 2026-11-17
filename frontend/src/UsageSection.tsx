import { useMemo, useState } from "react";
import { Link } from "react-router";
import { request } from "./api";
import { Badge, Card, Empty, ErrorBox } from "./components";
import { OverviewChart, type OverviewBucket, type OverviewSeries } from "./OverviewChart";
import { useAsync } from "./useAsync";
import { Sparkline } from "./UsageChart";
import { OTHER_COLOR, TOP_N, money, usageApi, type UsageProvider } from "./usage";

type OverviewProvider = {
  id: number;
  name: string;
  display_name: string;
  kind: string;
  color: string | null;
  missing_price: boolean;
  values: number[];
  selected_cost: number;
};
type Overview = { days: number; kind: string; buckets: OverviewBucket[]; providers: OverviewProvider[] };

const FALLBACK = ["#D85A30", "#7F77DD", "#1D9E75", "#D4537E", "#378ADD", "#BA7517", "#639922"];
const HIDDEN_KEY = "usage.hiddenProviders";

function loadHidden(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(HIDDEN_KEY) ?? "[]"));
  } catch {
    return new Set();
  }
}

function saveHidden(hidden: Set<string>) {
  try {
    localStorage.setItem(HIDDEN_KEY, JSON.stringify([...hidden]));
  } catch {
    /* 저장 못 해도 이번 화면에서는 적용된다 */
  }
}

function Seg<T extends string | number>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-zinc-300 text-xs dark:border-zinc-700">
      {options.map(([v, label]) => (
        <button
          key={String(v)}
          onClick={() => onChange(v)}
          className={`px-2.5 py-1 ${value === v ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Row({ p, color, total }: { p: UsageProvider; color: string; total: number }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_60px_64px_34px] items-center gap-2 border-t border-zinc-100 py-1.5 text-xs first:border-t-0 dark:border-zinc-800">
      <span className="flex min-w-0 items-center gap-1.5">
        <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: color }} />
        <span className="truncate">{p.display_name}</span>
        {p.missing_price && <Badge tone="amber">단가 없음</Badge>}
      </span>
      <Sparkline values={p.series} color={color} />
      <span className="text-right tabular-nums">{p.missing_price && p.cost === 0 ? "—" : money(p.cost)}</span>
      <span className="text-right text-zinc-500 tabular-nums">{total > 0 ? Math.round((p.cost / total) * 100) : 0}</span>
    </div>
  );
}

export type UsageDays = 7 | 15 | 30;

/**
 * 홈 화면의 AI 사용량.
 * 한 차트에 최근 3달(월별 일평균) · 최근 4주(주별 일평균) · 선택 기간(일별)을 빈 칸으로 나눠 보여주고,
 * 서비스를 골라 볼 수 있다.
 */
export default function UsageSection({ days, onDaysChange }: { days: UsageDays; onDaysChange: (d: UsageDays) => void }) {
  const [kind, setKind] = useState<"all" | "text" | "media">("all");
  const [showAll, setShowAll] = useState(false);
  const [hidden, setHidden] = useState<Set<string>>(loadHidden);
  const overview = useAsync(() => request<Overview>(`/api/usage/overview?days=${days}&kind=${kind}`), [days, kind]);
  const summary = useAsync(() => usageApi.summary(days, kind), [days, kind]);

  // 서비스마다 고정 색 (가려도 다른 서비스 색이 바뀌지 않게)
  const colorOf = useMemo(() => {
    const map = new Map<string, string>();
    (overview.data?.providers ?? []).forEach((p, i) => map.set(p.name, p.color || FALLBACK[i % FALLBACK.length]));
    return (name: string) => map.get(name) ?? OTHER_COLOR;
  }, [overview.data]);

  const visible = useMemo(() => (overview.data?.providers ?? []).filter((p) => !hidden.has(p.name)), [overview.data, hidden]);

  const series = useMemo<OverviewSeries[]>(() => {
    const top = visible.slice(0, TOP_N).map((p) => ({ label: p.display_name, color: colorOf(p.name), values: p.values }));
    const rest = visible.slice(TOP_N);
    if (rest.length && overview.data) {
      top.push({
        label: `기타 ${rest.length}개`,
        color: OTHER_COLOR,
        values: overview.data.buckets.map((_, i) => rest.reduce((s, p) => s + (p.values[i] ?? 0), 0)),
      });
    }
    return top;
  }, [visible, colorOf, overview.data]);

  function toggle(name: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      saveHidden(next);
      return next;
    });
  }

  const ranking = (summary.data?.providers ?? []).filter((p) => !hidden.has(p.name));
  const rankingTotal = ranking.reduce((s, p) => s + p.cost, 0);
  const shownRanking = showAll ? ranking : ranking.slice(0, TOP_N);
  const missing = (summary.data?.providers ?? []).filter((p) => p.missing_price);
  const allProviders = overview.data?.providers ?? [];
  const error = overview.error || summary.error;

  return (
    <Card
      title="AI 사용량"
      action={
        <div className="flex flex-wrap items-center gap-1.5">
          <Seg value={kind} onChange={setKind} options={[["all", "전체"], ["text", "텍스트"], ["media", "미디어"]]} />
          <Seg value={days} onChange={onDaysChange} options={[[7, "7일"], [15, "15일"], [30, "30일"]]} />
        </div>
      }
    >
      {error && <ErrorBox message={error} />}
      {missing.length > 0 && (
        <Link
          to="/usage"
          className="mb-3 block rounded-md bg-blue-50 px-3 py-2 text-xs text-blue-800 hover:underline dark:bg-blue-950/40 dark:text-blue-300"
        >
          단가가 없는 provider {missing.length}개: {missing.map((p) => p.display_name).join(", ")} · 단가를 넣으면 비용에 포함됩니다 →
        </Link>
      )}

      {allProviders.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          <span className="mr-1 text-[11px] text-zinc-500">서비스</span>
          {allProviders.map((p) => {
            const on = !hidden.has(p.name);
            return (
              <button
                key={p.id}
                onClick={() => toggle(p.name)}
                aria-pressed={on}
                className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${
                  on ? "border-zinc-400 text-zinc-800 dark:border-zinc-600 dark:text-zinc-200" : "border-zinc-200 text-zinc-400 line-through dark:border-zinc-800 dark:text-zinc-600"
                }`}
              >
                <span className="h-2 w-2 rounded-sm" style={{ background: on ? colorOf(p.name) : "transparent", border: `1px solid ${colorOf(p.name)}` }} />
                {p.display_name}
              </button>
            );
          })}
          {hidden.size > 0 && (
            <button
              onClick={() => {
                const next = new Set<string>();
                saveHidden(next);
                setHidden(next);
              }}
              className="text-xs text-blue-600 hover:underline dark:text-blue-400"
            >
              모두 보기
            </button>
          )}
        </div>
      )}

      {overview.loading && !overview.data ? (
        <p className="py-10 text-center text-sm text-zinc-500">불러오는 중…</p>
      ) : !overview.data || allProviders.length === 0 ? (
        <Empty>기록된 사용량이 없습니다.</Empty>
      ) : visible.length === 0 ? (
        <Empty>보여 줄 서비스를 하나 이상 고르세요.</Empty>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
          <OverviewChart buckets={overview.data.buckets} series={series} />
          <div>
            <div className="grid grid-cols-[minmax(0,1fr)_60px_64px_34px] gap-2 pb-1 text-[11px] text-zinc-500">
              <span>최근 {days}일</span>
              <span>추이</span>
              <span className="text-right">비용</span>
              <span className="text-right">%</span>
            </div>
            {shownRanking.map((p) => (
              <Row key={p.id} p={p} color={colorOf(p.name)} total={rankingTotal} />
            ))}
            <div className="mt-2 flex items-center justify-between text-xs">
              {ranking.length > TOP_N ? (
                <button onClick={() => setShowAll(!showAll)} className="text-blue-600 hover:underline dark:text-blue-400">
                  {showAll ? "상위 5개만 보기" : `나머지 ${ranking.length - TOP_N}개 보기`}
                </button>
              ) : (
                <span />
              )}
              <Link to="/usage" className="text-zinc-500 hover:underline">
                사용량 화면에서 자세히 →
              </Link>
            </div>
          </div>
        </div>
      )}
      <p className="mt-3 text-[11px] text-zinc-500">
        월·주 막대는 그 기간의 하루 평균 비용입니다 (이번 달·이번 주는 오늘까지 기준). 비용은 API 단가로 환산한 값이며, Claude는 Team 플랜 사용
        한도에서 차감되고 따로 청구되지 않습니다.
      </p>
    </Card>
  );
}
