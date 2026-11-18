import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, taskApi, type Project, type Proposal } from "../api";
import { Badge, Button, Card, ErrorBox, StatusBadge } from "../components";

type Draft = { checked: boolean; project_id: number | null; title: string; prompt: string; open: boolean };

/** Claude가 제안한 작업(```workplace-tasks 블록)을 확인하고 골라서 등록한다. */
export default function ProposalsCard({ taskId, refreshKey }: { taskId: number; refreshKey: unknown }) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function load(list: Proposal[]) {
    setProposals(list);
    setDrafts(
      Object.fromEntries(
        list
          .filter((p) => !p.task_id)
          .map((p) => [p.index, { checked: p.project_id != null, project_id: p.project_id, title: p.title, prompt: p.prompt, open: false }]),
      ),
    );
  }

  useEffect(() => {
    taskApi.proposals(taskId).then(load).catch((e: Error) => setError(e.message));
  }, [taskId, refreshKey]);

  const pending = proposals.filter((p) => !p.task_id);
  useEffect(() => {
    if (pending.length > 0 && projects.length === 0) api.projects().then(setProjects).catch(() => {});
  }, [pending.length, projects.length]);

  if (proposals.length === 0) return null;

  const picked = pending.filter((p) => drafts[p.index]?.checked);
  const missingProject = picked.some((p) => drafts[p.index].project_id == null);

  function update(index: number, patch: Partial<Draft>) {
    setDrafts((d) => ({ ...d, [index]: { ...d[index], ...patch } }));
  }

  async function register() {
    setBusy(true);
    setError(null);
    try {
      const items = picked.map((p) => {
        const d = drafts[p.index];
        return { index: p.index, project_id: d.project_id!, title: d.title, prompt: d.prompt };
      });
      load(await taskApi.registerProposals(taskId, items));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function dismiss() {
    if (!confirm("등록하지 않은 제안을 모두 지울까요?")) return;
    try {
      await taskApi.dismissProposals(taskId);
      load(await taskApi.proposals(taskId));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Card title={`제안된 작업 ${proposals.length}개`}>
      <p className="mb-2 text-xs text-zinc-500">
        Claude가 제안한 작업입니다. 확인하고 고친 뒤 등록하면 각 프로젝트의 할 일로 추가됩니다 (바로 실행하지는 않습니다).
      </p>
      <ul className="space-y-2">
        {proposals.map((p) => {
          const d = drafts[p.index];
          if (p.task_id || !d) {
            return (
              <li key={p.index} className="flex items-center gap-2 rounded-lg border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-800">
                <Badge tone="green">등록함</Badge>
                <Link to={`/tasks/${p.task_id}`} className="min-w-0 truncate hover:underline">
                  {p.title}
                </Link>
                <span className="text-xs text-zinc-500">· {p.project}</span>
                {p.task_status && (
                  <span className="ml-auto">
                    <StatusBadge status={p.task_status} />
                  </span>
                )}
              </li>
            );
          }
          return (
            <li key={p.index} className="rounded-lg border border-zinc-200 px-3 py-2 text-sm dark:border-zinc-800">
              <div className="flex flex-wrap items-center gap-2">
                <input type="checkbox" checked={d.checked} onChange={(e) => update(p.index, { checked: e.target.checked })} />
                <input
                  value={d.title}
                  onChange={(e) => update(p.index, { title: e.target.value })}
                  maxLength={200}
                  className="min-w-0 flex-1 rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                />
                <select
                  value={d.project_id ?? ""}
                  onChange={(e) => update(p.index, { project_id: e.target.value ? Number(e.target.value) : null })}
                  className="rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                >
                  <option value="">프로젝트 선택…</option>
                  {projects.map((pr) => (
                    <option key={pr.id} value={pr.id}>
                      {pr.name}
                    </option>
                  ))}
                </select>
                <button className="text-xs text-blue-600 hover:underline dark:text-blue-400" onClick={() => update(p.index, { open: !d.open })}>
                  {d.open ? "지시 접기" : "지시 보기·고치기"}
                </button>
              </div>
              {p.project_id == null && (
                <div className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                  "{p.project || "(이름 없음)"}"과 정확히 맞는 프로젝트가 없습니다. 프로젝트를 직접 고르세요.
                </div>
              )}
              {d.open && (
                <textarea
                  value={d.prompt}
                  onChange={(e) => update(p.index, { prompt: e.target.value })}
                  rows={6}
                  className="mt-2 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                />
              )}
            </li>
          );
        })}
      </ul>
      {pending.length > 0 && (
        <div className="mt-3 flex items-center justify-end gap-2">
          {missingProject && <span className="mr-auto text-xs text-amber-700 dark:text-amber-400">선택한 제안의 프로젝트를 모두 고르세요.</span>}
          <Button onClick={dismiss} disabled={busy}>
            남은 제안 지우기
          </Button>
          <Button
            variant="primary"
            onClick={register}
            disabled={busy || picked.length === 0 || missingProject || picked.some((p) => !drafts[p.index].prompt.trim())}
          >
            {busy ? "등록하는 중…" : `${picked.length}개 등록`}
          </Button>
        </div>
      )}
      {error && <ErrorBox message={error} />}
    </Card>
  );
}
