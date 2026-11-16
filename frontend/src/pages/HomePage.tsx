import { Link } from "react-router";
import { api } from "../api";
import { Card, Empty, ErrorBox, Loading, SessionRow, Stat } from "../components";
import { relativeTime, tokens } from "../format";
import { useAsync } from "../useAsync";

const WEEK = 7 * 24 * 3600 * 1000;

export default function HomePage() {
  const { data, error, loading } = useAsync(
    () => Promise.all([api.projects(), api.sessions({ limit: 500 })]),
    [],
  );
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const [projects, sessions] = data;
  const weekAgo = Date.now() - WEEK;
  const recent = sessions.filter((s) => s.ended_at && new Date(s.ended_at).getTime() > weekAgo);
  const weekOutput = recent.reduce((sum, s) => sum + s.output_tokens, 0);
  const activeProjects = projects.filter((p) => p.session_count > 0).slice(0, 6);
  const dirtyTotal = projects.reduce((sum, p) => sum + p.dirty_files, 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="프로젝트" value={projects.length} hint={`Claude 세션 있는 곳 ${projects.filter((p) => p.session_count).length}개`} />
        <Stat label="최근 7일 세션" value={recent.length} hint={`전체 ${sessions.length}개`} />
        <Stat label="최근 7일 출력 토큰" value={tokens(weekOutput)} hint="Claude Code 기준" />
        <Stat label="저장 안 된 변경" value={dirtyTotal} hint="모든 프로젝트 합계 (파일 수)" />
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card title="최근 세션" action={<span className="text-xs text-zinc-500">모든 프로젝트</span>}>
          {sessions.length === 0 ? (
            <Empty>아직 불러온 Claude Code 세션이 없습니다. 오른쪽 위 [다시 스캔]을 눌러 보세요.</Empty>
          ) : (
            sessions.slice(0, 10).map((s) => <SessionRow key={s.id} s={s} showProject />)
          )}
        </Card>

        <Card title="최근 작업한 프로젝트" action={<Link to="/projects" className="text-xs text-blue-600 hover:underline dark:text-blue-400">전체 보기</Link>}>
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
                    세션 {p.session_count} · 변경 {p.dirty_files} · {p.branch ?? "—"}
                  </div>
                </div>
                <span className="shrink-0 text-xs text-zinc-500">{relativeTime(p.last_activity_at)}</span>
              </Link>
            ))
          )}
        </Card>
      </div>
      <p className="text-xs text-zinc-500">
        작업 지시(M2), 리뷰(M3), provider별 사용량 대시보드(M4)는 다음 단계에서 추가됩니다.
      </p>
    </div>
  );
}
