import { useEffect, useState } from "react";
import type { Limits, RateLimit, RunnerStatus } from "./api";
import { relativeTime } from "./format";

const LONG: Limits = { max_budget_usd: 10, max_minutes: 120 };

type Preset = "default" | "long" | "custom";

function presetOf(limits: Limits): Preset {
  if (limits.max_budget_usd == null && limits.max_minutes == null) return "default";
  if (limits.max_budget_usd === LONG.max_budget_usd && limits.max_minutes === LONG.max_minutes) return "long";
  return "custom";
}

export function describeLimits(limits: Limits, runner: Pick<RunnerStatus, "max_budget_usd" | "max_minutes">): string {
  const budget = limits.max_budget_usd ?? runner.max_budget_usd;
  const minutes = limits.max_minutes ?? runner.max_minutes;
  const isDefault = limits.max_budget_usd == null && limits.max_minutes == null;
  return `$${budget} · ${minutes}분${isDefault ? " (기본)" : ""}`;
}

/** 실행 한도 고르기: 기본 / 긴 작업 / 직접 입력. 기본은 null로 보내 서버 기본값을 쓴다. */
export function LimitPicker({
  value,
  onChange,
  runner,
}: {
  value: Limits;
  onChange: (limits: Limits) => void;
  runner: Pick<RunnerStatus, "max_budget_usd" | "max_minutes">;
}) {
  const [preset, setPreset] = useState<Preset>(presetOf(value));
  const [budget, setBudget] = useState(String(value.max_budget_usd ?? runner.max_budget_usd));
  const [minutes, setMinutes] = useState(String(value.max_minutes ?? runner.max_minutes));

  useEffect(() => setPreset(presetOf(value)), [value]);

  function choose(next: Preset) {
    setPreset(next);
    if (next === "default") onChange({ max_budget_usd: null, max_minutes: null });
    if (next === "long") onChange(LONG);
    if (next === "custom") onChange({ max_budget_usd: Number(budget) || runner.max_budget_usd, max_minutes: Number(minutes) || runner.max_minutes });
  }

  function custom(b: string, m: string) {
    setBudget(b);
    setMinutes(m);
    const nb = Number(b);
    const nm = Math.round(Number(m));
    onChange({
      max_budget_usd: nb > 0 ? Math.min(nb, 50) : runner.max_budget_usd,
      max_minutes: nm > 0 ? Math.min(nm, 480) : runner.max_minutes,
    });
  }

  const option = (key: Preset, label: string, hint: string) => (
    <label
      className={`flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 text-sm ${
        preset === key ? "border-blue-500 bg-blue-50 dark:bg-blue-950/40" : "border-zinc-300 dark:border-zinc-700"
      }`}
    >
      <input type="radio" checked={preset === key} onChange={() => choose(key)} className="mt-1" />
      <span>
        <span className="block font-medium">{label}</span>
        <span className="block text-xs text-zinc-500">{hint}</span>
      </span>
    </label>
  );

  return (
    <div className="space-y-2">
      <div className="grid gap-2 sm:grid-cols-3">
        {option("default", "짧은 작업", `$${runner.max_budget_usd} · ${runner.max_minutes}분 (기본)`)}
        {option("long", "긴 작업", `$${LONG.max_budget_usd} · ${LONG.max_minutes}분`)}
        {option("custom", "직접 입력", "최대 $50 · 480분")}
      </div>
      {preset === "custom" && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-1.5">
            비용 $
            <input
              type="number"
              min="0.1"
              max="50"
              step="0.5"
              value={budget}
              onChange={(e) => custom(e.target.value, minutes)}
              className="h-8 w-20 rounded-md border border-zinc-300 bg-white px-2 dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <label className="flex items-center gap-1.5">
            시간
            <input
              type="number"
              min="1"
              max="480"
              step="10"
              value={minutes}
              onChange={(e) => custom(budget, e.target.value)}
              className="h-8 w-20 rounded-md border border-zinc-300 bg-white px-2 dark:border-zinc-700 dark:bg-zinc-900"
            />
            분
          </label>
        </div>
      )}
    </div>
  );
}

function Meter({ label, value, resetsAt }: { label: string; value: number | null; resetsAt: string | null }) {
  const pct = value == null ? null : Math.round(value * 100);
  const color = pct == null ? "bg-zinc-400" : pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-blue-500";
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-zinc-600 dark:text-zinc-400">{label}</span>
        <span className="tabular-nums">
          <span className="text-sm font-semibold">{pct == null ? "—" : `${pct}%`}</span>
          {resetsAt && <span className="ml-1.5 text-zinc-500">{relativeTime(resetsAt)} 초기화</span>}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div className={`h-full ${color}`} style={{ width: `${Math.min(100, pct ?? 0)}%` }} />
      </div>
    </div>
  );
}

/** Claude 구독 사용 한도 (5시간·7일). WorkPlace 실행 때 Claude Code가 알려준 마지막 값. */
export function RateLimitView({ data }: { data: RateLimit | null }) {
  if (!data) {
    return <p className="text-xs text-zinc-500">WorkPlace에서 작업을 한 번 실행하면 Claude 사용 한도가 여기에 표시됩니다.</p>;
  }
  return (
    <div className="space-y-2.5">
      <Meter label="5시간 한도" value={data.five_hour_utilization} resetsAt={data.five_hour_resets_at} />
      <Meter label="7일 한도" value={data.seven_day_utilization} resetsAt={data.seven_day_resets_at} />
      <p className="text-[11px] text-zinc-500">
        {relativeTime(data.ts)} 기준 · 터미널 등 다른 곳에서 쓴 사용량도 포함된 값입니다
        {data.overage_status === "rejected" && " · 한도를 넘으면 추가 과금 없이 사용이 제한됩니다"}
      </p>
    </div>
  );
}
