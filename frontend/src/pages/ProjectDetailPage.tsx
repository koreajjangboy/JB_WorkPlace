import { Link, useParams } from "react-router";
import { api, taskApi } from "../api";
import { Badge, Card, Empty, ErrorBox, Loading, SessionRow, Stat } from "../components";
import { dateTime, relativeTime, tokens, usd } from "../format";
import { PushBar } from "../push";
import { useAsync } from "../useAsync";
import { TaskRow } from "./TasksPage";

export default function ProjectDetailPage() {
  const id = Number(useParams().projectId);
  const { data, error, loading, reload } = useAsync(
    () => Promise.all([api.project(id), api.sessions({ projectId: id, limit: 500 }), taskApi.list({ projectId: id })]),
    [id],
  );
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  if (!data) return null;

  const [project, sessions, tasks] = data;
  const cost = sessions.reduce((sum, s) => sum + (s.cost_usd ?? 0), 0);
  const hasCost = sessions.some((s) => s.cost_usd != null);

  return (
    <div className="space-y-4">
      <div>
        <Link to="/projects" className="text-xs text-zinc-500 hover:underline">
          ← 프로젝트
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold">{project.name}</h1>
          <Badge>{project.branch ?? "브랜치 없음"}</Badge>
          {project.dirty_files > 0 && (
            <Link to={`/projects/${project.id}/changes`} className="hover:opacity-80" title="변경 내용 보고 커밋하기">
              <Badge tone="amber">저장 안 된 변경 {project.dirty_files} · 보기</Badge>
            </Link>
          )}
          <Link
            to={`/tasks/new?project=${project.id}`}
            className="ml-auto inline-flex h-8 items-center rounded-md bg-blue-600 px-3 text-sm text-white hover:bg-blue-700"
          >
            이 프로젝트에 작업 지시
          </Link>
        </div>
        <div className="text-xs text-zinc-500 [overflow-wrap:anywhere]">
          {project.path} · 마지막 커밋 {dateTime(project.last_commit_at)}
        </div>
        <div className="mt-2">
          <PushBar project={project} onPushed={reload} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Claude 세션" value={project.session_count} hint={`마지막 ${relativeTime(project.last_session_at)}`} />
        <Stat label="입력 토큰" value={tokens(project.input_tokens)} hint="캐시 제외" />
        <Stat label="출력 토큰" value={tokens(project.output_tokens)} />
        <Stat label="기록된 비용" value={hasCost ? usd(cost) : "—"} hint={hasCost ? "세션 기록 기준" : "비용 정보 없음"} />
      </div>

      {tasks.length > 0 && (
        <Card title={`작업 ${tasks.length}`}>
          {tasks.map((t) => (
            <TaskRow key={t.id} t={t} showProject={false} />
          ))}
        </Card>
      )}

      <Card title={`세션 ${sessions.length}`}>
        {sessions.length === 0 ? (
          <Empty>이 프로젝트에서 연 Claude Code 세션이 없습니다.</Empty>
        ) : (
          sessions.map((s) => <SessionRow key={s.id} s={s} />)
        )}
      </Card>
    </div>
  );
}
