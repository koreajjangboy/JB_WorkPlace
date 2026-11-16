import { useEffect, useMemo, useState } from "react";
import { reviewApi, type FileChange, type TaskDetail } from "../api";
import { Badge, Button, Card, Empty, ErrorBox } from "../components";
import { dateTime } from "../format";
import { useAsync } from "../useAsync";

const KIND: Record<FileChange["kind"], [string, "green" | "blue" | "red" | "zinc"]> = {
  added: ["추가", "green"],
  modified: ["수정", "blue"],
  deleted: ["삭제", "red"],
  renamed: ["이름 변경", "zinc"],
};

function DiffView({ text }: { text: string }) {
  return (
    <pre className="max-h-96 overflow-auto bg-zinc-50 py-2 font-mono text-[12px] leading-5 dark:bg-zinc-950">
      {text.split("\n").map((line, i) => {
        let cls = "text-zinc-500";
        if (line.startsWith("+") && !line.startsWith("+++")) cls = "bg-green-50 text-green-800 dark:bg-green-950/50 dark:text-green-300";
        else if (line.startsWith("-") && !line.startsWith("---")) cls = "bg-red-50 text-red-800 dark:bg-red-950/50 dark:text-red-300";
        else if (line.startsWith("@@")) cls = "text-blue-600 dark:text-blue-400";
        else if (!/^(diff |index |--- |\+\+\+ |새 파일)/.test(line)) cls = "text-zinc-700 dark:text-zinc-300";
        return (
          <div key={i} className={`px-3 whitespace-pre-wrap [overflow-wrap:anywhere] ${cls}`}>
            {line || " "}
          </div>
        );
      })}
    </pre>
  );
}

function FileRow({
  taskId,
  file,
  checked,
  onToggle,
}: {
  taskId: number;
  file: FileChange;
  checked: boolean;
  onToggle: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [diff, setDiff] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [label, tone] = KIND[file.kind];

  async function toggleDiff() {
    const next = !open;
    setOpen(next);
    if (next && diff === null) {
      try {
        setDiff((await reviewApi.diff(taskId, file.path)).diff);
      } catch (e) {
        setError((e as Error).message);
      }
    }
  }

  return (
    <div className="border-t border-zinc-100 first:border-t-0 dark:border-zinc-800">
      <div className="flex items-center gap-2 py-2">
        <input type="checkbox" checked={checked} onChange={onToggle} aria-label={`${file.path} 커밋에 포함`} />
        <Badge tone={tone}>{label}</Badge>
        <button onClick={toggleDiff} className="min-w-0 flex-1 truncate text-left font-mono text-xs hover:underline">
          {file.path}
        </button>
        {file.pre_existing && <Badge tone="amber">작업 전부터 변경</Badge>}
        <span className="shrink-0 font-mono text-xs tabular-nums">
          {file.additions != null && <span className="text-green-700 dark:text-green-400">+{file.additions}</span>}{" "}
          {file.deletions != null && <span className="text-red-700 dark:text-red-400">−{file.deletions}</span>}
        </span>
      </div>
      {open && (
        <div className="mb-2 overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-800">
          {error ? <div className="p-3 text-xs text-red-600">{error}</div> : diff === null ? <div className="p-3 text-xs text-zinc-500">불러오는 중…</div> : <DiffView text={diff} />}
        </div>
      )}
    </div>
  );
}

export default function ReviewCard({ task, onChanged }: { task: TaskDetail; onChanged: () => void }) {
  const { data, error, loading, reload } = useAsync(() => reviewApi.changes(task.id), [task.id, task.updated_at]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<"commit" | "complete" | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // 기본 선택: 이 작업에서 새로 바뀐 파일만. 작업 전부터 바뀌어 있던 파일은 직접 고르게 한다.
  useEffect(() => {
    if (!data) return;
    setSelected(new Set(data.files.filter((f) => data.tracked && !f.pre_existing).map((f) => f.path)));
    setMessage(data.commit_message ?? "");
  }, [data]);

  const files = useMemo(() => data?.files ?? [], [data]);
  const preExistingSelected = files.some((f) => f.pre_existing && selected.has(f.path));

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
      await reviewApi.commit(task.id, message, [...selected]);
      reload();
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
          {data.commit_sha && (
            <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300">
              커밋함 <code className="font-mono">{data.commit_sha.slice(0, 7)}</code> · {dateTime(data.committed_at)}
            </div>
          )}
          {!data.tracked && files.length > 0 && (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              이 작업은 변경 추적 기능이 생기기 전에 실행되어, 어떤 파일을 Claude가 바꿨는지 알 수 없습니다. 지금 저장 안 된 변경을 모두
              보여주니 커밋할 파일을 직접 고르세요.
            </p>
          )}

          {files.length === 0 ? (
            <Empty>{data.commit_sha ? "커밋한 뒤로 새로 바뀐 파일이 없습니다." : "이 작업이 바꾼 파일이 없습니다."}</Empty>
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
                <FileRow key={f.path} taskId={task.id} file={f} checked={selected.has(f.path)} onToggle={() => toggle(f.path)} />
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

          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className="mr-auto text-xs text-zinc-500">커밋은 이 PC의 git 설정(이름, 이메일)으로 합니다. push는 하지 않습니다.</span>
            {task.status !== "done" && (
              <Button onClick={doComplete} disabled={busy !== null}>
                {busy === "complete" ? "처리 중…" : "커밋 없이 완료"}
              </Button>
            )}
            {files.length > 0 && (
              <Button variant="primary" onClick={doCommit} disabled={busy !== null}>
                {busy === "commit" ? "커밋하는 중…" : `승인하고 커밋 (${selected.size}개 파일)`}
              </Button>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
