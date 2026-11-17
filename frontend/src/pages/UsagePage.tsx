import { useMemo, useState } from "react";
import { Badge, Button, Card, ErrorBox, Loading } from "../components";
import { useAsync } from "../useAsync";
import { OVERVIEW_NOTE, ServiceChips, UsageOverviewChart, useUsageOverview } from "../UsageSection";
import { UNIT_LABEL, formatQuantity, money, usageApi, type PriceRule, type ProviderInfo, type UsageProvider } from "../usage";

const KINDS: [string, string][] = [
  ["text", "텍스트"],
  ["embedding", "임베딩"],
  ["image", "이미지"],
  ["video", "영상"],
  ["audio", "음성"],
  ["mixed", "혼합"],
];
const TOKEN_UNITS = ["input_token", "output_token", "cache_write_token", "cache_read_token"];

function isTokenUnit(unit: string) {
  return unit.endsWith("_token") || unit === "token";
}

/** 단가 표시: 토큰은 100만 개당, 나머지는 1단위당 */
function priceLabel(rule: PriceRule) {
  return isTokenUnit(rule.unit) ? `$${(rule.price_per_unit * 1_000_000).toFixed(3)} / 100만` : `$${rule.price_per_unit}`;
}

function PriceEditor({ provider, rules, onChanged }: { provider: ProviderInfo; rules: PriceRule[]; onChanged: () => void }) {
  const [model, setModel] = useState("");
  const [unit, setUnit] = useState(provider.kind === "text" || provider.kind === "embedding" ? "input_token" : "credit");
  const [price, setPrice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const token = isTokenUnit(unit);

  async function add() {
    const value = Number(price);
    if (!unit.trim()) return setError("단위를 입력하세요.");
    if (!(value >= 0) || price.trim() === "") return setError("단가를 숫자로 입력하세요.");
    setError(null);
    try {
      await usageApi.addPrice({
        provider_id: provider.id,
        model: model.trim() || null,
        unit: unit.trim(),
        price_per_unit: token ? value / 1_000_000 : value,
      });
      setPrice("");
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove(id: number) {
    try {
      await usageApi.deletePrice(id);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-2">
      {rules.length === 0 ? (
        <p className="text-xs text-amber-700 dark:text-amber-400">단가가 없습니다. 아래에서 추가하면 과거 기록까지 비용이 계산됩니다.</p>
      ) : (
        <table className="w-full text-xs">
          <tbody>
            {rules.map((r) => (
              <tr key={r.id} className="border-t border-zinc-100 dark:border-zinc-800">
                <td className="py-1 pr-2 font-mono [overflow-wrap:anywhere]">{r.model ?? "(모든 모델)"}</td>
                <td className="py-1 pr-2">{UNIT_LABEL[r.unit] ?? r.unit}</td>
                <td className="py-1 pr-2 text-right tabular-nums">{priceLabel(r)}</td>
                <td className="py-1 text-right">
                  <button onClick={() => remove(r.id)} className="text-red-600 hover:underline dark:text-red-400">
                    삭제
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="모델 (비우면 전체)" className="h-7 w-36 rounded border border-zinc-300 bg-white px-2 dark:border-zinc-700 dark:bg-zinc-900" />
        <input list={`units-${provider.id}`} value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="단위" className="h-7 w-32 rounded border border-zinc-300 bg-white px-2 dark:border-zinc-700 dark:bg-zinc-900" />
        <datalist id={`units-${provider.id}`}>
          {[...TOKEN_UNITS, "token", "char", "credit", "second", "image", "request"].map((u) => (
            <option key={u} value={u}>
              {UNIT_LABEL[u] ?? u}
            </option>
          ))}
        </datalist>
        <span>$</span>
        <input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" placeholder={token ? "100만 개당" : "1단위당"} className="h-7 w-24 rounded border border-zinc-300 bg-white px-2 dark:border-zinc-700 dark:bg-zinc-900" />
        <Button className="h-7 text-xs" onClick={add}>
          단가 추가
        </Button>
      </div>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}

function ProviderCard({
  p,
  info,
  rules,
  total,
  onChanged,
}: {
  p: UsageProvider | null;
  info: ProviderInfo;
  rules: PriceRule[];
  total: number;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function patch(change: Partial<Pick<ProviderInfo, "display_name" | "kind" | "color">>) {
    try {
      await usageApi.patchProvider(info.id, change);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900" style={{ borderTopColor: info.color ?? undefined, borderTopWidth: 3 }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{info.display_name ?? info.name}</span>
        <Badge>{KINDS.find(([k]) => k === info.kind)?.[1] ?? info.kind}</Badge>
        {p?.missing_price && <Badge tone="amber">단가 없음</Badge>}
        <span className="ml-auto text-lg font-semibold tabular-nums">{p ? money(p.cost) : "$0"}</span>
        {p && total > 0 && <span className="text-xs text-zinc-500">{Math.round((p.cost / total) * 100)}%</span>}
      </div>
      <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{p ? formatQuantity(p.units) : "이 기간 기록 없음"}</div>
      {p && p.models.length > 0 && (
        <div className="mt-2 space-y-0.5 text-xs">
          {p.models.slice(0, 5).map((m) => (
            <div key={m.model} className="flex justify-between gap-2">
              <span className="truncate font-mono">{m.model}</span>
              <span className="shrink-0 tabular-nums">{m.missing_price ? "단가 없음" : money(m.cost)}</span>
            </div>
          ))}
        </div>
      )}
      {p && p.projects.length > 0 && (
        <div className="mt-2 text-[11px] text-zinc-500">
          프로젝트: {p.projects.slice(0, 4).map((x) => x.name).join(", ")}
          {p.projects.length > 4 && ` 외 ${p.projects.length - 4}`}
        </div>
      )}
      <button onClick={() => setOpen(!open)} className="mt-2 text-xs text-blue-600 hover:underline dark:text-blue-400">
        {open ? "닫기" : "단가와 설정"}
      </button>
      {open && (
        <div className="mt-2 space-y-3 border-t border-zinc-100 pt-2 dark:border-zinc-800">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <label className="flex items-center gap-1">
              이름
              <input defaultValue={info.display_name ?? ""} onBlur={(e) => e.target.value !== (info.display_name ?? "") && patch({ display_name: e.target.value })} className="h-7 w-28 rounded border border-zinc-300 bg-white px-2 dark:border-zinc-700 dark:bg-zinc-900" />
            </label>
            <label className="flex items-center gap-1">
              종류
              <select value={info.kind} onChange={(e) => patch({ kind: e.target.value })} className="h-7 rounded border border-zinc-300 bg-white px-1 dark:border-zinc-700 dark:bg-zinc-900">
                {KINDS.map(([k, label]) => (
                  <option key={k} value={k}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1">
              색
              <input type="color" value={info.color ?? "#888780"} onChange={(e) => patch({ color: e.target.value })} className="h-7 w-8" />
            </label>
          </div>
          <PriceEditor provider={info} rules={rules} onChanged={onChanged} />
          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
      )}
    </section>
  );
}

export default function UsagePage() {
  const [days, setDays] = useState(30);
  const [kind, setKind] = useState("all");
  const summary = useAsync(() => usageApi.summary(days, kind), [days, kind]);
  const meta = useAsync(() => Promise.all([usageApi.providers(), usageApi.prices()]), []);
  const o = useUsageOverview(days, kind);

  function reloadAll() {
    summary.reload();
    meta.reload();
    o.overview.reload();
  }

  const byId = useMemo(() => new Map((summary.data?.providers ?? []).map((p) => [p.id, p])), [summary.data]);

  if ((summary.loading && !summary.data) || (meta.loading && !meta.data)) return <Loading />;
  if (summary.error) return <ErrorBox message={summary.error} />;
  if (meta.error) return <ErrorBox message={meta.error} />;
  const s = summary.data!;
  const [providers, prices] = meta.data!;
  const ordered = [...providers].sort((a, b) => (byId.get(b.id)?.cost ?? -1) - (byId.get(a.id)?.cost ?? -1));

  const seg = (value: string | number, current: string | number, set: () => void, label: string) => (
    <button
      key={String(value)}
      onClick={set}
      className={`rounded-full border px-3 py-1 text-xs ${value === current ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900" : "border-zinc-300 text-zinc-600 dark:border-zinc-700 dark:text-zinc-400"}`}
    >
      {label}
    </button>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-2 text-lg font-semibold">사용량</h1>
        {[7, 15, 30].map((d) => seg(d, days, () => setDays(d), `${d}일`))}
        <span className="mx-1 text-zinc-300">|</span>
        {[["all", "전체"], ["text", "텍스트"], ["media", "미디어"]].map(([k, label]) => seg(k, kind, () => setKind(k), label))}
      </div>

      <Card title={`하루 비용 · 최근 ${days}일 합계 ${money(s.total_cost)}`} action={<span className="text-xs text-zinc-500">그 전 {days}일 {money(s.prev_total_cost)}</span>}>
        {o.overview.error && <ErrorBox message={o.overview.error} />}
        <ServiceChips o={o} />
        <UsageOverviewChart o={o} height={300} />
        <p className="mt-3 text-[11px] text-zinc-500">{OVERVIEW_NOTE}</p>
      </Card>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-2 xl:grid-cols-3">
        {ordered.map((info) => (
          <ProviderCard
            key={info.id}
            info={info}
            p={byId.get(info.id) ?? null}
            rules={prices.filter((r) => r.provider_id === info.id)}
            total={s.total_cost}
            onChanged={reloadAll}
          />
        ))}
      </div>

      <Card title="다른 프로젝트에서 사용량 보내기">
        <p className="text-xs text-zinc-600 dark:text-zinc-400">
          <code className="font-mono">clients/python/jb_usage.py</code> 파일을 프로젝트에 복사하고, AI API를 호출한 뒤 한 줄을 추가합니다. 처음 보는
          provider는 자동으로 등록됩니다.
        </p>
        <pre className="mt-2 overflow-auto rounded bg-zinc-100 p-3 font-mono text-xs dark:bg-zinc-950">{`from jb_usage import record_usage, record_openai, record_gemini

record_usage("runway", unit="credit", quantity=50, model="gen4_turbo", kind="video")
record_usage("elevenlabs", unit="char", quantity=len(text), kind="audio")
record_openai(response)          # OpenAI 응답의 토큰 수
record_gemini(response)          # Gemini 응답의 토큰 수`}</pre>
      </Card>
    </div>
  );
}
