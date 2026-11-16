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

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
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

// ---------------------------------------------------------------- M2: 작업 / 실행

export type TaskStatus = "todo" | "running" | "review" | "done" | "failed";
export type RunStatus = "running" | "succeeded" | "failed" | "stopped";

export type Run = {
  id: number;
  task_id: number;
  prompt: string;
  status: RunStatus;
  session_id: string | null;
  resumed_from: string | null;
  started_at: string;
  ended_at: string | null;
  exit_code: number | null;
  error: string | null;
  model: string | null;
  num_turns: number | null;
  input_tokens: number;
  output_tokens: number;
  cache_creation_tokens: number;
  cache_read_tokens: number;
  cost_usd: number | null;
};

export type Task = {
  id: number;
  project_id: number;
  project_name: string | null;
  title: string;
  prompt: string;
  status: TaskStatus;
  session_id: string | null;
  created_at: string;
  updated_at: string;
  run_count: number;
  total_cost_usd: number | null;
  last_run: Run | null;
  commit_message: string | null;
  commit_sha: string | null;
  committed_at: string | null;
};

export type TaskDetail = Task & {
  project_path: string | null;
  project_dirty_files: number;
  runs: Run[];
};

export type RunEvent = {
  seq: number;
  ts: string;
  kind: "init" | "text" | "tool_use" | "tool_result" | "result" | "error" | "stderr";
  payload: Record<string, any>;
};

export type RunnerStatus = {
  claude_found: boolean;
  claude_path: string | null;
  running: number;
  max_concurrent: number;
  max_minutes: number;
  max_budget_usd: number;
  model: string | null;
  allowed_tools: string[];
  disallowed_tools: string[];
};

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const taskApi = {
  runner: () => request<RunnerStatus>("/api/runner"),
  list: (params: { projectId?: number; status?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.projectId != null) q.set("project_id", String(params.projectId));
    if (params.status) q.set("status", params.status);
    return request<Task[]>(`/api/tasks?${q}`);
  },
  counts: () => request<Record<string, number>>("/api/tasks/counts"),
  get: (id: number) => request<TaskDetail>(`/api/tasks/${id}`),
  create: (body: { project_id: number; prompt: string; title?: string; run_now: boolean }) =>
    request<Task>("/api/tasks", json(body)),
  remove: async (id: number) => {
    const res = await fetch(`/api/tasks/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? res.statusText);
  },
  run: (id: number, prompt?: string) => request<Run>(`/api/tasks/${id}/runs`, json({ prompt: prompt ?? null })),
  stop: (runId: number) => request<{ ok: boolean }>(`/api/runs/${runId}/stop`, { method: "POST" }),
  events: (runId: number) => request<RunEvent[]>(`/api/runs/${runId}/events`),
  streamUrl: (runId: number, after = -1) => `/api/runs/${runId}/stream?after=${after}`,
};

// ---------------------------------------------------------------- 검토: 변경 파일, diff, 커밋

export type FileChange = {
  path: string;
  status: string;
  kind: "added" | "modified" | "deleted" | "renamed";
  pre_existing: boolean;
  additions: number | null;
  deletions: number | null;
  binary: boolean;
  size_bytes: number | null;
};

export type Changes = {
  tracked: boolean;
  files: FileChange[];
  commit_message: string | null;
  commit_sha: string | null;
  committed_at: string | null;
};

export const reviewApi = {
  changes: (taskId: number) => request<Changes>(`/api/tasks/${taskId}/changes`),
  diff: (taskId: number, path: string) =>
    request<{ path: string; diff: string }>(`/api/tasks/${taskId}/diff?path=${encodeURIComponent(path)}`),
  commit: (taskId: number, message: string, files: string[]) =>
    request<Task>(`/api/tasks/${taskId}/commit`, json({ message, files })),
  complete: (taskId: number) => request<Task>(`/api/tasks/${taskId}/complete`, { method: "POST" }),
};

// ---------------------------------------------------------------- 프로젝트의 저장 안 된 변경 전체

export const projectChangesApi = {
  changes: (projectId: number) => request<FileChange[]>(`/api/projects/${projectId}/changes`),
  diff: (projectId: number, path: string) =>
    request<{ path: string; diff: string }>(`/api/projects/${projectId}/diff?path=${encodeURIComponent(path)}`),
  draftMessage: (projectId: number, files: string[]) =>
    request<{ message: string; cost_usd: number | null }>(`/api/projects/${projectId}/commit-message`, json({ files })),
  commit: (projectId: number, files: string[], message: string) =>
    request<{ sha: string }>(`/api/projects/${projectId}/commit`, json({ files, message })),
};
