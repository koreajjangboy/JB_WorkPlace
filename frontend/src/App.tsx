import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { api } from "./api";
import { BookmarksMenu } from "./BookmarksMenu";
import { relativeTime } from "./format";
import { useAsync } from "./useAsync";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm ${
    isActive
      ? "bg-zinc-200 font-medium text-zinc-900 dark:bg-zinc-800 dark:text-zinc-50"
      : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
  }`;

export default function App() {
  const scan = useAsync(() => api.scanStatus(), []);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  async function rescan() {
    setScanning(true);
    setScanError(null);
    try {
      await api.scan();
      scan.reload();
      setVersion((v) => v + 1); // 페이지 데이터도 다시 불러오게 한다
    } catch (e) {
      setScanError((e as Error).message);
    } finally {
      setScanning(false);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-zinc-200 bg-white/90 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/90">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-2.5">
          <NavLink to="/" className="mr-4 text-[15px] font-semibold">
            JB WorkPlace
          </NavLink>
          <nav className="flex flex-wrap items-center gap-1">
            <NavLink to="/" end className={navClass}>
              홈
            </NavLink>
            <NavLink to="/projects" className={navClass}>
              프로젝트
            </NavLink>
            <NavLink to="/tasks" className={navClass}>
              작업
            </NavLink>
            <NavLink to="/usage" className={navClass}>
              사용량
            </NavLink>
            <BookmarksMenu />
            <NavLink to="/settings" className={navClass}>
              설정
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-xs text-zinc-500">
            {scanError ? (
              <span className="text-red-600">스캔 실패: {scanError}</span>
            ) : (
              <span>마지막 스캔 {scan.data ? relativeTime(scan.data.finished_at) : "진행 중…"}</span>
            )}
            <button
              onClick={rescan}
              disabled={scanning}
              className="rounded-md border border-zinc-300 px-2.5 py-1 text-xs hover:bg-zinc-100 disabled:opacity-60 dark:border-zinc-700 dark:hover:bg-zinc-900"
            >
              {scanning ? "스캔 중…" : "다시 스캔"}
            </button>
            <NavLink
              to="/tasks/new"
              className="inline-flex h-7 items-center rounded-md bg-blue-600 px-2.5 text-xs text-white hover:bg-blue-700"
            >
              + 새 작업
            </NavLink>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet key={version} />
      </main>
    </div>
  );
}
