import { useState } from "react";
import { Link } from "react-router";
import { api, taskApi } from "../api";
import CalendarSection from "../CalendarSection";
import { Card, Empty, ErrorBox, Loading, SessionRow, Stat } from "../components";
import { relativeTime } from "../format";
import { RateLimitView } from "../limits";
import { money, usageApi } from "../usage";
import UsageSection, { type UsageDays } from "../UsageSection";
import { useAsync } from "../useAsync";
import { TaskRow } from "./TasksPage";

export default function HomePage() {
  const [days, setDays] = useState<UsageDays>(7);
  const { data, error, loading } = useAsync(
    () =>
      Promise.all([
        api.projects(),
        api.sessions({ limit: 10 }),
        taskApi.list({ status: "running,review,failed" }),
        taskApi.rateLimit(),
      ]),
    [],
  );
  const usage = useAsync(() => usageApi.summary(days, "all"), [days]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const [projects, sessions, activeTasks, rateLimit] = data;
  const runningCount = activeTasks.filter((t) => t.status === "running").length;
  const reviewCount = activeTasks.filter((t) => t.status === "review").length;
  const activeProjects = projects.filter((p) => p.session_count > 0).slice(0, 6);
  const dirtyTotal = projects.reduce((sum, p) => sum + p.dirty_files, 0);
  const unpushed = projects.reduce((sum, p) => sum + p.ahead, 0);

  const u = usage.data;
  const delta = u && u.prev_total_cost > 0 ? Math.round(((u.total_cost - u.prev_total_cost) / u.prev_total_cost) * 100) : null;
  const missingPrice = u?.providers.filter((p) => p.missing_price).length ?? 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label={`최근 ${days}일 AI 비용 (환산)`}
          value={u ? money(u.total_cost) : "…"}
          hint={
            delta == null ? (
              "지난 기간 기록 없음"
            ) : (
              <span className={delta > 0 ? "text-red-600 dark:text-red-400" : "text-green-700 dark:text-green-400"}>
                지난 {days}일 대비 {delta > 0 ? "+" : ""}
                {delta}%
              </span>
            )
          }
        />
        <Stat
          label="사용 중인 provider"
          value={u ? u.provider_count : "…"}
          hint={missingPrice > 0 ? <span className="text-amber-700 dark:text-amber-400">단가 없음 {missingPrice}</span> : "모두 단가 있음"}
        />
        <Stat
          label="실행 중 / 리뷰 대기"
          value={`${runningCount} / ${reviewCount}`}
          hint={
            <Link to="/tasks" className="hover:underline">
              작업 보드 보기
            </Link>
          }
        />
        <Stat label="저장 안 된 변경" value={dirtyTotal} hint={`push 안 된 커밋 ${unpushed}개`} />
      </div>

      <CalendarSection />

      <UsageSection days={days} onDaysChange={setDays} />

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card
          title="주목할 작업"
          action={
            <Link to="/tasks/new" className="text-xs text-blue-600 hover:underline dark:text-blue-400">
              + 새 작업
            </Link>
          }
        >
          {activeTasks.length === 0 ? (
            <Empty>실행 중이거나 리뷰를 기다리는 작업이 없습니다.</Empty>
          ) : (
            activeTasks.slice(0, 6).map((t) => <TaskRow key={t.id} t={t} />)
          )}
        </Card>
        <Card title="Claude 사용 한도">
          <RateLimitView data={rateLimit} />
        </Card>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card title="최근 세션" action={<span className="text-xs text-zinc-500">모든 프로젝트</span>}>
          {sessions.length === 0 ? (
            <Empty>아직 불러온 Claude Code 세션이 없습니다. 오른쪽 위 [다시 스캔]을 눌러 보세요.</Empty>
          ) : (
            sessions.slice(0, 8).map((s) => <SessionRow key={s.id} s={s} showProject />)
          )}
        </Card>

        <Card
          title="최근 작업한 프로젝트"
          action={
            <Link to="/projects" className="text-xs text-blue-600 hover:underline dark:text-blue-400">
              전체 보기
            </Link>
          }
        >
          {activeProjects.length === 0 ? (
            <Empty>세션이 연결된 프로젝트가 없습니다.</Empty>
          ) : (
            activeProjects.map((p) => (
              <Link
                key={p.id}
                to={`/projects/${p.id}`}
                className="flex items-center justify-between gap-3 border-t border-zinc-100 py-2.5 first:border-t-0 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm">{p.name}</div>
                  <div className="text-xs text-zinc-500">
                    세션 {p.session_count} · 변경 {p.dirty_files}
                    {p.ahead > 0 && <> · push 안 됨 {p.ahead}</>} · {p.branch ?? "—"}
                  </div>
                </div>
                <span className="shrink-0 text-xs text-zinc-500">{relativeTime(p.last_activity_at)}</span>
              </Link>
            ))
          )}
        </Card>
      </div>
    </div>
  );
}
