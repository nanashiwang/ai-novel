/**
 * 后端 API 客户端层，按资源分模块导出。
 *
 * 字段命名与后端 Pydantic schema 保持一致（snake_case）。
 * 上层组件直接使用此处定义的类型即可，无需手动定义 DTO。
 */
import { downloadBlob, http } from "./http";

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
  personality: string;
  motivation: string;
  secret: string;
  arc: string;
  relationships: Record<string, unknown>;
  current_state: Record<string, unknown>;
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

export type RevisionTargetType =
  | "project_settings"
  | "story_bible"
  | "character"
  | "world_item"
  | "plot_thread";

export type RevisionProposal = {
  id: string;
  session_id: string;
  project_id: string;
  target_type: RevisionTargetType;
  target_id: string | null;
  action: "update" | "create";
  title: string;
  patch: Record<string, unknown>;
  reason: string;
  impact: string[];
  status: string;
};

export type RevisionMessage = {
  id: string;
  session_id: string;
  role: "user" | "assistant" | string;
  content: string;
};

export type RevisionSession = {
  id: string;
  project_id: string;
  scope: string;
  title: string;
  status: string;
};

export type RevisionChatRequest = {
  message: string;
  session_id?: string | null;
  scope?: string;
  target_type?: RevisionTargetType | null;
  target_id?: string | null;
};

export type RevisionChatResponse = {
  session: RevisionSession;
  reply: string;
  messages: RevisionMessage[];
  proposals: RevisionProposal[];
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
  // 创作偏好：让 LLM prompt 含具体约束；留空则由真实模型按项目元数据发挥。
  protagonist_archetype?: string;
  reference_works?: string[];
  forbidden_themes?: string[];
  temperature?: number | null;
  // 高级偏好（仅在 prompt 拼接时生效，后端不强校验）
  target_reader?: string;
  story_tone?: string;
  pacing?: string;
  ending_lean?: string;
  automation_level?: string;
  audit_strictness?: string;
};

// 与 backend/app/api/projects.py::PreflightResponse 对齐
export type PreflightCheckItem = {
  label: string;
  level: "ok" | "warn" | "block";
  detail: string;
};
export type PreflightNextAction = {
  kind: string;
  label: string;
  href_suffix: string;
};
export type PreflightReport = {
  project_status: string;
  plan_code: string;
  quota_key: string;
  quota_limit: number;
  quota_used: number;
  quota_reserved: number;
  quota_available: number;
  estimate_words: number;
  target_chapter_count: number;
  is_long_novel: boolean;
  can_generate: boolean;
  checks: PreflightCheckItem[];
  next_action: PreflightNextAction | null;
};

export type StoryDirection = {
  name: string;
  summary: string;
  selling_points: string[];
  risk: string;
  recommended: boolean;
};
export type DirectionPreviewPayload = {
  topic?: string;
  protagonist_archetype?: string;
  reference_works?: string[];
  forbidden_themes?: string[];
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
  // null/undefined 时由 activity 回落到 project.target_chapter_count 或 6；服务端上限 200
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

export type AuditScenePayload = {
  estimate_words?: number;
};

export type RewriteScenePayload = {
  target_words?: number;
  estimate_words?: number;
};

// 与 backend/app/models/continuity_issue.py 对齐
export type ContinuityIssue = {
  id: string;
  organization_id: string;
  project_id: string;
  chapter_id: string | null;
  scene_id: string | null;
  issue_type: string;
  severity: string;
  description: string;
  suggested_fix: string;
  status: string;
  created_at?: string;
  updated_at?: string;
};

export const continuityIssuesApi = {
  list: (projectId: string) =>
    http.get<ContinuityIssue[]>(`/projects/${projectId}/continuity-issues`),
};

export const projectsApi = {
  list: () => http.get<Project[]>("/projects"),
  get: (id: string) => http.get<Project>(`/projects/${id}`),
  create: (payload: ProjectCreate) => http.post<Project>("/projects", payload),
  delete: (id: string) => http.delete<void>(`/projects/${id}`),
  getBible: (id: string) => http.get<Bible>(`/projects/${id}/bible`),
  preflight: (id: string, jobType: string = "generate_bible") =>
    http.get<PreflightReport>(`/projects/${id}/preflight`, { job_type: jobType }),
  previewDirections: (id: string, payload: DirectionPreviewPayload) =>
    http.post<{ directions: StoryDirection[] }>(
      `/projects/${id}/bible/preview-directions`,
      payload,
    ),
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
  auditScene: (
    projectId: string,
    sceneId: string,
    payload: AuditScenePayload = {},
  ) =>
    http.post<GenerationJob>(
      `/projects/${projectId}/scenes/${sceneId}/audit`,
      payload,
    ),
  rewriteScene: (
    projectId: string,
    sceneId: string,
    payload: RewriteScenePayload = {},
  ) =>
    http.post<GenerationJob>(
      `/projects/${projectId}/scenes/${sceneId}/rewrite`,
      payload,
    ),
  generateFullNovel: (id: string, estimate_words: number) =>
    http.post<GenerationJob>(`/projects/${id}/generate-full-novel`, { estimate_words }),
};

export const revisionApi = {
  chat: (projectId: string, payload: RevisionChatRequest) =>
    http.post<RevisionChatResponse>(`/projects/${projectId}/revisions/chat`, payload),
  getSession: (projectId: string, sessionId: string) =>
    http.get<RevisionChatResponse>(`/projects/${projectId}/revisions/sessions/${sessionId}`),
  applyProposal: (projectId: string, proposalId: string) =>
    http.post<{ proposal: RevisionProposal; applied_change_id: string }>(
      `/projects/${projectId}/revisions/proposals/${proposalId}/apply`,
    ),
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
  // activity 写入的执行结果；scene_writing 任务会包含 context_summary 等
  // ContextBuilder Inspector 所需信息。
  output_payload?: Record<string, unknown> | null;
};

export const jobsApi = {
  list: () => http.get<GenerationJob[]>("/generation-jobs"),
  get: (id: string) => http.get<GenerationJob>(`/generation-jobs/${id}`),
  cancel: (id: string) => http.post<GenerationJob>(`/generation-jobs/${id}/cancel`),
  retry: (id: string) => http.post<GenerationJob>(`/generation-jobs/${id}/retry`),
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
export type NovelSpecPayload = {
  premise?: string;
  theme?: string;
  genre?: string;
  tone?: string;
  target_reader?: string;
  narrative_pov?: string;
  style_guide?: string;
  constraints?: string[];
  continuity_rules?: string[];
};

export type Character = {
  id: string;
  organization_id: string;
  project_id: string;
  name: string;
  role: string;
  description: string;
  personality?: string;
  motivation: string;
  secret?: string;
  arc: string;
  relationships?: Record<string, unknown>;
  current_state?: Record<string, unknown>;
};

export type CharacterPayload = {
  name: string;
  role?: string;
  description?: string;
  personality?: string;
  motivation?: string;
  secret?: string;
  arc?: string;
  relationships?: Record<string, unknown>;
  current_state?: Record<string, unknown>;
};

export type WorldItem = {
  id: string;
  organization_id: string;
  project_id: string;
  type: string;
  name: string;
  description: string;
  importance?: string;
  is_hard_rule?: boolean;
  attributes?: Record<string, unknown>;
};

export type WorldItemPayload = {
  type: string;
  name: string;
  description?: string;
  importance?: string;
  is_hard_rule?: boolean;
  attributes?: Record<string, unknown>;
};

export type PlotThread = {
  id: string;
  organization_id: string;
  project_id: string;
  title: string;
  thread_type: string;
  description: string;
  status: string;
  related_characters: string[];
};

export type PlotThreadPayload = {
  title: string;
  thread_type?: string;
  description?: string;
  status?: string;
  related_characters?: string[];
};

export const charactersApi = {
  list: (projectId: string) =>
    http.get<Character[]>(`/projects/${projectId}/characters`),
  create: (projectId: string, payload: CharacterPayload) =>
    http.post<Character>(`/projects/${projectId}/characters`, payload),
  update: (projectId: string, characterId: string, payload: Partial<CharacterPayload>) =>
    http.patch<Character>(`/projects/${projectId}/characters/${characterId}`, payload),
  remove: (projectId: string, characterId: string) =>
    http.delete<void>(`/projects/${projectId}/characters/${characterId}`),
};
export const chaptersApi = {
  list: (projectId: string) =>
    http.get<Chapter[]>(`/projects/${projectId}/chapters`),
};
export const scenesApi = {
  list: (projectId: string, chapterId?: string) =>
    http.get<Scene[]>(`/projects/${projectId}/scenes`, { chapter_id: chapterId }),
};

export const specApi = {
  get: (projectId: string) =>
    http.get<NovelSpecPayload & { id: string; project_id: string }>(
      `/projects/${projectId}/spec`,
    ),
  upsert: (projectId: string, payload: NovelSpecPayload) =>
    http.put<NovelSpecPayload & { id: string; project_id: string }>(
      `/projects/${projectId}/spec`,
      payload,
    ),
};

// 与 backend/app/api/project_extra.py::DraftVersionResponse 对齐
/** content 字段的序列化格式。'text' = 历史纯文本，'markdown' = 新写入路径。 */
export type ContentFormat = "text" | "markdown";

export type DraftVersion = {
  id: string;
  organization_id: string;
  project_id: string;
  chapter_id: string | null;
  scene_id: string | null;
  version_type: string;
  content: string;
  content_format: ContentFormat;
  word_count: number;
  status: string;
  parent_version_id: string | null;
  created_by: string;
  created_at?: string;
  updated_at?: string;
};

export type DraftVersionCreate = {
  chapter_id?: string | null;
  scene_id?: string | null;
  version_type?: string;
  content?: string;
  content_format?: ContentFormat;
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
  delete: (projectId: string, versionId: string) =>
    http.delete<void>(`/projects/${projectId}/versions/${versionId}`),
};
export const worldItemsApi = {
  list: (projectId: string) =>
    http.get<WorldItem[]>(`/projects/${projectId}/world-items`),
  create: (projectId: string, payload: WorldItemPayload) =>
    http.post<WorldItem>(`/projects/${projectId}/world-items`, payload),
  update: (projectId: string, itemId: string, payload: Partial<WorldItemPayload>) =>
    http.patch<WorldItem>(`/projects/${projectId}/world-items/${itemId}`, payload),
  remove: (projectId: string, itemId: string) =>
    http.delete<void>(`/projects/${projectId}/world-items/${itemId}`),
};
export const plotThreadsApi = {
  list: (projectId: string) =>
    http.get<PlotThread[]>(`/projects/${projectId}/plot-threads`),
  create: (projectId: string, payload: PlotThreadPayload) =>
    http.post<PlotThread>(`/projects/${projectId}/plot-threads`, payload),
  update: (projectId: string, threadId: string, payload: Partial<PlotThreadPayload>) =>
    http.patch<PlotThread>(`/projects/${projectId}/plot-threads/${threadId}`, payload),
  remove: (projectId: string, threadId: string) =>
    http.delete<void>(`/projects/${projectId}/plot-threads/${threadId}`),
};
export const memoryApi = {
  list: (projectId: string) =>
    http.get<unknown[]>(`/projects/${projectId}/memory`),
};
// 与 backend/app/models/export_file.py + project_extra.ExportResponse 对齐
export type ExportFile = {
  id: string;
  organization_id: string;
  project_id: string;
  export_type: string;
  file_url: string;
  status: string;
  created_by: string;
  file_size: number;
  created_at?: string;
};

export const exportsApi = {
  list: (projectId: string) =>
    http.get<ExportFile[]>(`/projects/${projectId}/exports`),
  create: (projectId: string, export_type: string) =>
    http.post<ExportFile>(`/projects/${projectId}/exports`, { export_type }),
  // 触发浏览器下载：拿 Blob → 创建临时 URL → 模拟点击 → 释放
  download: async (projectId: string, exportId: string) => {
    const { blob, filename } = await downloadBlob(
      `/projects/${projectId}/exports/${exportId}/download`,
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename ?? `${exportId}.bin`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 0);
  },
};

// ----- Admin -----
export type ModelGatewaySettings = {
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
    organization_count?: number;
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

export type AdminJobsFilter = {
  organization_id?: string;
  project_id?: string;
  job_type?: string;
  status?: string;
  limit?: number;
};

export type AdminModelCallsFilter = {
  organization_id?: string;
  project_id?: string;
  job_id?: string;
  task_type?: string;
  limit?: number;
};

export const adminApi = {
  users: () => http.get<unknown[]>("/admin/users"),
  user: (userId: string) => http.get<AdminUserDetail>(`/admin/users/${userId}`),
  updateUser: (userId: string, payload: AdminUserUpdate) =>
    http.patch<AdminUser>(`/admin/users/${userId}`, payload),
  resetUserPassword: (userId: string) =>
    http.post<{ temp_password: string; note: string }>(
      `/admin/users/${userId}/reset-password`,
    ),
  organizations: () => http.get<unknown[]>("/admin/organizations"),
  updateOrganization: (orgId: string, payload: AdminOrgUpdate) =>
    http.patch<{ id: string; plan_code: string; status: string }>(
      `/admin/organizations/${orgId}`,
      payload,
    ),
  organizationQuotas: (orgId: string) =>
    http.get<AdminQuotaBalance[]>(`/admin/organizations/${orgId}/quotas`),
  adjustOrganizationQuota: (orgId: string, payload: AdjustQuotaPayload) =>
    http.patch<{ status: string; limit_value: number }>(
      `/admin/organizations/${orgId}/quota`,
      payload,
    ),
  quotaBalances: (filter: { organization_id?: string; quota_key?: string } = {}) =>
    http.get<AdminQuotaBalance[]>("/admin/quota-balances", filter),
  quotaKeys: () =>
    http.get<{ feature_key: string; used_in_plans: number }[]>("/admin/quota-keys"),
  jobs: (filter: AdminJobsFilter = {}) =>
    http.get<GenerationJob[]>("/admin/generation-jobs", filter),
  cancelJob: (jobId: string) =>
    http.post<GenerationJob>(`/admin/generation-jobs/${jobId}/cancel`),
  modelCalls: (filter: AdminModelCallsFilter = {}) =>
    http.get<unknown[]>("/admin/model-calls", filter),
  auditLogs: () => http.get<unknown[]>("/admin/audit-logs"),
  contentReviews: () => http.get<unknown[]>("/admin/content-reviews"),
  plans: () => http.get<AdminPlan[]>("/admin/plans"),
  createPlan: (payload: AdminPlanUpsert) => http.post<AdminPlan>("/admin/plans", payload),
  updatePlan: (id: string, payload: AdminPlanUpsert) =>
    http.put<AdminPlan>(`/admin/plans/${id}`, payload),
  deletePlan: (id: string) => http.delete<void>(`/admin/plans/${id}`),
  modelGatewaySettings: () =>
    http.get<ModelGatewaySettings>("/admin/settings/model-gateway"),
  updateModelGatewaySettings: (payload: ModelGatewaySettingsUpdate) =>
    http.put<ModelGatewaySettings>("/admin/settings/model-gateway", payload),
  testModelGateway: (payload: ModelGatewayTestPayload) =>
    http.post<ModelGatewayTestResult>("/admin/settings/model-gateway/test", payload),
};

export type ModelGatewayTestPayload = {
  provider?: "openai" | "anthropic";
  default_model?: string;
  openai_base_url?: string;
  openai_api_key?: string | null;
  anthropic_base_url?: string;
  anthropic_api_key?: string | null;
};

export type ModelGatewayTestResult = {
  ok: boolean;
  provider: string;
  default_model: string;
  base_url: string;
  latency_ms: number;
  sample: string;
  error: string;
};

export type AdminUser = {
  id: string;
  email: string;
  display_name: string;
  platform_role: string;
  status: string;
};

export type AdminUserOrgInfo = {
  organization_id: string;
  organization_name: string;
  plan_code: string;
  role: string;
  member_status: string;
};

export type AdminUserDetail = AdminUser & {
  is_platform_staff: boolean;
  organizations: AdminUserOrgInfo[];
};

export type AdminUserUpdate = {
  display_name?: string;
  platform_role?: string;
  status?: string;
  reason?: string;
};

export type AdminOrgUpdate = {
  plan_code?: string;
  status?: string;
  reason?: string;
};

export type AdminQuotaBalance = {
  id: string;
  organization_id: string;
  quota_key: string;
  limit_value: number;
  used_value: number;
  reserved_value: number;
  period_start: string | null;
  period_end: string | null;
};

export type AdjustQuotaPayload = {
  quota_key: string;
  delta: number;
  reason?: string;
};
