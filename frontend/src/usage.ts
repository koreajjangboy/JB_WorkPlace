import { request } from "./api";

export type UsageProvider = {
  id: number;
  name: string;
  display_name: string;
  kind: string;
  color: string | null;
  is_new: boolean;
  cost: number;
  missing_price: boolean;
  series: number[];
  units: Record<string, number>;
  tokens: Record<string, number>;
  models: { model: string; cost: number; quantity: number; unit: string | null; missing_price: boolean }[];
  projects: { name: string; cost: number }[];
  records: number;
};

export type UsageSummary = {
  days: number;
  kind: "all" | "text" | "media";
  labels: string[];
  providers: UsageProvider[];
  total_cost: number;
  prev_total_cost: number;
  provider_count: number;
  new_providers: { id: number; name: string; missing_price: boolean }[];
};

export type ProviderInfo = {
  id: number;
  name: string;
  display_name: string | null;
  kind: string;
  color: string | null;
  created_at: string;
};

export type ServiceStatus = ProviderInfo & {
  collection: "claude_logs" | "app" | "manual" | "takeout";
  default_unit: string | null;
  detect: string | null;
  website: string | null;
  notes: string | null;
  helper: string;
  has_price: boolean;
  records: number;
  records_7d: number;
  last_at: string | null;
  reporting_projects: string[];
  used_in: { project: string; files: string[]; instrumented: boolean }[];
};

export type CatalogItem = {
  name: string;
  display_name: string;
  kind: string;
  default_unit: string;
  collection: string;
  detect: string;
  helper: string;
  website: string;
  registered: boolean;
};

export const serviceApi = {
  status: (refresh = false) => request<{ scanned_at: string; services: ServiceStatus[] }>(`/api/usage/services?refresh=${refresh}`),
  catalog: () => request<CatalogItem[]>("/api/usage/catalog"),
  create: (data: { name: string; display_name?: string; kind?: string; default_unit?: string; collection?: string; detect?: string; website?: string }) =>
    request<ProviderInfo>("/api/usage/providers", body("POST", data)),
  update: (id: number, data: Partial<Pick<ServiceStatus, "display_name" | "kind" | "color" | "collection" | "default_unit" | "detect" | "website" | "notes">>) =>
    request<ProviderInfo>(`/api/usage/providers/${id}`, body("PATCH", data)),
  remove: async (id: number) => {
    const res = await fetch(`/api/usage/providers/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? res.statusText);
  },
  manual: (data: { provider_id: number; date: string; cost_usd?: number | null; quantity?: number; unit?: string; project?: string; note?: string }) =>
    request<{ id: number }>("/api/usage/manual", body("POST", data)),
};

export type PriceRule = {
  id: number;
  provider_id: number;
  model: string | null;
  unit: string;
  price_per_unit: number;
  valid_from: string;
  note: string | null;
};

const body = (method: string, data: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const usageApi = {
  summary: (days: number, kind: string) => request<UsageSummary>(`/api/usage/summary?days=${days}&kind=${kind}`),
  providers: () => request<ProviderInfo[]>("/api/usage/providers"),
  patchProvider: (id: number, patch: Partial<Pick<ProviderInfo, "display_name" | "kind" | "color">>) =>
    request<ProviderInfo>(`/api/usage/providers/${id}`, body("PATCH", patch)),
  prices: () => request<PriceRule[]>("/api/usage/prices"),
  addPrice: (rule: { provider_id: number; model?: string | null; unit: string; price_per_unit: number; note?: string }) =>
    request<PriceRule>("/api/usage/prices", body("POST", rule)),
  deletePrice: async (id: number) => {
    const res = await fetch(`/api/usage/prices/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? res.statusText);
  },
};

export const OTHER_COLOR = "#B4B2A9";
export const TOP_N = 5;

/** 상위 N개는 각자 색, 나머지는 "기타"로 묶는다. 색이 없으면 순서대로 배정. */
export function topProviders(providers: UsageProvider[]) {
  const fallback = ["#D85A30", "#7F77DD", "#1D9E75", "#D4537E", "#378ADD"];
  const top = providers.slice(0, TOP_N).map((p, i) => ({ ...p, color: p.color || fallback[i] }));
  const rest = providers.slice(TOP_N);
  return { top, rest };
}

export const UNIT_LABEL: Record<string, string> = {
  token: "토큰",
  char: "문자",
  credit: "크레딧",
  second: "초",
  image: "이미지",
  request: "요청",
  input_token: "입력 토큰",
  output_token: "출력 토큰",
  cache_write_token: "캐시 쓰기 토큰",
  cache_read_token: "캐시 읽기 토큰",
};

export function formatQuantity(units: Record<string, number>): string {
  return Object.entries(units)
    .map(([unit, q]) => {
      const n = q >= 1_000_000 ? `${(q / 1_000_000).toFixed(1)}M` : q >= 1_000 ? `${Math.round(q / 1_000)}K` : `${Math.round(q * 100) / 100}`;
      return `${n} ${UNIT_LABEL[unit] ?? unit}`;
    })
    .join(" · ");
}

export function money(n: number): string {
  if (n >= 100) return `$${Math.round(n).toLocaleString()}`;
  if (n >= 1) return `$${n.toFixed(2)}`;
  if (n > 0) return `$${n.toFixed(3)}`;
  return "$0";
}

export type TakeoutImport = { file: string; days: number; prompts: number; tokens: number; first: string; last: string; imported_at: string };
export type TakeoutStatus = { dirs: { path: string; exists: boolean }[]; last_import: TakeoutImport | null };

/** Gemini 앱 사용량: Google Takeout 파일 가져오기 */
export const takeoutApi = {
  status: () => request<TakeoutStatus>("/api/usage/takeout"),
  scan: () => request<TakeoutStatus & { imported: TakeoutImport[] }>("/api/usage/takeout/scan", { method: "POST" }),
  upload: (file: File) =>
    request<TakeoutImport>(`/api/usage/takeout?name=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    }),
};
