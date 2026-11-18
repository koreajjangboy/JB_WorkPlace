import { type ReactNode, useEffect, useRef, useState } from "react";
import { request } from "./api";
import { Card } from "./components";
import { relativeTime } from "./format";
import { useAsync } from "./useAsync";

type Loan = { title: string; status: string | null; lent_on: string | null; due_on: string | null };
type LoginState = { state: "idle" | "waiting" | "done" | "failed"; message: string | null };
type BooknaraeData = {
  logged_in: boolean;
  error: string | null;
  fetched_at: string | null;
  loans: Loan[];
  login: LoginState;
  site_url: string;
};

const booknaraeApi = {
  loans: (refresh = false) => request<BooknaraeData>(`/api/booknarae${refresh ? "?refresh=true" : ""}`),
  login: () => request<LoginState>("/api/booknarae/login", { method: "POST" }),
  loginStatus: () => request<LoginState>("/api/booknarae/login"),
};

function daysLeft(due: string) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((new Date(`${due}T00:00:00`).getTime() - today.getTime()) / 86400000);
}

function DueBadge({ due }: { due: string | null }) {
  if (!due) return <span className="text-xs text-zinc-400">반납일 없음</span>;
  const n = daysLeft(due);
  const label = n < 0 ? `${-n}일 연체` : n === 0 ? "오늘 반납" : `D-${n}`;
  const color =
    n < 0
      ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
      : n <= 3
        ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
        : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium tabular-nums ${color}`}>{label}</span>;
}

function md(iso: string) {
  const [, m, d] = iso.split("-");
  return `${Number(m)}/${Number(d)}`;
}

export default function BooknaraeSection() {
  const forceRef = useRef(false);
  const { data, error, loading, reload } = useAsync(() => {
    const force = forceRef.current;
    forceRef.current = false;
    return booknaraeApi.loans(force);
  }, []);
  const refresh = () => {
    forceRef.current = true; // 서버 캐시를 건너뛰고 책나래에서 다시 받는다.
    reload();
  };

  const [login, setLogin] = useState<LoginState | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const loginState = login ?? data?.login ?? null;
  const waiting = loginState?.state === "waiting";

  // 로그인 창이 열려 있는 동안 상태를 확인하고, 끝나면 목록을 다시 받는다.
  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(async () => {
      try {
        const s = await booknaraeApi.loginStatus();
        setLogin(s);
        if (s.state !== "waiting") reload();
      } catch {
        /* 다음 차례에 다시 확인 */
      }
    }, 2000);
    return () => clearInterval(t);
  }, [waiting, reload]);

  const startLogin = async () => {
    setLoginError(null);
    try {
      setLogin(await booknaraeApi.login());
    } catch (e) {
      setLoginError(e instanceof Error ? e.message : String(e));
    }
  };

  const header = (
    <div className="flex items-center gap-2">
      {data?.fetched_at && <span className="text-xs text-zinc-500">{relativeTime(data.fetched_at)} 기준</span>}
      {data?.logged_in && (
        <button
          onClick={refresh}
          disabled={loading}
          className="h-7 rounded-md px-2 text-xs text-blue-600 hover:underline disabled:opacity-50 dark:text-blue-400"
        >
          {loading ? "불러오는 중…" : "새로고침"}
        </button>
      )}
    </div>
  );

  const loans = data?.loans ?? [];

  return (
    <Card title="책나래 대출 현황" action={header}>
      {error && <Notice tone="red">대출 현황을 불러오지 못했습니다: {error}</Notice>}
      {data?.error && <Notice tone="amber">책나래에서 목록을 받지 못했습니다: {data.error}</Notice>}
      {loginError && <Notice tone="red">{loginError}</Notice>}
      {loginState?.state === "failed" && loginState.message && <Notice tone="amber">{loginState.message}</Notice>}

      {data && !data.logged_in && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 dark:border-blue-900 dark:bg-blue-950">
          <span className="text-xs text-blue-900 dark:text-blue-200">
            {waiting
              ? "열린 브라우저 창에서 책나래에 로그인하세요. 로그인되면 창이 자동으로 닫히고 목록을 가져옵니다."
              : loans.length > 0
                ? "로그인이 필요합니다. 아래는 마지막으로 가져온 목록입니다."
                : "로그인이 필요합니다."}
          </span>
          <button
            onClick={startLogin}
            disabled={waiting}
            className="h-7 rounded-md bg-blue-600 px-3 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-60"
          >
            {waiting ? "로그인 기다리는 중…" : "책나래 로그인"}
          </button>
        </div>
      )}

      {loading && !data ? (
        <p className="py-4 text-center text-sm text-zinc-500">불러오는 중…</p>
      ) : loans.length === 0 ? (
        data?.logged_in && <p className="rounded-lg bg-zinc-50 py-6 text-center text-sm text-zinc-500 dark:bg-zinc-800/40">대출 중인 책이 없습니다.</p>
      ) : (
        <ul className={data && !data.logged_in ? "opacity-70" : ""}>
          {loans.map((l, i) => (
            <li key={`${l.title}-${i}`} className="flex items-center justify-between gap-3 border-t border-zinc-100 py-2.5 first:border-t-0 dark:border-zinc-800">
              <div className="min-w-0">
                <div className="truncate text-sm">{l.title}</div>
                <div className="text-xs text-zinc-500">
                  {[l.status, l.lent_on && `대출 ${md(l.lent_on)}`].filter(Boolean).join(" · ") || "—"}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {l.due_on && <span className="text-xs text-zinc-500 tabular-nums">반납 {md(l.due_on)}</span>}
                <DueBadge due={l.due_on} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Notice({ tone, children }: { tone: "red" | "amber"; children: ReactNode }) {
  const cls =
    tone === "red"
      ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
      : "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300";
  return <p className={`mb-2 rounded-md px-3 py-2 text-xs ${cls}`}>{children}</p>;
}
