import { useMemo, useRef, useState } from "react";
import { request } from "./api";
import { Card } from "./components";
import { useAsync } from "./useAsync";

export type CalendarEvent = {
  id: string;
  title: string;
  start: string;
  end: string;
  start_date: string;
  end_date: string;
  all_day: boolean;
  location: string | null;
  description: string | null;
  calendar: string;
  color: string;
};

export type CalendarData = {
  configured: boolean;
  timezone: string;
  calendars: { name: string; color: string }[];
  events: CalendarEvent[];
  errors: string[];
};

export const calendarApi = {
  events: (start: string, end: string, refresh = false) =>
    request<CalendarData>(`/api/calendar/events?start=${start}&end=${end}${refresh ? "&refresh=true" : ""}`),
};

const WEEK = ["일", "월", "화", "수", "목", "금", "토"];
const DAYS = 7; // 오늘부터 7일
const MAX_CHIPS = 5;

function ymd(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function addDays(d: Date, n: number) {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function hhmm(iso: string) {
  // 백엔드가 설정 시간대로 바꿔 준 시각(예: 2026-11-17T09:30:00+09:00)을 그대로 읽는다.
  return iso.slice(11, 16);
}

function eventTime(e: CalendarEvent, day: string) {
  if (e.all_day) return "종일";
  const startsToday = e.start_date === day;
  const endsToday = e.end_date === day;
  if (startsToday && endsToday) return e.start === e.end ? hhmm(e.start) : `${hhmm(e.start)}–${hhmm(e.end)}`;
  if (startsToday) return `${hhmm(e.start)}부터`;
  if (endsToday) return `${hhmm(e.end)}까지`;
  return "종일";
}

export default function CalendarSection() {
  const today = ymd(new Date());
  // 오늘 기준 몇 번째 7일 구간인지 (0 = 오늘부터 7일)
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(today);

  const base = new Date(`${today}T00:00:00`);
  const days = Array.from({ length: DAYS }, (_, i) => addDays(base, offset * DAYS + i));
  const from = ymd(days[0]);
  const to = ymd(days[DAYS - 1]);

  const forceRef = useRef(false);
  const { data, error, loading, reload } = useAsync(() => {
    const force = forceRef.current;
    forceRef.current = false;
    return calendarApi.events(from, to, force);
  }, [from, to]);
  const refresh = () => {
    forceRef.current = true; // 서버 캐시를 건너뛰고 Google에서 다시 받는다.
    reload();
  };

  const byDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const e of data?.events ?? []) {
      // 여러 날에 걸친 일정은 걸친 날마다 보여준다.
      const first = e.start_date < from ? from : e.start_date;
      for (let d = new Date(`${first}T00:00:00`); ymd(d) <= e.end_date; d = addDays(d, 1)) {
        const key = ymd(d);
        if (key > to) break;
        if (!map.has(key)) map.set(key, []);
        map.get(key)!.push(e);
      }
    }
    return map;
  }, [data, from, to]);

  const move = (n: number) => {
    const next = offset + n;
    setOffset(next);
    // 선택한 날도 새 구간의 첫날(이번 구간이면 오늘)로 옮긴다.
    setSelected(ymd(addDays(base, next * DAYS)));
  };
  const goToday = () => {
    setOffset(0);
    setSelected(today);
  };
  const first = days[0];
  const last = days[DAYS - 1];

  const selectedEvents = byDay.get(selected) ?? [];
  const selDate = new Date(`${selected}T00:00:00`);

  const header = (
    <div className="flex items-center gap-1.5">
      <button onClick={() => move(-1)} className="h-7 w-7 rounded-md text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800" aria-label="이전 7일">
        ‹
      </button>
      <span className="min-w-[8rem] text-center text-sm font-medium tabular-nums">
        {first.getMonth() + 1}/{first.getDate()} – {last.getMonth() + 1}/{last.getDate()}
      </span>
      <button onClick={() => move(1)} className="h-7 w-7 rounded-md text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800" aria-label="다음 7일">
        ›
      </button>
      <button onClick={goToday} className="ml-1 h-7 rounded-md border border-zinc-300 px-2 text-xs hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800">
        오늘
      </button>
      <button
        onClick={refresh}
        disabled={loading}
        className="h-7 rounded-md px-2 text-xs text-blue-600 hover:underline disabled:opacity-50 dark:text-blue-400"
      >
        {loading ? "불러오는 중…" : "새로고침"}
      </button>
    </div>
  );

  return (
    <Card title="Google 캘린더" action={header}>
      {error && <p className="mb-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950 dark:text-red-300">일정을 불러오지 못했습니다: {error}</p>}
      {data?.errors.map((m) => (
        <p key={m} className="mb-2 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">
          {m}
        </p>
      ))}
      {data && !data.configured && <SetupGuide />}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)]">
        {/* 달력 */}
        <div className={loading && !data ? "opacity-60" : ""}>
          <div className="grid grid-cols-7 text-center text-[11px] text-zinc-500">
            {days.map((d) => {
              const dow = d.getDay();
              return (
                <div key={ymd(d)} className={`py-1 ${dow === 0 ? "text-red-500" : dow === 6 ? "text-blue-500" : ""}`}>
                  {WEEK[dow]}
                </div>
              );
            })}
          </div>
          <div className="grid grid-cols-7 overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
            {days.map((d, i) => {
              const key = ymd(d);
              const evs = byDay.get(key) ?? [];
              const isToday = key === today;
              const isSel = key === selected;
              const dow = d.getDay();
              return (
                <button
                  key={key}
                  onClick={() => setSelected(key)}
                  className={`flex min-h-[9rem] flex-col gap-0.5 border-zinc-100 p-1 text-left align-top dark:border-zinc-800 ${
                    i !== 0 ? "border-l" : ""
                  } ${isSel ? "ring-2 ring-blue-500 ring-inset" : "hover:bg-zinc-50 dark:hover:bg-zinc-800/50"}`}
                >
                  <span
                    className={`inline-flex h-5 min-w-5 items-center justify-center self-start rounded-full px-1 text-[11px] tabular-nums ${
                      isToday ? "bg-blue-600 font-semibold text-white" : dow === 0 ? "text-red-500" : dow === 6 ? "text-blue-500" : ""
                    }`}
                  >
                    {d.getDate() === 1 || i === 0 ? `${d.getMonth() + 1}/${d.getDate()}` : d.getDate()}
                  </span>
                  {evs.slice(0, MAX_CHIPS).map((e) => (
                    <EventChip key={e.id} e={e} dim={false} />
                  ))}
                  {evs.length > MAX_CHIPS && <span className="px-1 text-[10px] text-zinc-500">+{evs.length - MAX_CHIPS}개 더</span>}
                </button>
              );
            })}
          </div>
          {data && data.calendars.length > 1 && (
            <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-zinc-500">
              {data.calendars.map((c) => (
                <span key={c.name} className="inline-flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full" style={{ background: c.color }} />
                  {c.name}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* 선택한 날의 일정 */}
        <div className="min-w-0">
          <div className="mb-2 flex items-baseline justify-between">
            <h3 className="text-sm font-semibold">
              {selDate.getMonth() + 1}월 {selDate.getDate()}일 ({WEEK[selDate.getDay()]})
              {selected === today && <span className="ml-1.5 text-xs font-normal text-blue-600 dark:text-blue-400">오늘</span>}
            </h3>
            <span className="text-xs text-zinc-500">{selectedEvents.length}개</span>
          </div>
          {selectedEvents.length === 0 ? (
            <p className="rounded-lg bg-zinc-50 py-6 text-center text-sm text-zinc-500 dark:bg-zinc-800/40">일정이 없습니다.</p>
          ) : (
            <ul className="space-y-1.5">
              {selectedEvents.map((e) => (
                <li key={e.id} className="flex gap-2.5 rounded-lg border border-zinc-100 p-2.5 dark:border-zinc-800">
                  <span className="mt-0.5 w-1 shrink-0 self-stretch rounded-full" style={{ background: e.color }} />
                  <div className="min-w-0 flex-1">
                    <div className="text-xs text-zinc-500 tabular-nums">{eventTime(e, selected)}</div>
                    <div className="text-sm font-medium break-words">{e.title}</div>
                    {e.location && <div className="truncate text-xs text-zinc-500">📍 {e.location}</div>}
                    {e.description && <div className="mt-1 line-clamp-2 text-xs whitespace-pre-line text-zinc-500">{e.description}</div>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Card>
  );
}

function EventChip({ e, dim }: { e: CalendarEvent; dim: boolean }) {
  if (e.all_day) {
    return (
      <span
        className={`truncate rounded px-1 py-px text-[10px] leading-4 text-white ${dim ? "opacity-50" : ""}`}
        style={{ background: e.color }}
        title={e.title}
      >
        {e.title}
      </span>
    );
  }
  return (
    <span className={`flex items-center gap-1 truncate px-0.5 text-[10px] leading-4 ${dim ? "opacity-50" : ""}`} title={`${hhmm(e.start)} ${e.title}`}>
      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: e.color }} />
      <span className="shrink-0 text-zinc-500 tabular-nums">{hhmm(e.start)}</span>
      <span className="truncate">{e.title}</span>
    </span>
  );
}

function SetupGuide() {
  return (
    <div className="mb-3 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs leading-relaxed text-blue-900 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-200">
      <div className="mb-1 font-semibold">Google 캘린더 연결하기</div>
      <ol className="list-decimal space-y-0.5 pl-4">
        <li>Google 캘린더 → 왼쪽 목록에서 캘린더의 ⋮ → <b>설정 및 공유</b></li>
        <li>
          <b>캘린더 통합</b>의 <b>iCal 형식의 비공개 주소</b>를 복사
        </li>
        <li>
          <code className="rounded bg-white/60 px-1 dark:bg-black/30">backend\.env</code>에{" "}
          <code className="rounded bg-white/60 px-1 dark:bg-black/30">GOOGLE_CALENDAR_ICS_URLS=복사한주소</code> 추가 (여러 개면 쉼표로)
        </li>
        <li>백엔드 서버를 다시 시작</li>
      </ol>
      <div className="mt-1 opacity-80">비공개 주소는 비밀번호처럼 다루세요. 주소를 아는 사람은 누구나 일정을 볼 수 있습니다.</div>
    </div>
  );
}
