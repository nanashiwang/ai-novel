export type CreativePrefs = {
  // 基础：默认展开
  topic: string;
  protagonist_archetype: string;
  target_reader: string;
  story_tone: string;
  forbidden_themes: string;
  // 高级：默认收起
  reference_works: string;
  pacing: string;
  ending_lean: string;
  automation_level: string;
  audit_strictness: string;
  temperature: number;
};

export const DEFAULT_PREFS: CreativePrefs = {
  topic: "",
  protagonist_archetype: "",
  target_reader: "",
  story_tone: "",
  forbidden_themes: "",
  reference_works: "",
  pacing: "",
  ending_lean: "",
  automation_level: "standard",
  audit_strictness: "standard",
  temperature: 0.7,
};

export function splitTags(value: string): string[] {
  return value
    .split(/[,，;；\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}
