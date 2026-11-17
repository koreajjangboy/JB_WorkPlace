import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { Badge, Button, Card, Empty, ErrorBox, Loading } from "../components";
import { relativeTime } from "../format";
import { useAsync } from "../useAsync";
import { UNIT_LABEL, billingApi, openaiApi, runwayApi, serviceApi, takeoutApi, type BillingStatus, type CatalogItem, type OpenAIStatus, type RunwayStatus, type ServiceStatus, type TakeoutImport } from "../usage";

const KINDS: [string, string][] = [
  ["text", "텍스트"],
  ["embedding", "임베딩"],
  ["image", "이미지"],
  ["video", "영상"],
  ["audio", "음성"],
  ["mixed", "혼합"],
];
const COLLECTION: Record<string, string> = {
  claude_logs: "자동 (Claude Code 세션 기록)",
  app: "앱에서 기록 (jb_usage)",
  manual: "직접 입력",
  takeout: "Google Takeout 파일 (Gemini 앱)",
};
const input = "h-8 rounded-md border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900";

/** 서비스마다 프로젝트 코드에 넣을 한 줄 */
function snippet(s: ServiceStatus): string {
  const unit = s.default_unit || "request";
  switch (s.helper) {
    case "record_gemini":
      return `from jb_usage import record_gemini\n\nresponse = client.models.generate_content(...)\nrecord_gemini(response)  # 토큰 수를 WorkPlace로 보냄`;
    case "record_openai":
      return `from jb_usage import record_openai\n\nresponse = client.chat.completions.create(...)\nrecord_openai(response)`;
    case "record_openai_upstage":
      return `from jb_usage import record_openai\n\n# Upstage는 OpenAI SDK로 호출하므로 provider 이름만 바꾼다\nresponse = client.chat.completions.create(...)\nrecord_openai(response, provider="upstage")`;
    default:
      return `from jb_usage import record_usage\n\n# API 호출 뒤에 사용량을 기록 (단위: ${UNIT_LABEL[unit] ?? unit})\nrecord_usage("${s.name}", unit="${unit}", quantity=사용량, kind="${s.kind}")`;
  }
}

function Status({ s }: { s: ServiceStatus }) {
  if (s.collection === "claude_logs") return <Badge tone="green">자동 수집</Badge>;
  if (s.collection === "takeout") return s.records > 0 ? <Badge tone="green">Takeout 가져옴</Badge> : <Badge tone="amber">아직 가져오지 않음</Badge>;
  if (s.records_7d > 0) return <Badge tone="green">기록 중</Badge>;
  if (s.records > 0) return <Badge tone="amber">최근 7일 기록 없음</Badge>;
  if (s.collection === "manual") return <Badge>직접 입력</Badge>;
  return <Badge tone="amber">아직 기록 없음</Badge>;
}

function ManualForm({ s, onDone }: { s: ServiceStatus; onDone: () => void }) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [cost, setCost] = useState("");
  const [quantity, setQuantity] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const c = cost.trim() ? Number(cost) : null;
    const q = quantity.trim() ? Number(quantity) : 0;
    if ((c == null || Number.isNaN(c)) && !(q > 0)) return setError("비용이나 사용량 중 하나는 숫자로 입력하세요.");
    setError(null);
    try {
      await serviceApi.manual({ provider_id: s.id, date: `${date}T12:00:00`, cost_usd: c, quantity: q, note: note || undefined });
      setMsg("저장했습니다");
      setCost("");
      setQuantity("");
      setNote("");
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={`${input} h-7 text-xs`} />
        <span>$</span>
        <input value={cost} onChange={(e) => setCost(e.target.value)} inputMode="decimal" placeholder="비용" className={`${input} h-7 w-20 text-xs`} />
        <input value={quantity} onChange={(e) => setQuantity(e.target.value)} inputMode="decimal" placeholder={`사용량 (${UNIT_LABEL[s.default_unit ?? ""] ?? s.default_unit ?? "단위"})`} className={`${input} h-7 w-32 text-xs`} />
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="메모 (예: 11월 청구서)" className={`${input} h-7 w-40 text-xs`} />
        <Button className="h-7 text-xs" onClick={save}>
          추가
        </Button>
      </div>
      {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
      {msg && !error && <p className="text-xs text-green-700 dark:text-green-400">{msg}</p>}
    </div>
  );
}

/** Gemini 앱: Google Takeout 파일을 올리거나 지켜보는 폴더에서 가져온다. */
function TakeoutPanel({ onDone }: { onDone: () => void }) {
  const st = useAsync(() => takeoutApi.status(), []);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [guide, setGuide] = useState(false);

  const describe = (r: TakeoutImport) =>
    `${r.file}: ${r.first} ~ ${r.last}, ${r.days}일 · 대화 ${r.prompts.toLocaleString()}회 · 약 ${r.tokens.toLocaleString()} 토큰`;

  async function run(job: () => Promise<string>) {
    setBusy(true);
    setError(null);
    setMsg(null);
    try {
      setMsg(await job());
      st.reload();
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const upload = (file: File) => run(async () => `가져왔습니다 — ${describe(await takeoutApi.upload(file))}`);
  const scan = () =>
    run(async () => {
      const r = await takeoutApi.scan();
      return r.imported.length
        ? `새 파일 ${r.imported.length}개를 가져왔습니다 — ${r.imported.map(describe).join(" / ")}`
        : "새 Takeout 파일이 없습니다";
    });

  const last = st.data?.last_import;
  const dirs = st.data?.dirs.filter((d, i) => d.exists || i === 0) ?? [];
  return (
    <div className="mt-2 space-y-1.5 text-xs">
      <p className="text-zinc-600 dark:text-zinc-400">
        Gemini 앱에는 사용량 API가 없어서, Google Takeout으로 내보낸 활동 기록의 글자 수로 토큰을 <b>추정</b>합니다.
        {last ? (
          <>
            {" "}
            마지막 가져오기 {relativeTime(last.imported_at)} ({last.first} ~ {last.last}).
          </>
        ) : (
          " 아직 가져온 파일이 없습니다."
        )}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <label
          className={`cursor-pointer rounded-md border border-zinc-300 px-2 py-1 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800 ${busy ? "pointer-events-none opacity-50" : ""}`}
        >
          {busy ? "가져오는 중…" : "Takeout 파일 올리기"}
          <input
            type="file"
            accept=".zip,.json"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) upload(f);
            }}
          />
        </label>
        <button onClick={scan} disabled={busy} className="text-blue-600 hover:underline disabled:opacity-50 dark:text-blue-400">
          폴더 지금 확인
        </button>
        <button onClick={() => setGuide(!guide)} className="text-blue-600 hover:underline dark:text-blue-400">
          {guide ? "안내 닫기" : "자동으로 받는 방법"}
        </button>
      </div>
      <p className="text-[11px] text-zinc-500">지켜보는 폴더 (10분마다 takeout-*.zip 확인): {dirs.map((d) => d.path).join(", ")}</p>
      {msg && <p className="text-green-700 dark:text-green-400">{msg}</p>}
      {error && <p className="text-red-600 dark:text-red-400">{error}</p>}
      {guide && (
        <ol className="list-decimal space-y-0.5 rounded bg-zinc-50 p-2 pl-6 text-zinc-600 dark:bg-zinc-950 dark:text-zinc-400">
          <li>
            <a href="https://takeout.google.com" target="_blank" rel="noreferrer" className="text-blue-600 hover:underline dark:text-blue-400">
              takeout.google.com
            </a>
            에서 <b>모두 선택 해제</b> → <b>내 활동</b>만 선택
          </li>
          <li>
            "모든 활동 데이터 포함됨" → <b>Gemini 앱</b>만 선택, "여러 형식" → 활동 기록 형식을 <b>JSON</b>으로 변경
          </li>
          <li>
            전송 방법 <b>Drive에 추가</b>, 빈도 <b>2개월마다 내보내기(1년)</b>, 파일 형식 .zip → 내보내기 만들기
          </li>
          <li>
            PC에 <b>Google Drive 데스크톱</b>을 설치해 두면 <code className="font-mono">G:\내 드라이브\Takeout</code>에 zip이 생기고 WorkPlace가 자동으로 가져옵니다
          </li>
          <li>그보다 자주 보고 싶으면 Takeout에서 한 번만 내보내기를 해서 받은 zip을 다운로드 폴더에 두거나 여기에 올리면 됩니다</li>
          <li>
            Gemini 설정의 <b>Gemini 앱 활동</b>이 켜져 있어야 기록이 남습니다
          </li>
        </ol>
      )}
    </div>
  );
}

/** Google Cloud 결제 내보내기(BigQuery)에서 실제 비용을 가져오는 서비스 (예: Gemini API) */
function BillingPanel({ billing, onDone }: { billing: BillingStatus; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const last = billing.last_sync;

  async function sync() {
    setBusy(true);
    setError(null);
    try {
      const r = await billingApi.sync(!last?.tables.some((t) => t.rows > 0));
      if (r.result.error) setError(r.result.error);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const rows = last?.tables.reduce((n, t) => n + t.rows, 0) ?? 0;
  return (
    <div className="mt-2 space-y-1 rounded-md bg-zinc-50 p-2 text-xs dark:bg-zinc-950">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Google Cloud 결제 내보내기</span>
        {last?.error ? <Badge tone="red">오류</Badge> : rows > 0 ? <Badge tone="green">연결됨</Badge> : <Badge tone="amber">데이터 기다리는 중</Badge>}
        <button onClick={sync} disabled={busy} className="ml-auto text-blue-600 hover:underline disabled:opacity-50 dark:text-blue-400">
          {busy ? "가져오는 중…" : "지금 가져오기"}
        </button>
      </div>
      <p className="text-zinc-600 dark:text-zinc-400">
        크레딧을 뺀 실제 청구 금액을 {billing.sync_hours}시간마다 날짜·프로젝트·모델별로 가져옵니다.
        {last && <> 마지막 확인 {relativeTime(last.at)}.</>}
      </p>
      {last?.tables.map((t) => (
        <p key={t.table} className="font-mono text-[11px] text-zinc-500" title={t.table}>
          {t.table.split(".").slice(0, 2).join(".")} ·{" "}
          {t.rows > 0 ? `${t.first} ~ ${t.last}, ${t.saved}건 ${t.cost_usd.toFixed(2)}${t.skipped_csv_days ? ` (CSV로 넣은 기간 ${t.skipped_csv_days}건 제외)` : ""}` : "아직 비어 있음 — 내보내기를 켠 뒤 몇 시간~하루 걸립니다"}
        </p>
      ))}
      {(error || last?.error) && <p className="text-red-600 dark:text-red-400">{error || last?.error}</p>}
    </div>
  );
}

type ApiSyncStatus = { configured: boolean; sync_hours: number; last_sync: { at: string; error: string | null; first?: string | null; last?: string | null } | null };

/** 서비스의 사용량 API(키 필요)에서 주기적으로 가져오는 연결 상태 (OpenAI, Runway 등) */
function ApiUsagePanel({
  title,
  st,
  summary,
  sync,
  guide,
  onDone,
}: {
  title: string;
  st: ApiSyncStatus;
  summary: () => string;
  sync: () => Promise<{ result: { error: string | null } }>;
  guide: ReactNode;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showGuide, setShowGuide] = useState(!st.configured);
  const last = st.last_sync;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const r = await sync();
      if (r.result.error) setError(r.result.error);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 space-y-1 rounded-md bg-zinc-50 p-2 text-xs dark:bg-zinc-950">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{title}</span>
        {!st.configured ? (
          <Badge tone="amber">키 없음</Badge>
        ) : last?.error ? (
          <Badge tone="red">오류</Badge>
        ) : last ? (
          <Badge tone="green">연결됨</Badge>
        ) : (
          <Badge>확인 전</Badge>
        )}
        {st.configured && (
          <button onClick={run} disabled={busy} className="ml-auto text-blue-600 hover:underline disabled:opacity-50 dark:text-blue-400">
            {busy ? "가져오는 중…" : "지금 가져오기"}
          </button>
        )}
      </div>
      <p className="text-zinc-600 dark:text-zinc-400">
        {st.sync_hours}시간마다 자동으로 가져옵니다. 코드는 고치지 않아도 됩니다.
        {last && !last.error && (
          <>
            {" "}
            마지막 확인 {relativeTime(last.at)} · {last.first ? summary() : "최근 사용 내역 없음"}.
          </>
        )}
      </p>
      {(error || last?.error) && <p className="text-red-600 dark:text-red-400">{error || last?.error}</p>}
      <button onClick={() => setShowGuide(!showGuide)} className="text-blue-600 hover:underline dark:text-blue-400">
        {showGuide ? "안내 닫기" : "연결 방법"}
      </button>
      {showGuide && <ol className="list-decimal space-y-0.5 pl-5 text-zinc-600 dark:text-zinc-400">{guide}</ol>}
    </div>
  );
}

const linkCls = "text-blue-600 hover:underline dark:text-blue-400";

function OpenAIPanel({ st, onDone }: { st: OpenAIStatus; onDone: () => void }) {
  const l = st.last_sync;
  return (
    <ApiUsagePanel
      title="OpenAI 조직 사용량 API"
      st={st}
      onDone={onDone}
      sync={() => openaiApi.sync()}
      summary={() => `${l?.first} ~ ${l?.last}, $${(l?.cost_usd ?? 0).toFixed(2)}, ${(l?.tokens ?? 0).toLocaleString()} 토큰`}
      guide={
        <>
          <li>
            <a href="https://platform.openai.com/settings/organization/admin-keys" target="_blank" rel="noreferrer" className={linkCls}>
              platform.openai.com → 조직 설정 → Admin keys
            </a>
            에서 <b>Create new admin key</b> (조직 Owner만 가능, 개인 계정은 Personal 조직), 권한은 <b>Read only</b>
          </li>
          <li>
            <code className="font-mono">backend\.env</code>에 <code className="font-mono">OPENAI_ADMIN_KEY=sk-admin-…</code> 추가 후 백엔드 다시 시작
          </li>
          <li>처음 180일을 가져오고, 이후 최근 40일을 다시 읽어 실제 비용과 모델별 토큰을 반영합니다</li>
        </>
      }
    />
  );
}

function RunwayPanel({ st, onDone }: { st: RunwayStatus; onDone: () => void }) {
  const l = st.last_sync;
  return (
    <ApiUsagePanel
      title="Runway 개발자 API 사용량"
      st={st}
      onDone={onDone}
      sync={() => runwayApi.sync()}
      summary={() =>
        `${l?.first} ~ ${l?.last}, ${(l?.credits ?? 0).toLocaleString()} 크레딧 ($${(l?.cost_usd ?? 0).toFixed(2)})` +
        (l?.credit_balance != null ? ` · 남은 크레딧 ${l.credit_balance.toLocaleString()}` : "")
      }
      guide={
        <>
          <li>
            <a href="https://dev.runwayml.com" target="_blank" rel="noreferrer" className={linkCls}>
              dev.runwayml.com
            </a>{" "}
            개발자 포털 → <b>API Keys</b>에서 키 만들기 (만든 직후에만 보이므로 바로 복사)
          </li>
          <li>
            <code className="font-mono">backend\.env</code>에 <code className="font-mono">RUNWAY_API_KEY=key_…</code> 추가 후 백엔드 다시 시작
          </li>
          <li>API로 쓴 크레딧을 날짜·모델별로 가져옵니다 (1크레딧 ${st.usd_per_credit}). 처음 90일, 이후 최근 40일</li>
          <li>웹 앱(구독)에서 쓴 크레딧은 별도이며, 조회 API가 Enterprise 플랜에서만 열려 있어 가져올 수 없습니다</li>
        </>
      }
    />
  );
}


function ServiceCard({ s, onChanged, billing, openai, runway }: { s: ServiceStatus; onChanged: () => void; billing?: BillingStatus; openai?: OpenAIStatus; runway?: RunwayStatus }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const missing = s.used_in.filter((u) => !s.reporting_projects.includes(u.project));
  // 서비스 API(결제 내보내기·OpenAI 조직 사용량)로 가져오면 코드에 jb_usage를 붙일 필요가 없다.
  const viaApi = !!billing || !!openai?.configured || !!runway?.configured;

  async function patch(change: Parameters<typeof serviceApi.update>[1]) {
    setError(null);
    try {
      await serviceApi.update(s.id, change);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove() {
    if (!confirm(`${s.display_name ?? s.name} 서비스를 목록에서 지울까요?`)) return;
    try {
      await serviceApi.remove(s.id);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(snippet(s));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setOpen(true);
    }
  }

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900" style={{ borderLeft: `4px solid ${s.color ?? "#888780"}` }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">{s.display_name ?? s.name}</span>
        <Status s={s} />
        <Badge>{KINDS.find(([k]) => k === s.kind)?.[1] ?? s.kind}</Badge>
        {!s.has_price && s.collection !== "claude_logs" && !viaApi && (
          <Link to="/usage">
            <Badge tone="amber">단가 없음</Badge>
          </Link>
        )}
        <span className="ml-auto text-xs text-zinc-500">
          {s.last_at ? `마지막 기록 ${relativeTime(s.last_at)} · 7일 ${s.records_7d}건` : "기록 없음"}
        </span>
      </div>

      <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">
        수집: {COLLECTION[s.collection]}
        {s.default_unit && <> · 기본 단위: {UNIT_LABEL[s.default_unit] ?? s.default_unit}</>}
        {s.website && (
          <>
            {" "}
            ·{" "}
            <a href={s.website} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline dark:text-blue-400">
              요금표
            </a>
          </>
        )}
      </div>

      {s.collection === "takeout" && <TakeoutPanel onDone={onChanged} />}
      {billing && <BillingPanel billing={billing} onDone={onChanged} />}
      {openai && <OpenAIPanel st={openai} onDone={onChanged} />}
      {runway && <RunwayPanel st={runway} onDone={onChanged} />}

      {s.collection !== "claude_logs" && s.collection !== "takeout" && !viaApi && (
        <div className="mt-2 text-xs">
          {s.used_in.length === 0 ? (
            <span className="text-zinc-500">코드에서 이 서비스를 쓰는 프로젝트를 찾지 못했습니다.</span>
          ) : (
            <>
              <span className="text-zinc-600 dark:text-zinc-400">코드에서 쓰는 프로젝트 {s.used_in.length}곳 · 기록을 보내는 곳 {s.used_in.length - missing.length}곳</span>
              <div className="mt-1 flex flex-wrap gap-1">
                {s.used_in.map((u) => {
                  const ok = s.reporting_projects.includes(u.project);
                  return (
                    <span
                      key={u.project}
                      title={u.files.join("\n")}
                      className={`rounded px-1.5 py-0.5 text-[11px] ${ok ? "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-300" : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"}`}
                    >
                      {ok ? "✓ " : ""}
                      {u.project}
                    </span>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}

      <div className="mt-2 flex flex-wrap gap-3 text-xs">
        {s.collection === "app" && !viaApi && (
          <button onClick={copy} className="text-blue-600 hover:underline dark:text-blue-400">
            {copied ? "복사했습니다" : "연결 코드 복사"}
          </button>
        )}
        <button onClick={() => setOpen(!open)} className="text-blue-600 hover:underline dark:text-blue-400">
          {open ? "닫기" : "설정 · 직접 입력"}
        </button>
      </div>

      {open && (
        <div className="mt-3 space-y-3 border-t border-zinc-100 pt-3 dark:border-zinc-800">
          {s.collection === "app" && !viaApi && (
            <div>
              <div className="mb-1 text-xs font-medium">연결 방법</div>
              <ol className="mb-1 list-decimal space-y-0.5 pl-4 text-xs text-zinc-600 dark:text-zinc-400">
                <li>
                  <code className="font-mono">C:\dev\JB_WorkPlace\clients\python\jb_usage.py</code>를 프로젝트 폴더에 복사
                </li>
                <li>API를 호출하는 곳 바로 뒤에 아래 코드 추가</li>
                <li>앱을 한 번 실행하면 이 화면의 "마지막 기록"이 바뀝니다</li>
              </ol>
              <pre className="overflow-auto rounded bg-zinc-100 p-2 font-mono text-[11px] dark:bg-zinc-950">{snippet(s)}</pre>
              {missing.length > 0 && (
                <p className="mt-1 text-[11px] text-zinc-500">
                  아직 연결되지 않은 프로젝트: {missing.map((m) => `${m.project} (${m.files[0]})`).join(", ")}
                </p>
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <label className="flex items-center gap-1">
              이름
              <input defaultValue={s.display_name ?? ""} onBlur={(e) => e.target.value !== (s.display_name ?? "") && patch({ display_name: e.target.value })} className={`${input} h-7 w-28 text-xs`} />
            </label>
            <label className="flex items-center gap-1">
              종류
              <select value={s.kind} onChange={(e) => patch({ kind: e.target.value })} className={`${input} h-7 text-xs`}>
                {KINDS.map(([k, label]) => (
                  <option key={k} value={k}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1">
              수집
              <select value={s.collection} onChange={(e) => patch({ collection: e.target.value as ServiceStatus["collection"] })} className={`${input} h-7 text-xs`} disabled={s.collection === "claude_logs"}>
                {Object.entries(COLLECTION)
                  .filter(([k]) => k !== "claude_logs" || s.collection === "claude_logs")
                  .map(([k, label]) => (
                    <option key={k} value={k}>
                      {label}
                    </option>
                  ))}
              </select>
            </label>
            <label className="flex items-center gap-1">
              기본 단위
              <input defaultValue={s.default_unit ?? ""} onBlur={(e) => e.target.value !== (s.default_unit ?? "") && patch({ default_unit: e.target.value })} className={`${input} h-7 w-20 text-xs`} />
            </label>
            <label className="flex items-center gap-1">
              색
              <input type="color" value={s.color ?? "#888780"} onChange={(e) => patch({ color: e.target.value })} className="h-7 w-8" />
            </label>
          </div>
          <label className="block text-xs">
            코드 감지 패턴 <span className="text-zinc-500">(정규식, 프로젝트 코드에서 이 서비스를 찾는 데 씀)</span>
            <input defaultValue={s.detect ?? ""} onBlur={(e) => e.target.value !== (s.detect ?? "") && patch({ detect: e.target.value })} className={`${input} mt-1 h-7 w-full font-mono text-xs`} />
          </label>
          <label className="block text-xs">
            메모
            <input defaultValue={s.notes ?? ""} onBlur={(e) => e.target.value !== (s.notes ?? "") && patch({ notes: e.target.value })} placeholder="예: 회사 카드로 결제, 월 $20 정액" className={`${input} mt-1 h-7 w-full text-xs`} />
          </label>
          {s.collection !== "claude_logs" && (
            <div>
              <div className="mb-1 text-xs font-medium">직접 입력</div>
              <ManualForm s={s} onDone={onChanged} />
            </div>
          )}
          <div className="flex justify-between text-xs">
            <Link to="/usage" className="text-blue-600 hover:underline dark:text-blue-400">
              단가표 편집 (사용량 화면) →
            </Link>
            {s.name !== "claude" && (
              <button onClick={remove} className="text-red-600 hover:underline dark:text-red-400">
                목록에서 지우기
              </button>
            )}
          </div>
          {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
        </div>
      )}
    </section>
  );
}

function AddService({ catalog, onAdded }: { catalog: CatalogItem[]; onAdded: () => void }) {
  const [custom, setCustom] = useState({ name: "", display_name: "", kind: "text", default_unit: "request" });
  const [error, setError] = useState<string | null>(null);

  async function add(data: Parameters<typeof serviceApi.create>[0]) {
    setError(null);
    try {
      await serviceApi.create(data);
      setCustom({ name: "", display_name: "", kind: "text", default_unit: "request" });
      onAdded();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const available = catalog.filter((c) => !c.registered);
  return (
    <Card title="서비스 추가">
      {available.length > 0 && (
        <div className="mb-3">
          <div className="mb-1.5 text-xs text-zinc-500">자주 쓰는 서비스 (누르면 등록)</div>
          <div className="flex flex-wrap gap-1.5">
            {available.map((c) => (
              <button key={c.name} onClick={() => add({ name: c.name })} className="rounded-full border border-zinc-300 px-3 py-1 text-xs hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800">
                + {c.display_name}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="text-xs text-zinc-500">목록에 없는 서비스</div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <input value={custom.name} onChange={(e) => setCustom({ ...custom, name: e.target.value })} placeholder="식별자 (예: suno)" className={`${input} w-32`} />
        <input value={custom.display_name} onChange={(e) => setCustom({ ...custom, display_name: e.target.value })} placeholder="표시 이름" className={`${input} w-32`} />
        <select value={custom.kind} onChange={(e) => setCustom({ ...custom, kind: e.target.value })} className={input}>
          {KINDS.map(([k, label]) => (
            <option key={k} value={k}>
              {label}
            </option>
          ))}
        </select>
        <input value={custom.default_unit} onChange={(e) => setCustom({ ...custom, default_unit: e.target.value })} placeholder="단위 (credit, char…)" className={`${input} w-32`} />
        <Button
          onClick={() =>
            custom.name.trim()
              ? add({ name: custom.name.trim(), display_name: custom.display_name.trim() || undefined, kind: custom.kind, default_unit: custom.default_unit.trim() || undefined })
              : setError("식별자를 입력하세요 (영문, 숫자, - _ .)")
          }
        >
          추가
        </Button>
      </div>
      {error && <p className="mt-1.5 text-xs text-red-600 dark:text-red-400">{error}</p>}
    </Card>
  );
}

export default function SettingsPage() {
  const status = useAsync(() => serviceApi.status(false), []);
  const billing = useAsync(() => billingApi.status(), []);
  const openai = useAsync(() => openaiApi.status(), []);
  const runway = useAsync(() => runwayApi.status(), []);
  const catalog = useAsync(() => serviceApi.catalog(), []);
  const [scanning, setScanning] = useState(false);

  async function rescan() {
    setScanning(true);
    try {
      await serviceApi.status(true);
      status.reload();
    } finally {
      setScanning(false);
    }
  }

  function reloadAll() {
    status.reload();
    billing.reload();
    openai.reload();
    runway.reload();
    catalog.reload();
  }

  if ((status.loading && !status.data) || (catalog.loading && !catalog.data)) return <Loading />;
  if (status.error) return <ErrorBox message={status.error} />;
  const services = status.data!.services;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-2 text-lg font-semibold">설정 · AI 서비스</h1>
        <span className="text-xs text-zinc-500">코드 확인 {relativeTime(status.data!.scanned_at)}</span>
        <Button className="ml-auto" onClick={rescan} disabled={scanning}>
          {scanning ? "프로젝트 코드 확인 중…" : "프로젝트 코드 다시 확인"}
        </Button>
      </div>

      <Card>
        <p className="text-xs text-zinc-600 dark:text-zinc-400">
          등록한 서비스는 사용량 화면과 홈 차트에 나옵니다. Claude는 세션 기록에서 자동으로 모으고, 다른 서비스는 그 서비스를 호출하는 프로젝트에{" "}
          <code className="font-mono">jb_usage.py</code>를 붙여 기록합니다 (API 응답에 토큰 수가 들어 있어 따로 키를 넣을 필요가 없습니다). 연결하기 어려운
          서비스는 청구 금액을 직접 입력할 수 있습니다.
        </p>
      </Card>

      {services.length === 0 ? (
        <Empty>등록한 서비스가 없습니다.</Empty>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-3 lg:grid-cols-2">
          {services.map((s) => (
            <ServiceCard
              key={s.id}
              s={s}
              onChanged={reloadAll}
              openai={s.name === "openai" ? openai.data ?? undefined : undefined}
              runway={s.name === "runway" ? runway.data ?? undefined : undefined}
              billing={billing.data && billing.data.tables.length > 0 && Object.values(billing.data.services).includes(s.name) ? billing.data : undefined}
            />
          ))}
        </div>
      )}

      {catalog.data && <AddService catalog={catalog.data} onAdded={reloadAll} />}
    </div>
  );
}
