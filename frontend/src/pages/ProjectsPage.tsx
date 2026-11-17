import { useMemo, useState } from "react";
import { Link } from "react-router";
import { api } from "../api";
import { Badge, Button, Card, Empty, ErrorBox, Loading, SessionRow } from "../components";
import { relativeTime, tokens } from "../format";
import { useAsync } from "../useAsync";
import AddProjectDialog from "./AddProjectDialog";

type Sort = "activity" | "name" | "sessions";

export default function ProjectsPage() {
  const { data, error, loading, reload } = useAsync(() => api.projects(), []);
  const unmatched = useAsync(() => api.sessions({ unmatched: true, limit: 20 }), []);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>("activity");
  const [onlyWithSessions, setOnlyWithSessions] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = () => {
    reload();
    unmatched.reload();
  };

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const hideSelected = async () => {
    const names = (data ?? []).filter((p) => selected.has(p.id)).map((p) => p.name);
    const msg = `${names.length}개 프로젝트를 목록에서 제외할까요?\n\n${names.join("\n")}\n\n폴더와 세션 기록은 지워지지 않으며, 나중에 [프로젝트 추가]에서 다시 추가할 수 있습니다.`;
    if (!window.confirm(msg)) return;
    setBusy(true);
    setActionError(null);
    try {
      await api.hideProjects([...selected]);
      setSelected(new Set());
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const rows = useMemo(() => {
    let list = data ?? [];
    const q = query.trim().toLowerCase();
    if (q) list = list.filter((p) => p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q));
    if (onlyWithSessions) list = list.filter((p) => p.session_count > 0);
    const sorted = [...list];
    if (sort === "name") sorted.sort((a, b) => a.name.localeCompare(b.name));
    if (sort === "sessions") sorted.sort((a, b) => b.session_count - a.session_count);
    return sorted; // activity: 서버가 이미 최근 활동순으로 준다
  }, [data, query, sort, onlyWithSessions]);

  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox message={error} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-2 text-lg font-semibold">프로젝트 {data?.length ?? 0}</h1>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="이름이나 경로로 찾기"
          className="h-8 w-56 rounded-md border border-zinc-300 bg-white px-2.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as Sort)}
          className="h-8 rounded-md border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          <option value="activity">최근 활동순</option>
          <option value="name">이름순</option>
          <option value="sessions">세션 많은 순</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm text-zinc-600 dark:text-zinc-400">
          <input type="checkbox" checked={onlyWithSessions} onChange={(e) => setOnlyWithSessions(e.target.checked)} />
          세션 있는 것만
        </label>
        <div className="ml-auto flex items-center gap-2">
          {selected.size > 0 && (
            <>
              <Button onClick={() => setSelected(new Set())} disabled={busy}>
                선택 해제
              </Button>
              <Button variant="danger" onClick={hideSelected} disabled={busy}>
                {busy ? "제외 중…" : `선택한 ${selected.size}개 삭제`}
              </Button>
            </>
          )}
          <Button variant="primary" onClick={() => setAdding(true)}>
            + 프로젝트 추가
          </Button>
        </div>
      </div>

      {actionError && <ErrorBox message={actionError} />}
      {adding && <AddProjectDialog onClose={() => setAdding(false)} onAdded={refresh} />}

      <Card>
        {rows.length === 0 ? (
          <Empty>조건에 맞는 프로젝트가 없습니다.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="text-left text-xs text-zinc-500">
                  <th className="w-8 pb-2 font-normal">
                    <input
                      type="checkbox"
                      aria-label="모두 선택"
                      checked={rows.length > 0 && rows.every((p) => selected.has(p.id))}
                      onChange={(e) => setSelected(e.target.checked ? new Set(rows.map((p) => p.id)) : new Set())}
                    />
                  </th>
                  <th className="pb-2 font-normal">프로젝트</th>
                  <th className="pb-2 font-normal">브랜치</th>
                  <th className="pb-2 text-right font-normal">변경</th>
                  <th className="pb-2 text-right font-normal">세션</th>
                  <th className="pb-2 text-right font-normal">출력 토큰</th>
                  <th className="pb-2 text-right font-normal">마지막 활동</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr
                    key={p.id}
                    className={`border-t border-zinc-100 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-800/50 ${selected.has(p.id) ? "bg-blue-50/60 dark:bg-blue-950/30" : ""}`}
                  >
                    <td className="py-2">
                      <input type="checkbox" aria-label={`${p.name} 선택`} checked={selected.has(p.id)} onChange={() => toggle(p.id)} />
                    </td>
                    <td className="py-2 pr-3">
                      <Link to={`/projects/${p.id}`} className="font-medium hover:underline">
                        {p.name}
                      </Link>
                      <div className="text-xs text-zinc-500">{p.path}</div>
                    </td>
                    <td className="py-2 pr-3">
                      <Badge>{p.branch ?? "—"}</Badge>
                      {p.ahead > 0 && (
                        <span className="ml-1" title="push 안 된 커밋">
                          <Badge tone="blue">↑{p.ahead}</Badge>
                        </span>
                      )}
                      {p.behind > 0 && (
                        <span className="ml-1" title="원격에만 있는 커밋 (pull 필요)">
                          <Badge tone="amber">↓{p.behind}</Badge>
                        </span>
                      )}
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      {p.dirty_files > 0 ? (
                        <Link to={`/projects/${p.id}/changes`} className="hover:opacity-80" title="변경 내용 보고 커밋하기">
                          <Badge tone="amber">{p.dirty_files}</Badge>
                        </Link>
                      ) : (
                        <span className="text-zinc-400">0</span>
                      )}
                    </td>
                    <td className="py-2 text-right tabular-nums">{p.session_count || <span className="text-zinc-400">0</span>}</td>
                    <td className="py-2 text-right tabular-nums">{p.output_tokens ? tokens(p.output_tokens) : <span className="text-zinc-400">—</span>}</td>
                    <td className="py-2 text-right text-xs text-zinc-500">{relativeTime(p.last_activity_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {unmatched.data && unmatched.data.length > 0 && (
        <Card title="프로젝트에 연결되지 않은 세션" action={<span className="text-xs text-zinc-500">스캔 폴더 밖에서 연 세션</span>}>
          {unmatched.data.map((s) => (
            <SessionRow key={s.id} s={s} />
          ))}
        </Card>
      )}
    </div>
  );
}
