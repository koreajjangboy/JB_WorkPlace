import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { taskApi, type Run, type RunEvent } from "../api";
import { Badge, Button, Card, ErrorBox, Loading, StatusBadge } from "../components";
import { dateTime, duration, tokens, usd } from "../format";
import { useAsync } from "../useAsync";

function clock(iso: string) {
  return new Date(iso).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function Elapsed({ since }: { since: string }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const sec = Math.max(0, Math.round((Date.now() - new Date(since).getTime()) / 1000));
  return <span className="tabular-nums">{`${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`}</span>;
}

function EventView({ e }: { e: RunEvent }) {
  const p = e.payload;
  switch (e.kind) {
    case "init":
      return <div className="text-[11px] text-zinc-500">{clock(e.ts)} · 세션 시작 · {p.model}</div>;
    case "text":
      return (
        <div className="max-w-[90%] rounded-xl rounded-bl-sm border border-zinc-200 bg-white px-3.5 py-2 text-sm whitespace-pre-wrap [overflow-wrap:anywhere] dark:border-zinc-800 dark:bg-zinc-900">
          {p.text}
        </div>
      );
    case "tool_use":
      return (
        <details className="rounded-md border border-zinc-200 bg-zinc-50 text-xs dark:border-zinc-800 dark:bg-zinc-900/60">
          <summary className="flex cursor-pointer items-center gap-1.5 px-2.5 py-1.5 text-zinc-600 dark:text-zinc-400">
            <Badge tone="blue">{p.name}</Badge>
            <span className="min-w-0 truncate font-mono">{p.summary}</span>
          </summary>
          <pre className="max-h-72 overflow-auto border-t border-zinc-200 px-2.5 py-2 font-mono whitespace-pre-wrap [overflow-wrap:anywhere] dark:border-zinc-800">
            {p.input}
          </pre>
        </details>
      );
    case "tool_result": {
      const first = String(p.text ?? "").split("\n")[0];
      return (
        <details className="ml-4 rounded-md border border-zinc-200 text-xs dark:border-zinc-800">
          <summary className="flex cursor-pointer items-center gap-1.5 px-2.5 py-1.5 text-zinc-600 dark:text-zinc-400">
            <Badge tone={p.is_error ? "red" : "zinc"}>{p.is_error ? "거부·오류" : "결과"}</Badge>
            <span className="min-w-0 truncate">{first || "(출력 없음)"}</span>
          </summary>
          <pre className="max-h-72 overflow-auto border-t border-zinc-200 px-2.5 py-2 font-mono whitespace-pre-wrap [overflow-wrap:anywhere] dark:border-zinc-800">
            {p.text}
          </pre>
        </details>
      );
    }
    case "result":
      return (
        <div
          className={`rounded-lg border px-3.5 py-2.5 text-sm ${
            p.is_error
              ? "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/40"
              : "border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950/40"
          }`}
        >
          <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400">
            <span className="font-medium">{p.is_error ? "실패로 끝남" : "완료"}</span>
            {p.num_turns != null && <span>· {p.num_turns}턴</span>}
            {p.duration_ms != null && <span>· {Math.round(p.duration_ms / 1000)}초</span>}
            {p.cost_usd != null && <span>· {usd(p.cost_usd)}</span>}
          </div>
          {p.text && <div className="whitespace-pre-wrap [overflow-wrap:anywhere]">{p.text}</div>}
          {Array.isArray(p.denials) && p.denials.length > 0 && (
            <div className="mt-2 text-xs text-amber-800 dark:text-amber-300">
              거부된 동작 {p.denials.length}개:{" "}
              {p.denials.map((d: { tool: string; summary: string }, i: number) => (
                <code key={i} className="mr-1.5 rounded bg-amber-100 px-1 dark:bg-amber-950">
                  {d.tool}
                  {d.summary ? `: ${d.summary}` : ""}
                </code>
              ))}
            </div>
          )}
        </div>
      );
    case "error":
      return (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          {p.text}
        </div>
      );
    case "stderr":
      return <div className="font-mono text-[11px] break-all text-zinc-500">{p.text}</div>;
    default:
      return null;
  }
}

function RunView({ run, index, onChange }: { run: Run; index: number; onChange: () => void }) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [live, setLive] = useState<Run>(run);
  const [error, setError] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const isRunning = live.status === "running";

  useEffect(() => setLive(run), [run]);

  useEffect(() => {
    setEvents([]);
    if (run.status !== "running") {
      taskApi.events(run.id).then(setEvents).catch((e: Error) => setError(e.message));
      return;
    }
    const source = new EventSource(taskApi.streamUrl(run.id));
    source.addEventListener("event", (msg) => {
      const ev = JSON.parse((msg as MessageEvent).data) as RunEvent;
      setEvents((prev) => (prev.some((p) => p.seq === ev.seq) ? prev : [...prev, ev]));
    });
    source.addEventListener("run", (msg) => setLive(JSON.parse((msg as MessageEvent).data) as Run));
    source.addEventListener("end", () => {
      source.close();
      onChange();
    });
    source.onerror = () => {
      // 연결이 끊기면 브라우저가 다시 연결한다. 끝난 실행이면 end 이벤트가 먼저 온다.
    };
    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run.id, run.status]);

  // 실행 중에는 새 기록이 오면 아래로 따라간다 (사용자가 위를 보고 있으면 그대로 둔다).
  useEffect(() => {
    if (!isRunning || !bottom.current) return;
    const nearBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 300;
    if (nearBottom) bottom.current.scrollIntoView({ block: "end" });
  }, [events.length, isRunning]);

  async function stop() {
    setStopping(true);
    try {
      await taskApi.stop(run.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStopping(false);
    }
  }

  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
        <span className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">실행 #{index + 1}</span>
        <StatusBadge status={live.status} />
        <span>{dateTime(live.started_at)}</span>
        <span>· {isRunning ? <Elapsed since={live.started_at} /> : duration(live.started_at, live.ended_at)}</span>
        {live.cost_usd != null && <span>· {usd(live.cost_usd)}</span>}
        {live.output_tokens > 0 && <span>· 출력 {tokens(live.output_tokens)} 토큰</span>}
        {live.resumed_from && <Badge>이전 세션 이어서</Badge>}
        {isRunning && (
          <Button variant="danger" className="ml-auto" onClick={stop} disabled={stopping}>
            {stopping ? "중단하는 중…" : "중단"}
          </Button>
        )}
      </div>
      <div className="space-y-2">
        <div className="flex justify-end">
          <div className="max-w-[85%] rounded-xl rounded-br-sm bg-blue-600 px-3.5 py-2 text-sm whitespace-pre-wrap text-white [overflow-wrap:anywhere]">
            {live.prompt}
          </div>
        </div>
        {events.map((e) => (
          <EventView key={e.seq} e={e} />
        ))}
        {isRunning && (
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500" /> Claude가 작업 중…
          </div>
        )}
        {error && <ErrorBox message={error} />}
        <div ref={bottom} />
      </div>
    </Card>
  );
}

export default function TaskDetailPage() {
  const id = Number(useParams().taskId);
  const navigate = useNavigate();
  const { data: task, error, loading, reload } = useAsync(() => taskApi.get(id), [id]);
  const [followUp, setFollowUp] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (loading && !task) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!task) return null;

  const running = task.status === "running";
  const neverRun = task.runs.length === 0;

  async function run(prompt?: string) {
    setBusy(true);
    setActionError(null);
    try {
      await taskApi.run(task!.id, prompt);
      setFollowUp("");
      reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm("이 작업과 실행 기록을 지울까요? 프로젝트 파일은 그대로 남습니다.")) return;
    try {
      await taskApi.remove(task!.id);
      navigate("/tasks");
    } catch (e) {
      setActionError((e as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <Link to="/tasks" className="text-xs text-zinc-500 hover:underline">
          ← 작업
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <StatusBadge status={task.status} />
          <h1 className="text-lg font-semibold">{task.title}</h1>
          {!running && (
            <Button variant="danger" className="ml-auto" onClick={remove}>
              삭제
            </Button>
          )}
        </div>
        <div className="text-xs text-zinc-500 [overflow-wrap:anywhere]">
          <Link to={`/projects/${task.project_id}`} className="hover:underline">
            {task.project_name}
          </Link>{" "}
          · {task.project_path} · 실행 {task.run_count}회
          {task.total_cost_usd != null && <> · 합계 {usd(task.total_cost_usd)}</>}
        </div>
        {task.project_dirty_files > 0 && !running && (
          <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
            이 프로젝트에는 저장 안 된 변경 {task.project_dirty_files}개가 있습니다. Claude가 바꾼 내용과 섞일 수 있어요.
          </p>
        )}
      </div>

      {neverRun && (
        <Card title="아직 실행하지 않은 작업">
          <div className="rounded-lg bg-zinc-100 px-3 py-2 text-sm whitespace-pre-wrap dark:bg-zinc-800">{task.prompt}</div>
          <div className="mt-3 flex justify-end">
            <Button variant="primary" onClick={() => run()} disabled={busy}>
              {busy ? "시작하는 중…" : "실행"}
            </Button>
          </div>
        </Card>
      )}

      {task.runs.map((r, i) => (
        <RunView key={r.id} run={r} index={i} onChange={reload} />
      ))}

      {!neverRun && (
        <Card title="추가 지시">
          <textarea
            value={followUp}
            onChange={(e) => {
              setFollowUp(e.target.value);
              setActionError(null);
            }}
            rows={3}
            disabled={running}
            placeholder={running ? "실행이 끝나면 이어서 지시할 수 있습니다" : "테스트도 추가해 줘"}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900"
          />
          <div className="mt-2 flex items-center justify-end gap-2">
            <span className="mr-auto text-xs text-zinc-500">같은 Claude 세션을 이어서 실행합니다.</span>
            <Button
              variant="primary"
              disabled={running || busy}
              onClick={() => (followUp.trim() ? run(followUp) : setActionError("지시 내용을 입력하세요."))}
            >
              {busy ? "시작하는 중…" : "다시 지시"}
            </Button>
          </div>
        </Card>
      )}
      {actionError && <ErrorBox action message={actionError} />}
    </div>
  );
}
