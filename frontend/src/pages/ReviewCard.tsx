import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { api, reviewApi, type PushResult, type TaskDetail } from "../api";
import { FileRow } from "../changes";
import { Button, Card, Empty, ErrorBox } from "../components";
import { dateTime } from "../format";
import { PushBar, PushOutcome } from "../push";
import { useAsync } from "../useAsync";

export default function ReviewCard({ task, onChanged }: { task: TaskDetail; onChanged: () => void }) {
  const { data, error, loading, reload } = useAsync(() => reviewApi.changes(task.id), [task.id, task.updated_at]);
  const project = useAsync(() => api.project(task.project_id), [task.project_id, task.updated_at]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<"commit" | "complete" | "revert" | null>(null);
  const [confirmRevert, setConfirmRevert] = useState(false);
  const [revertDone, setRevertDone] = useState<number | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [pushAfter, setPushAfter] = useState(true);
  const [lastCommit, setLastCommit] = useState<(PushResult & { sha: string }) | null>(null);
  const hasRemote = !!project.data?.has_remote;

  // 기본 선택: 이 작업에서 새로 바뀐 파일만. 작업 전부터 바뀌어 있던 파일은 직접 고르게 한다.
  useEffect(() => {
    if (!data) return;
    setSelected(new Set(data.files.filter((f) => data.tracked && !f.pre_existing).map((f) => f.path)));
    setMessage(data.commit_message ?? "");
  }, [data]);

  const files = useMemo(() => data?.files ?? [], [data]);
  const preExistingSelected = files.some((f) => f.pre_existing && selected.has(f.path));
  const selectedFiles = files.filter((f) => selected.has(f.path));
  const blocked = selectedFiles.filter((f) => !f.revertable);

  function toggle(path: string) {
    setFormError(null);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  async function doCommit() {
    if (selected.size === 0) return setFormError("커밋할 파일을 하나 이상 고르세요.");
    if (!message.trim()) return setFormError("커밋 메시지를 입력하세요.");
    setBusy("commit");
    setFormError(null);
    try {
      const res = await reviewApi.commit(task.id, message, [...selected], pushAfter && hasRemote);
      setLastCommit(res);
      reload();
      project.reload();
      onChanged();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function doRevert() {
    setBusy("revert");
    setFormError(null);
    try {
      const res = await reviewApi.revert(task.id, [...selected]);
      setConfirmRevert(false);
      setRevertDone(res.reverted.length);
      reload();
      project.reload();
      onChanged();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function doComplete() {
    setBusy("complete");
    setFormError(null);
    try {
      await reviewApi.complete(task.id);
      onChanged();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card
      title="검토와 커밋"
      action={
        <button onClick={reload} className="text-xs text-zinc-500 hover:underline">
          새로 고침
        </button>
      }
    >
      {error && <ErrorBox action message={error} />}
      {loading && !data && <p className="text-sm text-zinc-500">변경 사항을 읽는 중…</p>}
      {data && (
        <div className="space-y-3">
          {lastCommit ? (
            <PushOutcome result={lastCommit} sha={lastCommit.sha} />
          ) : (
            data.commit_sha && (
              <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300">
                커밋함 <code className="font-mono">{data.commit_sha.slice(0, 7)}</code> · {dateTime(data.committed_at)}
              </div>
            )
          )}
          {data.commit_sha && project.data && project.data.has_remote && (project.data.ahead > 0 || !project.data.upstream) && (
            <PushBar project={project.data} onPushed={project.reload} />
          )}
          {!data.tracked && files.length > 0 && (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              이 작업은 변경 추적 기능이 생기기 전에 실행되어, 어떤 파일을 Claude가 바꿨는지 알 수 없습니다. 지금 저장 안 된 변경을 모두
              보여주니 커밋할 파일을 직접 고르세요.
            </p>
          )}

          {files.length === 0 ? (
            <div>
              <Empty>{data.commit_sha ? "커밋한 뒤로 새로 바뀐 파일이 없습니다." : "이 작업이 바꾼 파일이 없습니다."}</Empty>
              {task.project_dirty_files > 0 && (
                <p className="-mt-3 text-center text-xs text-zinc-600 dark:text-zinc-400">
                  작업 전부터 있던 저장 안 된 변경 {task.project_dirty_files}개는{" "}
                  <Link to={`/projects/${task.project_id}/changes`} className="text-blue-600 hover:underline dark:text-blue-400">
                    프로젝트 변경 사항
                  </Link>
                  에서 확인하고 커밋할 수 있습니다.
                </p>
              )}
            </div>
          ) : (
            <div>
              <div className="mb-1 flex items-center justify-between text-xs text-zinc-500">
                <span>
                  바뀐 파일 {files.length}개 · {selected.size}개 선택 · 파일 이름을 누르면 diff
                </span>
                <span className="space-x-2">
                  <button className="hover:underline" onClick={() => setSelected(new Set(files.map((f) => f.path)))}>
                    모두 선택
                  </button>
                  <button className="hover:underline" onClick={() => setSelected(new Set())}>
                    선택 해제
                  </button>
                </span>
              </div>
              {files.map((f) => (
                <FileRow
                  key={f.path}
                  file={f}
                  checked={selected.has(f.path)}
                  onToggle={() => toggle(f.path)}
                  loadDiff={async (p) => (await reviewApi.diff(task.id, p)).diff}
                />
              ))}
              {preExistingSelected && (
                <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                  "작업 전부터 변경" 파일을 고르면, 작업 전에 직접 바꿔 둔 내용도 함께 커밋됩니다. diff를 확인하세요.
                </p>
              )}
            </div>
          )}

          {files.length > 0 && (
            <label className="block">
              <span className="mb-1 block text-sm font-medium">
                커밋 메시지 <span className="font-normal text-zinc-500">{data.commit_message ? "(Claude가 제안한 메시지, 고칠 수 있음)" : ""}</span>
              </span>
              <textarea
                value={message}
                onChange={(e) => {
                  setMessage(e.target.value);
                  setFormError(null);
                }}
                rows={Math.min(10, Math.max(3, message.split("\n").length + 1))}
                placeholder="feat: 무엇을 왜 바꿨는지"
                className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 font-mono text-xs dark:border-zinc-700 dark:bg-zinc-900"
              />
            </label>
          )}

          {formError && <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>}

          {revertDone != null && (
            <div className="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm dark:border-zinc-800 dark:bg-zinc-900">
              파일 {revertDone}개를 작업 전 상태로 되돌렸습니다.
            </div>
          )}

          {confirmRevert && (
            <div className="rounded-lg border border-red-300 bg-red-50 p-3 dark:border-red-900 dark:bg-red-950/30">
              <div className="text-sm font-medium text-red-800 dark:text-red-300">이 파일들을 작업 전 상태로 되돌릴까요? 되돌린 내용은 복구할 수 없습니다.</div>
              <ul className="mt-2 space-y-1 text-xs">
                {selectedFiles.map((f) => (
                  <li key={f.path} className="[overflow-wrap:anywhere]">
                    <code className="font-mono">{f.path}</code>{" "}
                    <span className={f.revertable ? "text-zinc-600 dark:text-zinc-400" : "text-red-700 dark:text-red-400"}>
                      — {f.revert_note}
                    </span>
                  </li>
                ))}
              </ul>
              {blocked.length > 0 && (
                <p className="mt-2 text-xs text-red-700 dark:text-red-400">되돌릴 수 없는 파일 {blocked.length}개를 선택에서 빼야 합니다.</p>
              )}
              <div className="mt-2 flex justify-end gap-2">
                <Button onClick={() => setConfirmRevert(false)}>취소</Button>
                <Button variant="danger" onClick={doRevert} disabled={busy !== null || blocked.length > 0}>
                  {busy === "revert" ? "되돌리는 중…" : `되돌리기 (${selected.size}개 파일)`}
                </Button>
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className="mr-auto text-xs text-zinc-500">커밋은 이 PC의 git 설정(이름, 이메일)으로 합니다.</span>
            {files.length > 0 && data.tracked && !confirmRevert && (
              <Button
                variant="danger"
                onClick={() => (selected.size === 0 ? setFormError("되돌릴 파일을 고르세요.") : (setConfirmRevert(true), setRevertDone(null)))}
                disabled={busy !== null}
              >
                되돌리기…
              </Button>
            )}
            {files.length > 0 && hasRemote && (
              <label className="flex items-center gap-1.5 text-sm text-zinc-700 dark:text-zinc-300">
                <input type="checkbox" checked={pushAfter} onChange={(e) => setPushAfter(e.target.checked)} />
                커밋 후 바로 push
              </label>
            )}
            {task.status !== "done" && (
              <Button onClick={doComplete} disabled={busy !== null}>
                {busy === "complete" ? "처리 중…" : "커밋 없이 완료"}
              </Button>
            )}
            {files.length > 0 && (
              <Button variant="primary" onClick={doCommit} disabled={busy !== null}>
                {busy === "commit"
                  ? pushAfter && hasRemote
                    ? "커밋하고 push하는 중…"
                    : "커밋하는 중…"
                  : `승인하고 ${pushAfter && hasRemote ? "커밋·push" : "커밋"} (${selected.size}개 파일)`}
              </Button>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
