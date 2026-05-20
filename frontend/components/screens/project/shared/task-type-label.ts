const TASK_TYPE_LABELS: Record<string, string> = {
  generate_bible: "故事圣经生成",
  generate_outline: "章节大纲生成",
  generate_scene_plan: "场景拆分",
  write_scene: "场景正文写作",
  audit_scene: "审稿",
  rewrite_scene: "重写",
  full_novel: "全书生成",
};

export function taskTypeLabel(jobType: string): string {
  return TASK_TYPE_LABELS[jobType] ?? jobType;
}
