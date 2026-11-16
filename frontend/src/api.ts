export type Project = {
  id: number;
  name: string;
  path: string;
  branch: string | null;
  dirty_files: number;
  last_commit_at: string | null;
  last_activity_at: string | null;
  session_count: number;
  last_session_at: string | null;
  input_tokens: number;
  output_tokens: number;
};

export type SessionSummary = {
  id: string;
  project_id: number | null;
  project_name: string | null;
  cwd: string | null;
  git_branch: string | null;
  title: string | null;
  first_prompt: string | null;
  started_at: string | null;
  ended_at: string | null;
  user_messages: number;
  assistant_messages: number;
  models: string[];
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  cost_usd: number | null;
};

export type TranscriptEntry = {
  kind: "user" | "command" | "assistant" | "tool_use" | "tool_result";
  ts: string | null;
  text: string;
  tool_name?: string;
  model?: string;
  is_error?: boolean;
};

export type Transcript = { total: number; offset: number; entries: TranscriptEntry[] };

export type ScanResult = {
  projects: number;
  sessions: number;
  sessions_updated: number;
  unmatched_sessions: number;
  finished_at: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* 본문이 JSON이 아니면 상태 코드만 보여준다 */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  projects: () => request<Project[]>("/api/projects"),
  project: (id: number) => request<Project>(`/api/projects/${id}`),
  sessions: (params: { projectId?: number; unmatched?: boolean; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.projectId != null) q.set("project_id", String(params.projectId));
    if (params.unmatched) q.set("unmatched", "true");
    if (params.limit) q.set("limit", String(params.limit));
    return request<SessionSummary[]>(`/api/sessions?${q}`);
  },
  session: (id: string) => request<SessionSummary>(`/api/sessions/${id}`),
  transcript: (id: string, offset = 0, limit = 200) =>
    request<Transcript>(`/api/sessions/${id}/transcript?offset=${offset}&limit=${limit}`),
  scanStatus: () => request<ScanResult | null>("/api/scan"),
  scan: () => request<ScanResult>("/api/scan", { method: "POST" }),
};
