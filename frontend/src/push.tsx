import { useState } from "react";
import { projectChangesApi, type Project, type PushResult } from "./api";
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

/** 프로젝트의 원격 연결 상태와 [push] 버튼. */
export function PushBar({ project, onPushed }: { project: Project; onPushed: () => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PushResult | null>(null);

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
        <span>{project.upstream ? `원격: ${project.upstream}` : "원격 브랜치에 아직 연결되지 않음"}</span>
        {project.ahead > 0 && <Badge tone="blue">push 안 된 커밋 {project.ahead}</Badge>}
        {project.behind > 0 && <Badge tone="amber">원격에 새 커밋 {project.behind} (pull 필요)</Badge>}
        {project.upstream && project.ahead === 0 && project.behind === 0 && <Badge tone="green">원격과 같음</Badge>}
        {needsPush && (
          <Button variant="primary" className="h-7 text-xs" onClick={push} disabled={busy}>
            {busy ? "push 중…" : project.upstream ? `push (${project.ahead}개 커밋)` : "push (원격 브랜치 만들기)"}
          </Button>
        )}
      </div>
      {result && <PushOutcome result={result} />}
    </div>
  );
}
