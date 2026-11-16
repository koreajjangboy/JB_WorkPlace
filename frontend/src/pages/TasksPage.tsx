import { useEffect, useState } from "react";
import { Link } from "react-router";
import { taskApi, type Task } from "../api";
import { Card, Empty, ErrorBox, Loading, StatusBadge } from "../components";
import { relativeTime, usd } from "../format";
import { useAsync } from "../useAsync";
import TaskBoard from "./TaskBoard";

const FILTERS: [string, string][] = [
  ["", "전체"],
  ["running", "실행 중"],
  ["review", "리뷰"],
  ["failed", "실패"],
  ["todo", "할 일"],
  ["done", "완료"],
];

export function TaskRow({ t, showProject = true }: { t: Task; showProject?: boolean }) {
  return (
    <Link
      to={`/tasks/${t.id}`}
      className="flex items-center justify-between gap-3 border-t border-zinc-100 py-2.5 first:border-t-0 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <StatusBadge status={t.status} />
          <span className="truncate text-sm">{t.title}</span>
        </div>
        <div className="mt-0.5 truncate text-xs text-zinc-500">
          {showProject && <>{t.project_name} · </>}실행 {t.run_count}회
          {t.total_cost_usd != null && <> · {usd(t.total_cost_usd)}</>}
          {t.last_run?.error && t.status === "failed" && <> · {t.last_run.error}</>}
        </div>
      </div>
      <span className="shrink-0 text-xs text-zinc-500">{relativeTime(t.updated_at)}</span>
    </Link>
  );
}

function loadView(): "board" | "list" {
  try {
    return localStorage.getItem("tasks.view") === "list" ? "list" : "board";
  } catch {
    return "board";
  }
}

export default function TasksPage() {
  const [filter, setFilter] = useState("");
  const [view, setView] = useState<"board" | "list">(loadView);
  const effectiveFilter = view === "board" ? "" : filter;
  const tasks = useAsync(() => taskApi.list({ status: effectiveFilter || undefined }), [effectiveFilter]);

  function changeView(next: "board" | "list") {
    setView(next);
    try {
      localStorage.setItem("tasks.view", next);
    } catch {
      /* 저장 못 해도 화면은 바뀐다 */
    }
  }
  const counts = useAsync(() => taskApi.counts(), []);
  const anyRunning = (counts.data?.running ?? 0) > 0;

  // 실행 중인 작업이 있으면 목록을 주기적으로 새로 고친다.
  useEffect(() => {
    if (!anyRunning) return;
    const timer = setInterval(() => {
      tasks.reload();
      counts.reload();
    }, 4000);
    return () => clearInterval(timer);
  }, [anyRunning, tasks.reload, counts.reload]);

  const total = Object.values(counts.data ?? {}).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-2 text-lg font-semibold">작업</h1>
        <div className="mr-2 inline-flex overflow-hidden rounded-md border border-zinc-300 text-xs dark:border-zinc-700">
          {(["board", "list"] as const).map((v) => (
            <button
              key={v}
              onClick={() => changeView(v)}
              className={`px-3 py-1 ${view === v ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900" : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"}`}
            >
              {v === "board" ? "보드" : "목록"}
            </button>
          ))}
        </div>
        {view === "list" && FILTERS.map(([value, label]) => {
          const n = value ? counts.data?.[value] ?? 0 : total;
          return (
            <button
              key={value}
              onClick={() => setFilter(value)}
              className={`rounded-full border px-3 py-1 text-xs ${
                filter === value
                  ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                  : "border-zinc-300 text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-900"
              }`}
            >
              {label} {n}
            </button>
          );
        })}
        <Link
          to="/tasks/new"
          className="ml-auto inline-flex h-8 items-center rounded-md bg-blue-600 px-3 text-sm text-white hover:bg-blue-700"
        >
          새 작업
        </Link>
      </div>

      {tasks.error ? (
        <ErrorBox message={tasks.error} />
      ) : tasks.loading && !tasks.data ? (
        <Loading />
      ) : view === "board" ? (
        <TaskBoard tasks={tasks.data ?? []} />
      ) : (
        <Card>
          {tasks.data && tasks.data.length > 0 ? (
            tasks.data.map((t) => <TaskRow key={t.id} t={t} />)
          ) : (
            <Empty>{filter ? "이 상태의 작업이 없습니다." : "아직 작업이 없습니다. [새 작업]으로 Claude Code에 일을 맡겨 보세요."}</Empty>
          )}
        </Card>
      )}
    </div>
  );
}
