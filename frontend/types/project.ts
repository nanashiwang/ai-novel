export type ProjectStatus =
  | "created"
  | "bible_generating"
  | "bible_ready"
  | "outline_generating"
  | "outline_ready"
  | "drafting"
  | "auditing"
  | "rewriting"
  | "completed"
  | "exported";

export type ChapterStatus = "planned" | "scenes_planned" | "drafting" | "drafted" | "auditing" | "needs_rewrite" | "rewriting" | "finalized";
export type SceneStatus = "planned" | "writing" | "drafted" | "audited" | "rewritten" | "approved";

export type Project = {
  id: string;
  organizationId: string;
  title: string;
  genre: string;
  tags: string[];
  status: ProjectStatus;
  targetWordCount: number;
  currentWordCount: number;
  targetChapterCount: number;
  completedChapterCount: number;
  currentChapterIndex?: number;
  style: string;
  targetReader: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
};

export type NovelSpec = {
  id: string;
  organizationId: string;
  projectId: string;
  premise: string;
  theme: string;
  genre: string;
  tone: string;
  narrativePov: string;
  styleGuide: string;
  constraints: string[];
};

export type Chapter = {
  id: string;
  organizationId: string;
  projectId: string;
  volumeIndex: number;
  chapterIndex: number;
  title: string;
  summary: string;
  goal: string;
  conflict: string;
  endingHook: string;
  status: ChapterStatus;
  wordCount: number;
  progress: number;
  updatedAt: string;
};

export type Scene = {
  id: string;
  organizationId: string;
  projectId: string;
  chapterId: string;
  sceneIndex: number;
  title: string;
  timeMarker: string;
  location: string;
  characters: string[];
  goal: string;
  conflict: string;
  emotionStart: string;
  emotionEnd: string;
  status: SceneStatus;
  targetWords?: number;
  beatStart?: number | null;
  beatEnd?: number | null;
  beatGroupSummary?: string;
  budgetReason?: string;
  draftVersionId?: string;
  wordCount: number;
};

export type Character = {
  id: string;
  organizationId: string;
  projectId: string;
  name: string;
  role: string;
  archetype: string;
  status: string;
  currentGoal: string;
  secret: string;
  relationshipTags: string[];
};

export type WorldItem = {
  id: string;
  organizationId: string;
  projectId: string;
  type: "location" | "organization" | "rule" | "item" | "power";
  name: string;
  summary: string;
  references: string[];
};

export type ContinuityIssue = {
  id: string;
  organizationId: string;
  projectId: string;
  severity: "low" | "medium" | "high";
  type: "timeline" | "character" | "world" | "style" | "logic";
  title: string;
  location: string;
  status: "open" | "fixed" | "ignored";
  suggestion: string;
  createdAt: string;
};

export type ExportFile = {
  id: string;
  organizationId: string;
  projectId: string;
  format: "Markdown" | "TXT" | "DOCX" | "EPUB" | "PDF";
  fileName: string;
  source: "final_version" | "draft_version";
  size: string;
  status: "ready" | "generating" | "failed";
  createdAt: string;
};
