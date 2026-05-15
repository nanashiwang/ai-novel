export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type WorkflowStepStatus = "pending" | "running" | "completed" | "failed";

export type WorkflowStep = {
  id: string;
  name: string;
  status: WorkflowStepStatus;
  durationMs?: number;
};

export type GenerationJob = {
  id: string;
  organizationId: string;
  projectId: string;
  title: string;
  taskType: "story_bible" | "outline" | "chapter" | "scene" | "review" | "rewrite" | "export";
  status: JobStatus;
  queue: "low" | "normal" | "high" | "internal";
  progress: number;
  reservedQuota: number;
  consumedQuota: number;
  releasedQuota: number;
  workflowRunId: string;
  currentStep: string;
  createdAt: string;
  updatedAt: string;
};

export type ModelCall = {
  id: string;
  organizationId: string;
  projectId?: string;
  generationJobId?: string;
  taskType: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
  status: "success" | "error";
  costUsd: number;
  promptPreview: string;
  responsePreview: string;
  createdAt: string;
};
