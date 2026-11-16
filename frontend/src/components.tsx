import type { ReactNode } from "react";
import { Link } from "react-router";
import type { SessionSummary } from "./api";
import { relativeTime, tokens, usd } from "./format";

export function Card({ title, action, children }: { title?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      {(title || action) && (
        <div className="mb-2 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-lg bg-zinc-100 px-3 py-2.5 dark:bg-zinc-900">
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-xs text-zinc-500">{hint}</div>}
    </div>
  );
}

export function Loading() {
  return <p className="py-8 text-center text-sm text-zinc-500">불러오는 중…</p>;
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
      데이터를 불러오지 못했습니다: {message}
      <div className="mt-1 text-xs opacity-80">백엔드 서버와 PostgreSQL이 켜져 있는지 확인하세요.</div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-zinc-500">{children}</p>;
}

export function Badge({ children, tone = "zinc" }: { children: ReactNode; tone?: "zinc" | "amber" | "blue" }) {
  const tones = {
    zinc: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
    amber: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
    blue: "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300",
  };
  return <span className={`rounded px-1.5 py-0.5 text-[11px] whitespace-nowrap ${tones[tone]}`}>{children}</span>;
}

export function SessionRow({ s, showProject = false }: { s: SessionSummary; showProject?: boolean }) {
  return (
    <Link
      to={`/sessions/${s.id}`}
      className="flex items-center justify-between gap-3 border-t border-zinc-100 py-2.5 first:border-t-0 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
    >
      <div className="min-w-0">
        <div className="truncate text-sm">{s.title || "(제목 없음)"}</div>
        <div className="truncate text-xs text-zinc-500">
          {showProject && <span className="mr-1.5">{s.project_name ?? "프로젝트 미연결"} ·</span>}
          질문 {s.user_messages} · 응답 {s.assistant_messages} · 출력 {tokens(s.output_tokens)} 토큰
          {s.cost_usd != null && <> · {usd(s.cost_usd)}</>}
        </div>
      </div>
      <span className="shrink-0 text-xs text-zinc-500">{relativeTime(s.ended_at)}</span>
    </Link>
  );
}
