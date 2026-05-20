/**
 * Admin 后台本地运行时形状声明。
 *
 * 这些表的 API 当前返回 unknown[]，前端在调用点就近 narrow；
 * 待后端补全 Pydantic schema 后应迁移到 lib/api.ts 统一管理。
 */

export type AdminOrg = {
  id: string;
  name: string;
  type: string;
  plan_code: string;
  status: string;
  owner_user_id: string;
};

export type AdminModelCall = {
  id: string;
  organization_id: string;
  project_id: string | null;
  job_id: string | null;
  task_type: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  status: string;
  created_at: string;
};

export type AdminAuditLog = {
  id: string;
  organization_id: string;
  actor_user_id: string;
  action: string;
  target_type: string;
  target_id: string;
  created_at: string;
};

export type AdminContentReview = {
  id: string;
  organization_id: string;
  project_id: string;
  issue_type: string;
  severity: string;
  description: string;
  status: string;
  created_at: string;
};
