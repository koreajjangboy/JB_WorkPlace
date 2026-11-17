import { useMemo, useState } from "react";
import { Link } from "react-router";
import { Badge, Card, Empty, ErrorBox } from "./components";
import { useAsync } from "./useAsync";
import { Sparkline, UsageChart, type AverageLine } from "./UsageChart";
import { OTHER_COLOR, money, topProviders, usageApi, type UsageProvider } from "./usage";

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

const AVG_LONG_DAYS = 90; // 최근 3달
const AVG_SHORT_DAYS = 28; // 최근 4주
const AVG_LONG_COLOR = "#E24B4A";
const AVG_SHORT_COLOR = "#378ADD";

/** 90일 일별 합계에서 최근 3달·4주 일평균을 구한다. */
function dailyAverages(providers: UsageProvider[], length: number) {
  const totals = Array.from({ length }, (_, i) => providers.reduce((s, p) => s + (p.series[i] ?? 0), 0));
  const avg = (n: number) => totals.slice(-n).reduce((s, v) => s + v, 0) / Math.min(n, Math.max(1, totals.length));
  return { long: avg(AVG_LONG_DAYS), short: avg(AVG_SHORT_DAYS) };
}

/** 홈 화면의 AI 사용량: 비용 기준, 상위 5개 provider + 기타, 3달·4주 일평균 기준선. */
export default function UsageSection({ days, onDaysChange }: { days: UsageDays; onDaysChange: (d: UsageDays) => void }) {
  const [kind, setKind] = useState<"all" | "text" | "media">("all");
  const [showAll, setShowAll] = useState(false);
  const { data, error, loading } = useAsync(() => usageApi.summary(days, kind), [days, kind]);
  const longRange = useAsync(() => usageApi.summary(AVG_LONG_DAYS, kind), [kind]);

  const avg = useMemo(
    () => (longRange.data ? dailyAverages(longRange.data.providers, longRange.data.labels.length) : null),
    [longRange.data],
  );
  const averages = useMemo<AverageLine[]>(
    () =>
      avg
        ? [
            { label: "최근 3달 일평균", value: avg.long, color: AVG_LONG_COLOR, dash: [6, 4] },
            { label: "최근 4주 일평균", value: avg.short, color: AVG_SHORT_COLOR, dash: [2, 3] },
          ]
        : [],
    [avg],
  );

  const { top, rest } = topProviders(data?.providers ?? []);
  const missing = (data?.providers ?? []).filter((p) => p.missing_price);
  const shown = showAll ? [...top, ...rest.map((p) => ({ ...p, color: OTHER_COLOR }))] : top;

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
      {loading && !data ? (
        <p className="py-10 text-center text-sm text-zinc-500">불러오는 중…</p>
      ) : !data || data.providers.length === 0 ? (
        <Empty>이 기간에 기록된 사용량이 없습니다.</Empty>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <div>
            <div className="mb-1.5 flex flex-wrap gap-2.5 text-[11px] text-zinc-500">
              {top.map((p) => (
                <span key={p.id} className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-sm" style={{ background: p.color! }} />
                  {p.display_name}
                </span>
              ))}
              {rest.length > 0 && (
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-sm" style={{ background: OTHER_COLOR }} />
                  기타 {rest.length}개
                </span>
              )}
              {averages.map((a) => (
                <span key={a.label} className="flex items-center gap-1">
                  <svg width="14" height="4" aria-hidden="true">
                    <line x1="0" y1="2" x2="14" y2="2" stroke={a.color} strokeWidth="1.5" strokeDasharray={a.dash?.join(" ")} />
                  </svg>
                  {a.label} {money(a.value)}
                </span>
              ))}
            </div>
            <UsageChart labels={data.labels} providers={data.providers} averages={averages} />
          </div>
          <div>
            <div className="grid grid-cols-[minmax(0,1fr)_60px_64px_34px] gap-2 pb-1 text-[11px] text-zinc-500">
              <span>Provider</span>
              <span>추이</span>
              <span className="text-right">비용</span>
              <span className="text-right">%</span>
            </div>
            {shown.map((p) => (
              <Row key={p.id} p={p} color={p.color || OTHER_COLOR} total={data.total_cost} />
            ))}
            <div className="mt-2 flex items-center justify-between text-xs">
              {rest.length > 0 ? (
                <button onClick={() => setShowAll(!showAll)} className="text-blue-600 hover:underline dark:text-blue-400">
                  {showAll ? "상위 5개만 보기" : `나머지 ${rest.length}개 보기`}
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
        비용은 API 단가로 환산한 값입니다. Claude는 Team 플랜 사용 한도에서 차감되며 따로 청구되지 않습니다.
      </p>
    </Card>
  );
}
