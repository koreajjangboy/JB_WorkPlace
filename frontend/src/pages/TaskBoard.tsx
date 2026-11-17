import { useState, type MouseEvent } from "react";
import { Link } from "react-router";
import { taskApi, type Task } from "../api";
import { StatusBadge } from "../components";
import { relativeTime, usd } from "../format";

const COLUMNS: { key: string; title: string; statuses: Task["status"][]; tone: string }[] = [
  { key: "todo", title: "할 일", statuses: ["todo"], tone: "text-zinc-600 dark:text-zinc-300" },
  { key: "running", title: "실행 중", statuses: ["running"], tone: "text-blue-700 dark:text-blue-400" },
  { key: "review", title: "리뷰 · 실패", statuses: ["review", "failed"], tone: "text-amber-700 dark:text-amber-400" },
  { key: "done", title: "완료", statuses: ["done"], tone: "text-green-700 dark:text-green-400" },
];

// 프로젝트 칩 색상. Tailwind가 클래스를 찾을 수 있도록 전체 문자열로 적는다.
const PROJECT_TONES = [
  "bg-sky-100 text-sky-800 ring-sky-300 dark:bg-sky-900/50 dark:text-sky-200 dark:ring-sky-700",
  "bg-violet-100 text-violet-800 ring-violet-300 dark:bg-violet-900/50 dark:text-violet-200 dark:ring-violet-700",
  "bg-emerald-100 text-emerald-800 ring-emerald-300 dark:bg-emerald-900/50 dark:text-emerald-200 dark:ring-emerald-700",
  "bg-orange-100 text-orange-800 ring-orange-300 dark:bg-orange-900/50 dark:text-orange-200 dark:ring-orange-700",
  "bg-pink-100 text-pink-800 ring-pink-300 dark:bg-pink-900/50 dark:text-pink-200 dark:ring-pink-700",
  "bg-teal-100 text-teal-800 ring-teal-300 dark:bg-teal-900/50 dark:text-teal-200 dark:ring-teal-700",
  "bg-indigo-100 text-indigo-800 ring-indigo-300 dark:bg-indigo-900/50 dark:text-indigo-200 dark:ring-indigo-700",
  "bg-lime-100 text-lime-800 ring-lime-300 dark:bg-lime-900/50 dark:text-lime-200 dark:ring-lime-700",
  "bg-rose-100 text-rose-800 ring-rose-300 dark:bg-rose-900/50 dark:text-rose-200 dark:ring-rose-700",
  "bg-cyan-100 text-cyan-800 ring-cyan-300 dark:bg-cyan-900/50 dark:text-cyan-200 dark:ring-cyan-700",
  "bg-fuchsia-100 text-fuchsia-800 ring-fuchsia-300 dark:bg-fuchsia-900/50 dark:text-fuchsia-200 dark:ring-fuchsia-700",
  "bg-yellow-100 text-yellow-800 ring-yellow-300 dark:bg-yellow-900/50 dark:text-yellow-200 dark:ring-yellow-700",
];
const NO_PROJECT_TONE = "bg-zinc-100 text-zinc-600 ring-zinc-300 dark:bg-zinc-800 dark:text-zinc-300 dark:ring-zinc-700";

/** 프로젝트 ID로 색을 고른다. 같은 프로젝트는 항상 같은 색이 된다. */
function projectTone(id: number | null): string {
  if (id == null) return NO_PROJECT_TONE;
  return PROJECT_TONES[Math.abs(id) % PROJECT_TONES.length];
}

function RunButton({ t, onStarted }: { t: Task; onStarted?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start(e: MouseEvent) {
    // 카드 전체가 링크라서 상세 페이지로 넘어가지 않도록 막는다.
    e.preventDefault();
    e.stopPropagation();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await taskApi.run(t.id);
      onStarted?.();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="ml-auto flex shrink-0 items-center gap-1.5">
      {error && (
        <span className="max-w-[8rem] truncate text-red-600 dark:text-red-400" title={error}>
          {error}
        </span>
      )}
      <button
        type="button"
        onClick={start}
        disabled={busy}
        className="inline-flex h-5 items-center rounded bg-blue-600 px-1.5 text-[11px] text-white hover:bg-blue-700 disabled:opacity-60"
      >
        {busy ? "시작하는 중…" : "▶ 실행"}
      </button>
    </span>
  );
}

function Card({ t, onChanged, showProject = true }: { t: Task; onChanged?: () => void; showProject?: boolean }) {
  const accent =
    t.status === "running"
      ? "border-l-blue-500"
      : t.status === "failed"
        ? "border-l-red-500"
        : t.status === "review"
          ? "border-l-amber-500"
          : t.status === "done"
            ? "border-l-green-500"
            : "border-l-zinc-300 dark:border-l-zinc-700";
  return (
    <Link
      to={`/tasks/${t.id}`}
      className={`block rounded-md border border-l-4 border-zinc-200 bg-white px-3 py-2 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800/60 ${accent}`}
    >
      {/* 1줄: 프로젝트 칩 + 제목 */}
      <div className="flex min-w-0 items-center gap-1.5" title={t.title}>
        {showProject && (
          <span
            className={`max-w-[45%] shrink-0 truncate rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset ${projectTone(t.project_id)}`}
          >
            {t.project_name ?? "프로젝트 미연결"}
          </span>
        )}
        <span className="min-w-0 truncate text-sm">{t.title}</span>
      </div>
      {/* 2줄: 상태 · 시간 · 비용 (실패 사유 또는 실행 버튼) */}
      <div className="mt-1 flex min-w-0 items-center gap-1.5 whitespace-nowrap text-[11px] text-zinc-500">
        {t.status === "failed" && <StatusBadge status="failed" />}
        <span>{relativeTime(t.updated_at)}</span>
        {t.total_cost_usd != null && <span>· {usd(t.total_cost_usd)}</span>}
        {t.status === "failed" && t.last_run?.error && (
          <span className="min-w-0 truncate text-red-600 dark:text-red-400" title={t.last_run.error}>
            · {t.last_run.error}
          </span>
        )}
        {t.status === "todo" && <RunButton t={t} onStarted={onChanged} />}
      </div>
    </Link>
  );
}

const OPEN_KEY = "tasks.board.open";

function loadOpen(): Set<string> {
  try {
    const raw = localStorage.getItem(OPEN_KEY);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

type Group = { key: string; projectId: number | null; name: string; items: Task[] };

/** 칼럼 안의 작업을 프로젝트별로 묶는다. 최근에 갱신된 작업이 있는 프로젝트가 위로 온다. */
function groupByProject(items: Task[]): Group[] {
  const map = new Map<string, Group>();
  for (const t of items) {
    const key = t.project_id == null ? "none" : String(t.project_id);
    let g = map.get(key);
    if (!g) {
      g = { key, projectId: t.project_id, name: t.project_name ?? "프로젝트 미연결", items: [] };
      map.set(key, g);
    }
    g.items.push(t);
  }
  const latest = (g: Group) => Math.max(...g.items.map((t) => new Date(t.updated_at).getTime() || 0));
  return [...map.values()].sort((a, b) => latest(b) - latest(a));
}

function ProjectGroup({
  g,
  open,
  onToggle,
  onChanged,
}: {
  g: Group;
  open: boolean;
  onToggle: () => void;
  onChanged?: () => void;
}) {
  const failed = g.items.filter((t) => t.status === "failed").length;
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full min-w-0 items-center gap-1.5 rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-left hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800/60"
      >
        <span className={`shrink-0 text-[10px] text-zinc-400 transition-transform ${open ? "rotate-90" : ""}`}>▶</span>
        <span
          className={`min-w-0 truncate rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${projectTone(g.projectId)}`}
          title={g.name}
        >
          {g.name}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-1.5 text-[11px] text-zinc-500">
          {failed > 0 && <span className="text-red-600 dark:text-red-400">실패 {failed}</span>}
          <span>{g.items.length}</span>
        </span>
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5 border-l-2 border-zinc-200 pl-2 dark:border-zinc-800">
          {g.items.map((t) => (
            <Card key={t.id} t={t} onChanged={onChanged} showProject={false} />
          ))}
        </div>
      )}
    </div>
  );
}

/** 작업 칸반 보드: 할 일 → 실행 중 → 리뷰·실패 → 완료. 칼럼 안에서는 프로젝트별로 접어 둔다. */
export default function TaskBoard({ tasks, onChanged }: { tasks: Task[]; onChanged?: () => void }) {
  const [open, setOpen] = useState<Set<string>>(loadOpen);

  function toggle(key: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      try {
        localStorage.setItem(OPEN_KEY, JSON.stringify([...next]));
      } catch {
        /* 저장 못 해도 화면은 바뀐다 */
      }
      return next;
    });
  }

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {COLUMNS.map((col) => {
        const items = tasks.filter((t) => col.statuses.includes(t.status));
        const groups = groupByProject(items);
        return (
          <section key={col.key} className="rounded-xl bg-zinc-100 p-2 dark:bg-zinc-900/60">
            <div className={`mb-2 flex items-center justify-between px-1 text-sm font-semibold ${col.tone}`}>
              <span>{col.title}</span>
              <span className="text-xs font-normal text-zinc-500">{items.length}</span>
            </div>
            <div className="space-y-1.5">
              {groups.length === 0 ? (
                <p className="px-1 py-4 text-center text-xs text-zinc-400">없음</p>
              ) : (
                groups.map((g) => {
                  const key = `${col.key}:${g.key}`;
                  return (
                    <ProjectGroup
                      key={g.key}
                      g={g}
                      open={open.has(key)}
                      onToggle={() => toggle(key)}
                      onChanged={onChanged}
                    />
                  );
                })
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
