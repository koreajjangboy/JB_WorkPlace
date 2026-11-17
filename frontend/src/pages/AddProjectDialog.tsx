import { useState } from "react";
import { api, type FolderEntry } from "../api";
import { Badge, Button, Empty, ErrorBox, Loading } from "../components";
import { useAsync } from "../useAsync";

/** 폴더를 탐색해 프로젝트로 추가한다. 처음엔 스캔 폴더(C:\dev 등) 목록이 나오고, 폴더를 눌러 안으로 들어간다. */
export default function AddProjectDialog({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [path, setPath] = useState<string | undefined>(undefined);
  const { data, error, loading } = useAsync(() => api.folders(path), [path]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [manual, setManual] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [hideRegistered, setHideRegistered] = useState(true);

  const toggle = (p: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });

  const add = async (paths: string[]) => {
    setSaving(true);
    setSaveError(null);
    try {
      for (const p of paths) await api.addProject(p);
      onAdded();
      onClose();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const folders = (data?.folders ?? []).filter((f) => !(hideRegistered && f.status === "registered"));
  const selectable = folders.filter((f) => f.status !== "registered");
  const allSelected = selectable.length > 0 && selectable.every((f) => selected.has(f.path));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg border border-zinc-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <h2 className="font-semibold">프로젝트 추가</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200" aria-label="닫기">
            ✕
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b border-zinc-200 px-4 py-2 text-sm dark:border-zinc-800">
          <Button onClick={() => setPath(undefined)} disabled={!data?.path}>
            스캔 폴더
          </Button>
          <Button onClick={() => setPath(data?.parent ?? undefined)} disabled={!data?.parent}>
            ↑ 위로
          </Button>
          <span className="min-w-0 flex-1 truncate font-mono text-xs text-zinc-500" title={data?.path ?? ""}>
            {data?.path ?? "스캔 폴더 목록"}
          </span>
          <label className="flex items-center gap-1.5 text-xs text-zinc-600 dark:text-zinc-400">
            <input type="checkbox" checked={hideRegistered} onChange={(e) => setHideRegistered(e.target.checked)} />
            이미 추가된 폴더 숨기기
          </label>
        </div>

        <div className="min-h-[240px] flex-1 overflow-y-auto px-2 py-1">
          {loading && !data ? (
            <Loading />
          ) : error ? (
            <ErrorBox message={error} />
          ) : folders.length === 0 ? (
            <Empty>하위 폴더가 없습니다.</Empty>
          ) : (
            <>
              <label className="flex items-center gap-2 px-2 py-1.5 text-xs text-zinc-500">
                <input
                  type="checkbox"
                  checked={allSelected}
                  disabled={selectable.length === 0}
                  onChange={() =>
                    setSelected((prev) => {
                      const next = new Set(prev);
                      for (const f of selectable) {
                        if (allSelected) next.delete(f.path);
                        else next.add(f.path);
                      }
                      return next;
                    })
                  }
                />
                이 폴더의 항목 모두 선택
              </label>
              {folders.map((f) => (
                <FolderRow key={f.path} f={f} checked={selected.has(f.path)} onToggle={() => toggle(f.path)} onOpen={() => setPath(f.path)} />
              ))}
            </>
          )}
        </div>

        <div className="space-y-2 border-t border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <div className="flex gap-2">
            <input
              value={manual}
              onChange={(e) => setManual(e.target.value)}
              placeholder="경로를 직접 입력 (예: D:\work\my-app)"
              className="h-8 min-w-0 flex-1 rounded-md border border-zinc-300 bg-white px-2.5 font-mono text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
            <Button onClick={() => add([manual.trim()])} disabled={saving || !manual.trim()}>
              경로 추가
            </Button>
          </div>
          {saveError && <ErrorBox message={saveError} />}
          <div className="flex items-center justify-end gap-2">
            <span className="mr-auto text-xs text-zinc-500">{selected.size}개 선택됨</span>
            <Button onClick={onClose}>취소</Button>
            <Button variant="primary" onClick={() => add([...selected])} disabled={saving || selected.size === 0}>
              {saving ? "추가 중…" : `${selected.size}개 추가`}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function FolderRow({ f, checked, onToggle, onOpen }: { f: FolderEntry; checked: boolean; onToggle: () => void; onOpen: () => void }) {
  const registered = f.status === "registered";
  return (
    <div className="flex items-center gap-2 rounded px-2 py-1.5 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
      <input type="checkbox" checked={registered || checked} disabled={registered} onChange={onToggle} />
      <button onClick={onOpen} className="min-w-0 flex-1 truncate text-left text-sm hover:underline" title={`${f.path} 안으로 들어가기`}>
        📁 {f.name}
      </button>
      {f.is_git && <Badge tone="blue">git</Badge>}
      {registered && <Badge tone="green">추가됨</Badge>}
      {f.status === "hidden" && <Badge tone="amber">제외됨</Badge>}
    </div>
  );
}
