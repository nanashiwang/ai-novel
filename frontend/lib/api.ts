/**
 * 后端 API 客户端层，按资源分模块导出。
 *
 * 字段命名与后端 Pydantic schema 保持一致（snake_case）。
 * 上层组件直接使用此处定义的类型即可，无需手动定义 DTO。
 */
import { http } from "./http";

// ----- Auth -----
export type CurrentUser = {
  id: string;
  email: string;
  display_name: string;
  platform_role: string;
  organization_role: string;
  organization_id: string;
  organization_name: string;
  plan_code: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: CurrentUser;
};

export const authApi = {
  login: (email: string, password: string) =>
    http.post<TokenResponse>("/auth/login", { email, password }),
  register: (email: string, password: string, display_name: string) =>
    http.post<TokenResponse>("/auth/register", { email, password, display_name }),
  refresh: () => http.post<TokenResponse>("/auth/refresh"),
  logout: () => http.post<void>("/auth/logout"),
  me: () => http.get<CurrentUser>("/auth/me"),
};

// ----- Project -----
export type Project = {
  id: string;
  organization_id: string;
  title: string;
  genre: string;
  target_word_count: number;
  target_chapter_count: number;
  current_word_count: number;
  completed_chapter_count: number;
  language: string;
  style: string;
  status: string;
  cover_url: string;
  tags: string[];
  target_reader: string;
};

export type ProjectCreate = {
  title: string;
  premise?: string;
  genre?: string;
  target_word_count?: number;
  target_chapter_count?: number;
  style?: string;
};

export type BibleSpec = {
  id: string;
  premise: string;
  theme: string;
  genre: string;
  tone: string;
  target_reader: string;
  narrative_pov: string;
  style_guide: string;
  constraints: string[];
};

export type BibleCharacter = {
  id: string;
  name: string;
  role: string;
  description: string;
  motivation: string;
  arc: string;
};

export type BibleWorldItem = {
  id: string;
  type: string;
  name: string;
  description: string;
  importance: string;
  is_hard_rule: boolean;
};

export type BiblePlotThread = {
  id: string;
  title: string;
  thread_type: string;
  description: string;
  status: string;
};

export type Bible = {
  project_id: string;
  project_status: string;
  spec: BibleSpec | null;
  characters: BibleCharacter[];
  world_items: BibleWorldItem[];
  plot_threads: BiblePlotThread[];
  latest_job: GenerationJob | null;
};

export type GenerateBiblePayload = {
  estimate_words?: number;
  topic?: string;
  force_regenerate?: boolean;
};

// 与 backend/app/schemas/story_generation.py::ChapterPlanItem 对齐
export type Chapter = {
  id: string;
  project_id: string;
  volume_id: string | null;
  chapter_index: number;
  title: string;
  summary: string;
  goal: string;
  conflict: string;
  ending_hook: string;
  status: string;
};

export type GenerateOutlinePayload = {
  // null/undefined 时由 activity 回落到 project.target_chapter_count 或 6
  target_chapters?: number | null;
  estimate_words?: number;
  force_regenerate?: boolean;
};

// 与 backend/app/schemas/story_generation.py::ScenePlanItem 对齐
export type Scene = {
  id: string;
  project_id: string;
  chapter_id: string;
  scene_index: number;
  title: string;
  time_marker: string;
  location: string;
  characters: string[];
  goal: string;
  conflict: string;
  emotion_start: string;
  emotion_end: string;
  reveal: string;
  hook: string;
  status: string;
};

export type GenerateScenePlanPayload = {
  scenes_per_chapter?: number;
  expected_words?: number;
  estimate_words?: number;
  force_regenerate?: boolean;
};

export type WriteScenePayload = {
  target_words?: number;
};

export const projectsApi = {
  list: () => http.get<Project[]>("/projects"),
  get: (id: string) => http.get<Project>(`/projects/${id}`),
  create: (payload: ProjectCreate) => http.post<Project>("/projects", payload),
  delete: (id: string) => http.delete<void>(`/projects/${id}`),
  getBible: (id: string) => http.get<Bible>(`/projects/${id}/bible`),
  generateBible: (id: string, payload: GenerateBiblePayload) =>
    http.post<GenerationJob>(`/projects/${id}/bible/generate`, payload),
  generateOutline: (id: string, payload: GenerateOutlinePayload = {}) =>
    http.post<GenerationJob>(`/projects/${id}/outline/generate`, payload),
  generateScenePlan: (
    projectId: string,
    chapterId: string,
    payload: GenerateScenePlanPayload = {},
  ) =>
    http.post<GenerationJob>(
      `/projects/${projectId}/chapters/${chapterId}/scenes/generate`,
      payload,
    ),
  writeScene: (
    projectId: string,
    sceneId: string,
    payload: WriteScenePayload = {},
  ) =>
    http.post<GenerationJob>(
      `/projects/${projectId}/scenes/${sceneId}/write`,
      payload,
    ),
  generateFullNovel: (id: string, estimate_words: number) =>
    http.post<GenerationJob>(`/projects/${id}/generate-full-novel`, { estimate_words }),
};

// ----- Generation Jobs -----
export type GenerationJob = {
  id: string;
  organization_id: string;
  user_id: string;
  project_id: string;
  job_type: string;
  status: string;
  priority: string;
  plan_code: string;
  reserved_quota: number;
  consumed_quota: number;
  workflow_id: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  // 用户提交时的原始参数；前端通过 input_payload.chapter_id 等
  // 在 jobs 列表里精确匹配某章/某 scene 的任务。
  input_payload?: Record<string, unknown> | null;
};

export const jobsApi = {
  list: () => http.get<GenerationJob[]>("/generation-jobs"),
  get: (id: string) => http.get<GenerationJob>(`/generation-jobs/${id}`),
  cancel: (id: string) => http.post<GenerationJob>(`/generation-jobs/${id}/cancel`),
};

// ----- Quota / Usage -----
export type QuotaBalance = {
  id: string;
  organization_id: string;
  quota_key: string;
  limit_value: number;
  used_value: number;
  reserved_value: number;
  period_start: string;
  period_end: string;
  reset_at: string;
};

export type UsageEvent = {
  id: string;
  organization_id: string;
  user_id: string;
  project_id: string | null;
  job_id: string | null;
  event_type: string;
  amount: number;
  unit: string;
  created_at: string;
};

export const quotaApi = {
  list: () => http.get<QuotaBalance[]>("/quotas"),
  usage: () => http.get<UsageEvent[]>("/usage"),
  entitlements: () =>
    http.get<{ organization_id: string; plan_code: string; entitlements: string[] }>(
      "/entitlements",
    ),
};

// ----- Billing -----
export type Plan = {
  id?: string;
  code: string;
  name: string;
  description: string;
  price_monthly: number;
  price_yearly?: number | null;
  currency?: string;
  status: string;
};

export const billingApi = {
  plans: () => http.get<Plan[]>("/billing/plans"),
  checkout: (plan_code: string) =>
    http.post<{ checkout_url: string }>("/billing/checkout-session", { plan_code }),
};

// ----- Organizations -----
export type Organization = {
  id: string;
  name: string;
  type: string;
  plan_code: string;
  status: string;
  owner_user_id: string;
};

export type Member = {
  id: string;
  organization_id: string;
  user_id: string;
  role: string;
  status: string;
};

export const organizationsApi = {
  mine: () => http.get<Organization[]>("/organizations"),
  current: () => http.get<Organization>("/organizations/current"),
  update: (payload: Partial<Pick<Organization, "name" | "plan_code" | "status">>) =>
    http.patch<Organization>("/organizations/current", payload),
  members: () => http.get<Member[]>("/organizations/current/members"),
  invite: (email: string, role: string) =>
    http.post<Member>("/organizations/current/members", { email, role }),
  removeMember: (id: string) =>
    http.delete<void>(`/organizations/current/members/${id}`),
};

// ----- Characters / Chapters / Scenes / WorldItems / Memory -----
export const charactersApi = {
  list: (projectId: string) =>
    http.get<unknown[]>(`/projects/${projectId}/characters`),
};
export const chaptersApi = {
  list: (projectId: string) =>
    http.get<Chapter[]>(`/projects/${projectId}/chapters`),
};
export const scenesApi = {
  list: (projectId: string, chapterId?: string) =>
    http.get<Scene[]>(`/projects/${projectId}/scenes`, { chapter_id: chapterId }),
};

// 与 backend/app/api/project_extra.py::DraftVersionResponse 对齐
export type DraftVersion = {
  id: string;
  organization_id: string;
  project_id: string;
  chapter_id: string | null;
  scene_id: string | null;
  version_type: string;
  content: string;
  word_count: number;
  status: string;
  parent_version_id: string | null;
  created_by: string;
};

export type DraftVersionCreate = {
  chapter_id?: string | null;
  scene_id?: string | null;
  version_type?: string;
  content?: string;
  word_count?: number;
  status?: string;
  parent_version_id?: string | null;
};

export const versionsApi = {
  // 按 scene_id 过滤；不传时返回项目全部 draft_versions。
  // base list 默认按 created_at desc 排序，所以第一个是最新。
  list: (projectId: string, params: { scene_id?: string; chapter_id?: string } = {}) =>
    http.get<DraftVersion[]>(`/projects/${projectId}/versions`, params),
  get: (projectId: string, versionId: string) =>
    http.get<DraftVersion>(`/projects/${projectId}/versions/${versionId}`),
  create: (projectId: string, payload: DraftVersionCreate) =>
    http.post<DraftVersion>(`/projects/${projectId}/versions`, payload),
};
export const worldItemsApi = {
  list: (projectId: string) =>
    http.get<unknown[]>(`/projects/${projectId}/world-items`),
};
export const memoryApi = {
  list: (projectId: string) =>
    http.get<unknown[]>(`/projects/${projectId}/memory`),
};
export const exportsApi = {
  list: (projectId: string) =>
    http.get<unknown[]>(`/projects/${projectId}/exports`),
  create: (projectId: string, export_type: string) =>
    http.post(`/projects/${projectId}/exports`, { export_type }),
};

// ----- Admin -----
export type ModelGatewaySettings = {
  mode: "mock" | "real";
  provider: "openai" | "anthropic";
  default_model: string;
  openai_base_url: string;
  openai_api_key_configured: boolean;
  anthropic_base_url: string;
  anthropic_api_key_configured: boolean;
  active_base_url: string;
  ready: boolean;
};

export type ModelGatewaySettingsUpdate = {
  mode: "mock" | "real";
  provider: "openai" | "anthropic";
  default_model: string;
  openai_base_url: string;
  openai_api_key?: string | null;
  anthropic_base_url: string;
  anthropic_api_key?: string | null;
};

export type AdminPlanFeature = {
  id?: string;
  feature_key: string;
  enabled: boolean;
  limit_value: number | null;
  limit_unit: string;
};

export type AdminPlan = Required<Pick<Plan, "id">> &
  Plan & {
    price_yearly: number | null;
    currency: string;
    features: AdminPlanFeature[];
  };

export type AdminPlanUpsert = {
  code: string;
  name: string;
  description: string;
  price_monthly: number;
  price_yearly: number | null;
  currency: string;
  status: string;
  features: AdminPlanFeature[];
};

export const adminApi = {
  users: () => http.get<unknown[]>("/admin/users"),
  organizations: () => http.get<unknown[]>("/admin/organizations"),
  jobs: () => http.get<unknown[]>("/admin/generation-jobs"),
  modelCalls: () => http.get<unknown[]>("/admin/model-calls"),
  auditLogs: () => http.get<unknown[]>("/admin/audit-logs"),
  contentReviews: () => http.get<unknown[]>("/admin/content-reviews"),
  plans: () => http.get<AdminPlan[]>("/admin/plans"),
  createPlan: (payload: AdminPlanUpsert) => http.post<AdminPlan>("/admin/plans", payload),
  updatePlan: (id: string, payload: AdminPlanUpsert) =>
    http.put<AdminPlan>(`/admin/plans/${id}`, payload),
  modelGatewaySettings: () =>
    http.get<ModelGatewaySettings>("/admin/settings/model-gateway"),
  updateModelGatewaySettings: (payload: ModelGatewaySettingsUpdate) =>
    http.put<ModelGatewaySettings>("/admin/settings/model-gateway", payload),
};
