import { useEffect, useRef, useState } from "react";

type Bookmark = { title: string; url: string };

const STORAGE_KEY = "bookmarks";

const DEFAULT_BOOKMARKS: Bookmark[] = [
  {
    title: "Agentic AI 2기 교안",
    url: "https://app.notion.com/p/teamsparta/AX-Agentic-AI-2-3ae2dc3ef51480f8807bc61feb5d9fbd?source=copy_link",
  },
];

function load(): Bookmark[] {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw == null) return DEFAULT_BOOKMARKS;
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : DEFAULT_BOOKMARKS;
  } catch {
    return DEFAULT_BOOKMARKS;
  }
}

const input =
  "h-7 w-full rounded-md border border-zinc-300 bg-white px-2 text-xs dark:border-zinc-700 dark:bg-zinc-900";

/** 헤더의 "즐겨찾기" 메뉴. 마우스를 올리면 등록된 링크 목록이 뜬다. */
export function BookmarksMenu() {
  const [items, setItems] = useState<Bookmark[]>(load);
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const closeTimer = useRef<number | null>(null);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  }, [items]);

  function show() {
    if (closeTimer.current) window.clearTimeout(closeTimer.current);
    setOpen(true);
  }
  function hide() {
    // 메뉴와 패널 사이를 지나갈 때 바로 닫히지 않도록 잠깐 기다린다
    closeTimer.current = window.setTimeout(() => {
      setOpen(false);
      setAdding(false);
    }, 150);
  }

  function add(e: React.FormEvent) {
    e.preventDefault();
    const u = url.trim();
    if (!u) return;
    const href = /^https?:\/\//i.test(u) ? u : `https://${u}`;
    setItems((prev) => [...prev, { title: title.trim() || href, url: href }]);
    setTitle("");
    setUrl("");
    setAdding(false);
  }

  function remove(i: number) {
    setItems((prev) => prev.filter((_, j) => j !== i));
  }

  return (
    <div className="relative" onMouseEnter={show} onMouseLeave={hide}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`rounded-md px-3 py-1.5 text-sm ${
          open
            ? "bg-zinc-100 text-zinc-900 dark:bg-zinc-900 dark:text-zinc-50"
            : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
        }`}
      >
        즐겨찾기
      </button>
      {open && (
        <div className="absolute left-0 top-full z-20 pt-1">
          <div className="w-72 rounded-md border border-zinc-200 bg-white p-1 shadow-lg dark:border-zinc-800 dark:bg-zinc-950">
            {items.length === 0 ? (
              <div className="px-2 py-2 text-xs text-zinc-500">등록된 즐겨찾기가 없습니다.</div>
            ) : (
              <ul>
                {items.map((b, i) => (
                  <li key={`${b.url}-${i}`} className="group flex items-center rounded hover:bg-zinc-100 dark:hover:bg-zinc-900">
                    <a
                      href={b.url}
                      target="_blank"
                      rel="noreferrer"
                      title={b.url}
                      className="min-w-0 flex-1 truncate px-2 py-1.5 text-sm"
                    >
                      {b.title}
                    </a>
                    <button
                      type="button"
                      onClick={() => remove(i)}
                      title="삭제"
                      className="invisible px-2 text-xs text-zinc-400 hover:text-red-600 group-hover:visible"
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-1 border-t border-zinc-200 pt-1 dark:border-zinc-800">
              {adding ? (
                <form onSubmit={add} className="flex flex-col gap-1 p-1">
                  <input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="제목" className={input} />
                  <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="링크" className={input} />
                  <div className="flex justify-end gap-1">
                    <button type="button" onClick={() => setAdding(false)} className="rounded-md px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900">
                      취소
                    </button>
                    <button type="submit" className="rounded-md bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700">
                      추가
                    </button>
                  </div>
                </form>
              ) : (
                <button
                  type="button"
                  onClick={() => setAdding(true)}
                  className="w-full rounded px-2 py-1.5 text-left text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-900"
                >
                  + 즐겨찾기 추가
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
