import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { api, projectChangesApi, type PushResult } from "../api";
import { FileRow, LARGE_FILE_BYTES, formatBytes } from "../changes";
import { Badge, Button, Card, Empty, ErrorBox, Loading } from "../components";
import { usd } from "../format";
import { PushBar, PushOutcome } from "../push";
import { useAsync } from "../useAsync";

export default function ProjectChangesPage() {
  const id = Number(useParams().projectId);
  const project = useAsync(() => api.project(id), [id]);
  const changes = useAsync(() => projectChangesApi.changes(id), [id]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [draftInfo, setDraftInfo] = useState<string | null>(null);
  const [committing, setCommitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [committed, setCommitted] = useState<(PushResult & { sha: string }) | null>(null);
  const [pushAfter, setPushAfter] = useState(true);

  const files = useMemo(() => changes.data ?? [], [changes.data]);

  // 처음엔 모두 선택. 다시 불러오면 아직 남아 있는 파일만 선택을 유지한다.
  useEffect(() => {
    if (!changes.data) return;
    setSelected((prev) => {
      const paths = changes.data!.map((f) => f.path);
      if (prev.size === 0) return new Set(paths);
      return new Set(paths.filter((p) => prev.has(p)));
    });
  }, [changes.data]);

  const chosen = files.filter((f) => selected.has(f.path));
  const chosenBytes = chosen.reduce((sum, f) => sum + (f.binary ? f.size_bytes ?? 0 : 0), 0);
  const largeChosen = chosen.filter((f) => (f.size_bytes ?? 0) >= LARGE_FILE_BYTES);

  function toggle(path: string) {
    setFormError(null);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  async function draft() {
    if (selected.size === 0) return setFormError("메시지를 쓸 파일을 하나 이상 고르세요.");
    setDrafting(true);
    setFormError(null);
    setDraftInfo(null);
    try {
      const res = await projectChangesApi.draftMessage(id, [...selected]);
      setMessage(res.message);
      setDraftInfo(`Claude가 고른 파일 ${selected.size}개의 내용을 보고 작성했습니다${res.cost_usd != null ? ` (${usd(res.cost_usd)})` : ""}. 확인하고 고쳐 쓰세요.`);
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setDrafting(false);
    }
  }

  async function doCommit() {
    if (selected.size === 0) return setFormError("커밋할 파일을 하나 이상 고르세요.");
    if (!message.trim()) return setFormError("커밋 메시지를 입력하세요. [Claude에게 메시지 쓰게 하기]를 눌러도 됩니다.");
    setCommitting(true);
    setFormError(null);
    try {
      const res = await projectChangesApi.commit(id, [...selected], message, pushAfter && !!project.data?.has_remote);
      setCommitted(res);
      setMessage("");
      setDraftInfo(null);
      setSelected(new Set());
      changes.reload();
      project.reload();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setCommitting(false);
    }
  }

  if ((project.loading && !project.data) || (changes.loading && !changes.data)) return <Loading />;
  if (project.error) return <ErrorBox message={project.error} />;
  const p = project.data!;

  return (
    <div className="space-y-4">
      <div>
        <Link to={`/projects/${p.id}`} className="text-xs text-zinc-500 hover:underline">
          ← {p.name}
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold">저장 안 된 변경</h1>
          <Badge>{p.branch ?? "브랜치 없음"}</Badge>
        </div>
        <div className="text-xs text-zinc-500 [overflow-wrap:anywhere]">{p.path}</div>
        <div className="mt-2">
          <PushBar project={p} onPushed={project.reload} />
        </div>
      </div>

      {committed && <PushOutcome result={committed} sha={committed.sha} />}

      {changes.error && <ErrorBox action message={changes.error} />}

      <Card
        title={`변경 파일 ${files.length}개`}
        action={
          <button onClick={changes.reload} className="text-xs text-zinc-500 hover:underline">
            새로 고침
          </button>
        }
      >
        {files.length === 0 ? (
          <Empty>저장 안 된 변경이 없습니다.</Empty>
        ) : (
          <>
            <div className="mb-1 flex items-center justify-between text-xs text-zinc-500">
              <span>{selected.size}개 선택 · 파일 이름을 누르면 내용(diff)을 볼 수 있습니다</span>
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
                loadDiff={async (path) => (await projectChangesApi.diff(id, path)).diff}
                showPreExisting={false}
              />
            ))}
            {largeChosen.length > 0 && (
              <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
                큰 파일 {largeChosen.length}개가 선택되어 있습니다 (바이너리 합계 {formatBytes(chosenBytes)}). 영상·이미지 같은 큰 파일은 저장소를 무겁게
                만들 수 있어요. 커밋하지 않을 파일이면 선택을 해제하거나 .gitignore에 추가하세요.
              </p>
            )}
          </>
        )}
      </Card>

      {files.length > 0 && (
        <Card title="커밋">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={draft} disabled={drafting || committing || selected.size === 0}>
                {drafting ? "Claude가 내용을 읽는 중…" : "Claude에게 메시지 쓰게 하기"}
              </Button>
              <span className="text-xs text-zinc-500">고른 파일의 내용과 저장소의 기존 커밋 스타일을 보고 초안을 씁니다. 파일은 바꾸지 않습니다.</span>
            </div>
            {draftInfo && <p className="text-xs text-zinc-600 dark:text-zinc-400">{draftInfo}</p>}
            <textarea
              value={message}
              onChange={(e) => {
                setMessage(e.target.value);
                setFormError(null);
              }}
              rows={Math.min(12, Math.max(4, message.split("\n").length + 1))}
              placeholder="커밋 메시지"
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 font-mono text-xs dark:border-zinc-700 dark:bg-zinc-900"
            />
            {formError && <p className="text-sm text-red-600 dark:text-red-400">{formError}</p>}
            <div className="flex flex-wrap items-center justify-end gap-2">
              <span className="mr-auto text-xs text-zinc-500">고른 파일만 이 PC의 git 설정으로 커밋합니다.</span>
              {p.has_remote ? (
                <label className="flex items-center gap-1.5 text-sm text-zinc-700 dark:text-zinc-300">
                  <input type="checkbox" checked={pushAfter} onChange={(e) => setPushAfter(e.target.checked)} />
                  커밋 후 바로 push
                </label>
              ) : (
                <span className="text-xs text-zinc-500">원격 저장소가 없어 push는 하지 않습니다</span>
              )}
              <Button variant="primary" onClick={doCommit} disabled={committing || drafting}>
                {committing
                  ? pushAfter && p.has_remote
                    ? "커밋하고 push하는 중…"
                    : "커밋하는 중…"
                  : `승인하고 ${pushAfter && p.has_remote ? "커밋·push" : "커밋"} (${selected.size}개 파일)`}
              </Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
