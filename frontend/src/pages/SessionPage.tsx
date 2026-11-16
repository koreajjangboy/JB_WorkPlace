import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api, type TranscriptEntry } from "../api";
import { Badge, Card, ErrorBox, Loading, Stat } from "../components";
import { dateTime, duration, tokens, usd } from "../format";
import { useAsync } from "../useAsync";

const PAGE = 200;

function Entry({ e, showTools }: { e: TranscriptEntry; showTools: boolean }) {
  const time = e.ts ? new Date(e.ts).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" }) : "";

  if (e.kind === "user" || e.kind === "command") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-xl rounded-br-sm bg-blue-600 px-3.5 py-2 text-sm whitespace-pre-wrap text-white [overflow-wrap:anywhere]">
          {e.kind === "command" && <div className="mb-1 text-[11px] opacity-80">명령</div>}
          {e.text}
          <div className="mt-1 text-right text-[11px] opacity-70">{time}</div>
        </div>
      </div>
    );
  }
  if (e.kind === "assistant") {
    return (
      <div className="max-w-[90%] rounded-xl rounded-bl-sm border border-zinc-200 bg-white px-3.5 py-2 text-sm whitespace-pre-wrap [overflow-wrap:anywhere] dark:border-zinc-800 dark:bg-zinc-900">
        {e.text}
        <div className="mt-1 text-[11px] text-zinc-500">{time}</div>
      </div>
    );
  }
  if (!showTools) return null;
  const isUse = e.kind === "tool_use";
  return (
    <details className="ml-2 rounded-md border border-zinc-200 bg-zinc-50 text-xs dark:border-zinc-800 dark:bg-zinc-900/60">
      <summary className="flex cursor-pointer items-center gap-1.5 px-2.5 py-1.5 text-zinc-600 dark:text-zinc-400">
        {isUse ? (
          <>
            <Badge tone="blue">{e.tool_name}</Badge>
            <span>도구 호출</span>
          </>
        ) : (
          <>
            <Badge tone={e.is_error ? "amber" : "zinc"}>{e.is_error ? "오류" : "결과"}</Badge>
            <span className="min-w-0 truncate">{e.text.split("\n")[0].slice(0, 90)}</span>
          </>
        )}
      </summary>
      <pre className="max-h-72 overflow-auto border-t border-zinc-200 px-2.5 py-2 font-mono whitespace-pre-wrap [overflow-wrap:anywhere] dark:border-zinc-800">
        {e.text}
      </pre>
    </details>
  );
}

export default function SessionPage() {
  const id = useParams().sessionId!;
  const meta = useAsync(() => api.session(id), [id]);
  const [entries, setEntries] = useState<TranscriptEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [showTools, setShowTools] = useState(true);

  useEffect(() => {
    setEntries([]);
    setError(null);
    api
      .transcript(id, 0, PAGE)
      .then((t) => (setEntries(t.entries), setTotal(t.total)))
      .catch((e: Error) => setError(e.message));
  }, [id]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const t = await api.transcript(id, entries.length, PAGE);
      setEntries((prev) => [...prev, ...t.entries]);
      setTotal(t.total);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingMore(false);
    }
  }

  if (meta.loading && !meta.data) return <Loading />;
  if (meta.error) return <ErrorBox message={meta.error} />;
  const s = meta.data!;

  return (
    <div className="space-y-4">
      <div>
        {s.project_id ? (
          <Link to={`/projects/${s.project_id}`} className="text-xs text-zinc-500 hover:underline">
            ← {s.project_name}
          </Link>
        ) : (
          <Link to="/projects" className="text-xs text-zinc-500 hover:underline">
            ← 프로젝트
          </Link>
        )}
        <h1 className="mt-1 text-lg font-semibold">{s.title || "(제목 없음)"}</h1>
        <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
          <span>{dateTime(s.started_at)} 시작 · {duration(s.started_at, s.ended_at)}</span>
          {s.git_branch && <Badge>{s.git_branch}</Badge>}
          {s.models.map((m) => (
            <Badge key={m} tone="blue">{m}</Badge>
          ))}
          <span className="truncate">{s.cwd}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="질문 / 응답" value={`${s.user_messages} / ${s.assistant_messages}`} />
        <Stat label="입력 토큰" value={tokens(s.input_tokens)} hint={`캐시 읽기 ${tokens(s.cache_read_tokens)} · 쓰기 ${tokens(s.cache_creation_tokens)}`} />
        <Stat label="출력 토큰" value={tokens(s.output_tokens)} />
        <Stat label="기록된 비용" value={usd(s.cost_usd)} hint={s.cost_usd == null ? "기록에 비용 정보 없음" : "세션 기록 기준"} />
      </div>

      <Card
        title={`대화 (${total}개 항목)`}
        action={
          <label className="flex items-center gap-1.5 text-xs text-zinc-600 dark:text-zinc-400">
            <input type="checkbox" checked={showTools} onChange={(e) => setShowTools(e.target.checked)} />
            도구 호출 보기
          </label>
        }
      >
        {error && <ErrorBox message={error} />}
        <div className="space-y-2.5">
          {entries.map((e, i) => (
            <Entry key={i} e={e} showTools={showTools} />
          ))}
        </div>
        {entries.length < total && (
          <div className="mt-4 text-center">
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-100 disabled:opacity-60 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              {loadingMore ? "불러오는 중…" : `더 보기 (${total - entries.length}개 남음)`}
            </button>
          </div>
        )}
      </Card>
    </div>
  );
}
