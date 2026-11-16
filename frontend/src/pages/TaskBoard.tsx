import { Link } from "react-router";
import type { Task } from "../api";
import { StatusBadge } from "../components";
import { relativeTime, usd } from "../format";

const COLUMNS: { key: string; title: string; statuses: Task["status"][]; tone: string }[] = [
  { key: "todo", title: "할 일", statuses: ["todo"], tone: "text-zinc-600 dark:text-zinc-300" },
  { key: "running", title: "실행 중", statuses: ["running"], tone: "text-blue-700 dark:text-blue-400" },
  { key: "review", title: "리뷰 · 실패", statuses: ["review", "failed"], tone: "text-amber-700 dark:text-amber-400" },
  { key: "done", title: "완료", statuses: ["done"], tone: "text-green-700 dark:text-green-400" },
];

function Card({ t }: { t: Task }) {
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
      <div className="line-clamp-2 text-sm [overflow-wrap:anywhere]">{t.title}</div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-zinc-500">
        {t.status === "failed" && <StatusBadge status="failed" />}
        <span className="truncate">{t.project_name}</span>
        <span>· {relativeTime(t.updated_at)}</span>
        {t.total_cost_usd != null && <span>· {usd(t.total_cost_usd)}</span>}
      </div>
      {t.status === "failed" && t.last_run?.error && (
        <div className="mt-1 line-clamp-2 text-[11px] text-red-600 dark:text-red-400">{t.last_run.error}</div>
      )}
    </Link>
  );
}

/** 작업 칸반 보드: 할 일 → 실행 중 → 리뷰·실패 → 완료 */
export default function TaskBoard({ tasks }: { tasks: Task[] }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {COLUMNS.map((col) => {
        const items = tasks.filter((t) => col.statuses.includes(t.status));
        return (
          <section key={col.key} className="rounded-xl bg-zinc-100 p-2 dark:bg-zinc-900/60">
            <div className={`mb-2 flex items-center justify-between px-1 text-sm font-semibold ${col.tone}`}>
              <span>{col.title}</span>
              <span className="text-xs font-normal text-zinc-500">{items.length}</span>
            </div>
            <div className="space-y-2">
              {items.length === 0 ? (
                <p className="px-1 py-4 text-center text-xs text-zinc-400">없음</p>
              ) : (
                items.map((t) => <Card key={t.id} t={t} />)
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
