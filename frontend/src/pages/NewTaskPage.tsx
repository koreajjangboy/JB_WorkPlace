import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { api, taskApi } from "../api";
import { Button, Card, ErrorBox, Loading } from "../components";
import { useAsync } from "../useAsync";

export default function NewTaskPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { data, error, loading } = useAsync(() => Promise.all([api.projects(), taskApi.runner()]), []);
  const [projectId, setProjectId] = useState<number | null>(params.get("project") ? Number(params.get("project")) : null);
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [submitting, setSubmitting] = useState<"save" | "run" | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const projects = useMemo(() => data?.[0] ?? [], [data]);
  const project = projects.find((p) => p.id === projectId) ?? null;

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} />;
  const runner = data![1];
  const busy = runner.running >= runner.max_concurrent;
  const canRun = runner.claude_found && !busy;

  async function submit(runNow: boolean) {
    if (!projectId) return setFormError("프로젝트를 고르세요.");
    if (!prompt.trim()) return setFormError("지시 내용을 입력하세요.");
    setSubmitting(runNow ? "run" : "save");
    setFormError(null);
    try {
      const task = await taskApi.create({ project_id: projectId, prompt, title: title || undefined, run_now: runNow });
      navigate(`/tasks/${task.id}`);
    } catch (e) {
      setFormError((e as Error).message);
      setSubmitting(null);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-lg font-semibold">새 작업</h1>
      <Card>
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium">프로젝트</span>
            <select
              value={projectId ?? ""}
              onChange={(e) => {
                setProjectId(e.target.value ? Number(e.target.value) : null);
                setFormError(null);
              }}
              className="h-9 w-full rounded-md border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            >
              <option value="">프로젝트 선택</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} {p.branch ? `(${p.branch})` : ""}
                </option>
              ))}
            </select>
            {project && (
              <span className="mt-1 block text-xs text-zinc-500 [overflow-wrap:anywhere]">
                {project.path}
                {project.dirty_files > 0 && (
                  <span className="ml-2 text-amber-700 dark:text-amber-400">
                    저장 안 된 변경 {project.dirty_files}개가 있습니다. Claude가 바꾼 내용과 섞일 수 있어요.
                  </span>
                )}
              </span>
            )}
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium">지시</span>
            <textarea
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value);
                setFormError(null);
              }}
              rows={8}
              placeholder="README에 설치 방법 섹션을 추가해 줘"
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium">
              제목 <span className="font-normal text-zinc-500">(비워 두면 지시의 첫 줄)</span>
            </span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="h-9 w-full rounded-md border border-zinc-300 bg-white px-3 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>

          {formError && <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>}

          <div className="flex flex-wrap items-center justify-end gap-2">
            {!runner.claude_found && <span className="mr-auto text-xs text-red-600">claude 실행 파일을 찾지 못해 등록만 할 수 있습니다.</span>}
            {runner.claude_found && busy && (
              <span className="mr-auto text-xs text-amber-700 dark:text-amber-400">
                다른 작업이 실행 중이라 지금은 등록만 할 수 있습니다.
              </span>
            )}
            <Button onClick={() => submit(false)} disabled={submitting !== null}>
              {submitting === "save" ? "등록 중…" : "등록"}
            </Button>
            <Button variant="primary" onClick={() => submit(true)} disabled={submitting !== null || !canRun}>
              {submitting === "run" ? "시작하는 중…" : "바로 실행"}
            </Button>
          </div>
        </div>
      </Card>

      <Card title="실행 규칙">
        <ul className="space-y-1 text-xs text-zinc-600 dark:text-zinc-400">
          <li>· 프로젝트 폴더 안에서만 파일을 읽고 고칩니다. 커밋, push, 삭제, 인터넷 접속은 막혀 있습니다.</li>
          <li>· 허용된 명령: 테스트, 빌드, 린트, git diff/status/log 같은 읽기 전용 명령</li>
          <li>
            · 한 번 실행에 최대 {runner.max_minutes}분, ${runner.max_budget_usd}까지 · 동시에 {runner.max_concurrent}개
          </li>
          <li>· 허용 목록에 없는 동작은 묻지 않고 거부되며, 실행 기록에 표시됩니다.</li>
        </ul>
      </Card>
    </div>
  );
}
