import { useEffect, useState } from "react";
import { projectChangesApi, request, type Project, type PushResult } from "./api";
import { Badge, Button } from "./components";

/** push 결과 한 줄: 성공이면 초록, 실패면 이유와 함께 빨강. */
export function PushOutcome({ result, sha }: { result: PushResult | null; sha?: string }) {
  if (!result && !sha) return null;
  const ok = result?.pushed;
  const failed = result && !result.pushed && result.push_error;
  return (
    <div
      className={`rounded-md border px-3 py-2 text-sm whitespace-pre-wrap [overflow-wrap:anywhere] ${
        failed
          ? "border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300"
          : "border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300"
      }`}
    >
      {sha && (
        <>
          커밋함 <code className="font-mono">{sha.slice(0, 7)}</code>
          {ok ? " · push 완료" : failed ? " · push 실패: " : " · push는 하지 않았습니다"}
        </>
      )}
      {!sha && ok && "push 완료"}
      {failed && <span>{result!.push_error}</span>}
    </div>
  );
}

type RemoteInfo = { remote: string | null; web_url: string | null; branch_url: string | null; host: string | null };

/** 원격 저장소(GitHub 등)를 새 탭에서 여는 링크. 웹 주소로 바꿀 수 없는 원격이면 아무것도 안 보인다. */
export function RemoteLink({ projectId }: { projectId: number }) {
  const [info, setInfo] = useState<RemoteInfo | null>(null);
  useEffect(() => {
    let alive = true;
    request<RemoteInfo>(`/api/projects/${projectId}/remote`)
      .then((r) => alive && setInfo(r))
      .catch(() => alive && setInfo(null));
    return () => {
      alive = false;
    };
  }, [projectId]);
  if (!info?.web_url) return null;
  const label = info.host === "github.com" ? "GitHub" : info.host === "gitlab.com" ? "GitLab" : info.host;
  return (
    <a
      href={info.web_url}
      target="_blank"
      rel="noreferrer"
      title={info.web_url}
      className="inline-flex items-center gap-1 rounded-md border border-zinc-300 px-2 py-0.5 text-blue-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-blue-400 dark:hover:bg-zinc-800"
    >
      {label}에서 보기 ↗
    </a>
  );
}

/** 프로젝트의 원격 연결 상태와 [push] 버튼. */
export function PushBar({ project, onPushed }: { project: Project; onPushed: () => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PushResult | null>(null);
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  async function fetchRemote() {
    setFetching(true);
    setFetchError(null);
    try {
      await projectChangesApi.fetch(project.id);
      onPushed();
    } catch (e) {
      setFetchError((e as Error).message);
    } finally {
      setFetching(false);
    }
  }

  if (!project.has_remote) {
    return <span className="text-xs text-zinc-500">원격 저장소 없음 (push할 곳이 없습니다)</span>;
  }
  const needsPush = project.ahead > 0 || !project.upstream;

  async function push() {
    setBusy(true);
    setResult(null);
    try {
      setResult(await projectChangesApi.push(project.id));
      onPushed();
    } catch (e) {
      setResult({ pushed: false, push_output: null, push_error: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400">
        <RemoteLink projectId={project.id} />
        <span>{project.upstream ? `원격: ${project.upstream}` : "원격 브랜치에 아직 연결되지 않음"}</span>
        {project.ahead > 0 && <Badge tone="blue">push 안 된 커밋 {project.ahead}</Badge>}
        {project.behind > 0 && <Badge tone="amber">원격에 새 커밋 {project.behind} (pull 필요)</Badge>}
        {project.upstream && project.ahead === 0 && project.behind === 0 && <Badge tone="green">원격과 같음</Badge>}
        {needsPush && (
          <Button variant="primary" className="h-7 text-xs" onClick={push} disabled={busy}>
            {busy ? "push 중…" : project.upstream ? `push (${project.ahead}개 커밋)` : "push (원격 브랜치 만들기)"}
          </Button>
        )}
        {project.upstream && (
          <button
            onClick={fetchRemote}
            disabled={fetching}
            className="text-blue-600 hover:underline disabled:opacity-60 dark:text-blue-400"
            title="원격의 최신 상태를 가져옵니다 (내 파일은 바꾸지 않음)"
          >
            {fetching ? "확인 중…" : "원격 확인"}
          </button>
        )}
      </div>
      {fetchError && <PushOutcome result={{ pushed: false, push_output: null, push_error: fetchError }} />}
      {result && <PushOutcome result={result} />}
    </div>
  );
}
