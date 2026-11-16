import { useState } from "react";
import type { FileChange } from "./api";
import { Badge } from "./components";

const KIND: Record<FileChange["kind"], [string, "green" | "blue" | "red" | "zinc"]> = {
  added: ["추가", "green"],
  modified: ["수정", "blue"],
  deleted: ["삭제", "red"],
  renamed: ["이름 변경", "zinc"],
};

export const LARGE_FILE_BYTES = 1_000_000;

export function formatBytes(n: number | null): string {
  if (n == null) return "";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}MB`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}KB`;
  return `${n}B`;
}

export function DiffView({ text }: { text: string }) {
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

/** 변경 파일 한 줄: 체크박스, 종류, 경로(누르면 diff), 크기/줄 수. */
export function FileRow({
  file,
  checked,
  onToggle,
  loadDiff,
  showPreExisting = true,
}: {
  file: FileChange;
  checked: boolean;
  onToggle: () => void;
  loadDiff: (path: string) => Promise<string>;
  showPreExisting?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [diff, setDiff] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [label, tone] = KIND[file.kind];
  const large = (file.size_bytes ?? 0) >= LARGE_FILE_BYTES;

  async function toggleDiff() {
    const next = !open;
    setOpen(next);
    if (next && diff === null) {
      try {
        setDiff(await loadDiff(file.path));
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
        {showPreExisting && file.pre_existing && <Badge tone="amber">작업 전부터 변경</Badge>}
        {file.binary && <Badge>바이너리</Badge>}
        {large && <Badge tone="amber">큰 파일</Badge>}
        <span className="shrink-0 font-mono text-xs text-zinc-500 tabular-nums">
          {file.additions != null && <span className="text-green-700 dark:text-green-400">+{file.additions}</span>}{" "}
          {file.deletions != null && <span className="text-red-700 dark:text-red-400">−{file.deletions}</span>}
          {file.additions == null && formatBytes(file.size_bytes)}
        </span>
      </div>
      {open && (
        <div className="mb-2 overflow-hidden rounded-md border border-zinc-200 dark:border-zinc-800">
          {error ? (
            <div className="p-3 text-xs text-red-600">{error}</div>
          ) : diff === null ? (
            <div className="p-3 text-xs text-zinc-500">불러오는 중…</div>
          ) : (
            <DiffView text={file.binary ? `${diff}\n크기: ${formatBytes(file.size_bytes)}` : diff} />
          )}
        </div>
      )}
    </div>
  );
}
