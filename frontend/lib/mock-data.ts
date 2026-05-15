import type {
  AuditLog,
  Character,
  Chapter,
  ContinuityIssue,
  ExportFile,
  GenerationJob,
  ModelCall,
  MockUser,
  NovelSpec,
  Organization,
  OrganizationMember,
  Plan,
  PlanFeature,
  Project,
  QuotaBalance,
  QuotaReservation,
  Scene,
  UsageEvent,
  WorkflowStep,
  WorldItem,
} from "@/types";

export const mockNormalUser: MockUser = {
  id: "user_writer",
  name: "玄夜",
  email: "writer@example.com",
  platformRole: "user",
  organizationRole: "owner",
  status: "active",
  currentOrganizationId: "org_personal",
  organizationName: "personal-workspace",
  planCode: "Pro",
};

export const mockAdminUser: MockUser = {
  id: "user_admin",
  name: "Admin",
  email: "admin@novelflow.ai",
  platformRole: "super_admin",
  organizationRole: "owner",
  status: "active",
  currentOrganizationId: "org_personal",
  organizationName: "personal-workspace",
  planCode: "Pro",
};

export const organizations: Organization[] = [
  { id: "org_personal", name: "personal-workspace", ownerUserId: "user_writer", planCode: "Pro", status: "active", createdAt: "2026-01-16T10:00:00Z" },
  { id: "org_moon", name: "月见内容工作室", ownerUserId: "user_editor", planCode: "Team", status: "active", createdAt: "2025-12-08T10:00:00Z" },
  { id: "org_archive", name: "星海档案社", ownerUserId: "user_admin", planCode: "Enterprise", status: "trialing", createdAt: "2025-10-21T10:00:00Z" },
];

export const members: OrganizationMember[] = [
  { id: "mem_1", organizationId: "org_personal", userId: "user_writer", role: "owner", status: "active", joinedAt: "2026-01-16T10:00:00Z" },
  { id: "mem_2", organizationId: "org_personal", userId: "user_admin", role: "owner", status: "active", joinedAt: "2026-01-16T10:00:00Z" },
  { id: "mem_3", organizationId: "org_moon", userId: "user_editor", role: "editor", status: "active", joinedAt: "2026-02-10T10:00:00Z" },
];

export const plans: Plan[] = [
  { code: "Free", name: "Free", description: "体验故事圣经与短篇生成", priceMonthly: 0, status: "active", queuePriority: "low", maxConcurrentJobs: 1, targetUser: "个人试用" },
  { code: "Starter", name: "Starter", description: "适合轻量连载作者", priceMonthly: 49, priceYearly: 490, status: "active", queuePriority: "normal", maxConcurrentJobs: 2, targetUser: "单人作者" },
  { code: "Pro", name: "Pro", description: "长篇小说自动生产与审稿", priceMonthly: 129, priceYearly: 1290, status: "active", queuePriority: "high", maxConcurrentJobs: 3, targetUser: "专业作者" },
  { code: "Team", name: "Team", description: "多人协作、API Key 与高级审核", priceMonthly: 399, priceYearly: 3990, status: "active", queuePriority: "enterprise", maxConcurrentJobs: 8, targetUser: "内容团队" },
  { code: "Enterprise", name: "Enterprise", description: "专属队列、合同额度和审计导出", priceMonthly: 0, status: "active", queuePriority: "enterprise", maxConcurrentJobs: 20, targetUser: "企业客户" },
];

export const planFeatures: PlanFeature[] = [
  { id: "pf_free_words", planCode: "Free", featureKey: "monthly_generated_words", featureName: "月生成字数", enabled: true, limitValue: 50000, limitUnit: "words", description: "包含故事圣经、大纲和正文生成" },
  { id: "pf_pro_words", planCode: "Pro", featureKey: "monthly_generated_words", featureName: "月生成字数", enabled: true, limitValue: 1000000, limitUnit: "words", description: "支持长篇项目连续生成" },
  { id: "pf_pro_review", planCode: "Pro", featureKey: "review_engine", featureName: "自动审稿", enabled: true, limitValue: 300, limitUnit: "times", description: "连续性、人物、世界观、风格审稿" },
  { id: "pf_pro_export", planCode: "Pro", featureKey: "export_formats", featureName: "导出格式", enabled: true, limitValue: 5, limitUnit: "formats", description: "Markdown / TXT / DOCX / EPUB / PDF" },
  { id: "pf_team_api", planCode: "Team", featureKey: "api_keys", featureName: "API Key", enabled: true, limitValue: 10, limitUnit: "times", description: "团队自动化和外部系统集成" },
  { id: "pf_ent_queue", planCode: "Enterprise", featureKey: "dedicated_queue", featureName: "专属任务队列", enabled: true, limitValue: "unlimited", limitUnit: "boolean", description: "企业专属优先级与 SLA" },
];

export const quotas: QuotaBalance[] = [
  { id: "quota_words", organizationId: "org_personal", quotaKey: "monthly_generated_words", label: "月生成字数", periodStart: "2026-05-01", periodEnd: "2026-05-31", limitValue: 1000000, usedValue: 682450, reservedValue: 42000, resetAt: "2026-06-01" },
  { id: "quota_review", organizationId: "org_personal", quotaKey: "monthly_review_count", label: "自动审稿次数", periodStart: "2026-05-01", periodEnd: "2026-05-31", limitValue: 300, usedValue: 183, reservedValue: 6, resetAt: "2026-06-01" },
  { id: "quota_rewrite", organizationId: "org_personal", quotaKey: "monthly_rewrite_count", label: "局部重写次数", periodStart: "2026-05-01", periodEnd: "2026-05-31", limitValue: 180, usedValue: 73, reservedValue: 2, resetAt: "2026-06-01" },
  { id: "quota_concurrent", organizationId: "org_personal", quotaKey: "concurrent_jobs", label: "并发任务", periodStart: "2026-05-01", periodEnd: "2026-05-31", limitValue: 3, usedValue: 2, reservedValue: 1, resetAt: "2026-06-01" },
];

export const projects: Project[] = [
  { id: "demo-project", organizationId: "org_personal", title: "雾都归档人", genre: "悬疑 · 都市", tags: ["档案馆", "失忆", "双线叙事"], status: "drafting", targetWordCount: 300000, currentWordCount: 268450, targetChapterCount: 48, completedChapterCount: 23, currentChapterIndex: 13, style: "冷峻克制，细节密集", targetReader: "偏好都市悬疑和反转叙事的读者", createdBy: "user_writer", createdAt: "2026-03-02T10:00:00Z", updatedAt: "2026-05-15T14:20:00Z" },
  { id: "star-king", organizationId: "org_personal", title: "星海失落王座", genre: "科幻 · 史诗", tags: ["舰队", "王座", "AI 叛乱"], status: "outline_ready", targetWordCount: 260000, currentWordCount: 193200, targetChapterCount: 36, completedChapterCount: 12, currentChapterIndex: 2, style: "宏大史诗，群像推进", targetReader: "科幻战争读者", createdBy: "user_writer", createdAt: "2026-02-18T10:00:00Z", updatedAt: "2026-05-14T11:10:00Z" },
  { id: "night-rail", organizationId: "org_personal", title: "长安夜行录", genre: "古风 · 传奇", tags: ["夜巡", "异闻", "权谋"], status: "auditing", targetWordCount: 220000, currentWordCount: 156780, targetChapterCount: 30, completedChapterCount: 18, style: "古雅但节奏紧凑", targetReader: "古风悬疑读者", createdBy: "user_writer", createdAt: "2026-01-22T10:00:00Z", updatedAt: "2026-05-13T19:30:00Z" },
  { id: "black-tower", organizationId: "org_personal", title: "黑塔继承者", genre: "奇幻 · 冒险", tags: ["黑塔", "继承试炼"], status: "bible_ready", targetWordCount: 180000, currentWordCount: 0, targetChapterCount: 24, completedChapterCount: 0, style: "黑暗奇幻，强设定", targetReader: "奇幻冒险读者", createdBy: "user_writer", createdAt: "2026-04-11T10:00:00Z", updatedAt: "2026-05-12T09:00:00Z" },
  { id: "river-rain", organizationId: "org_personal", title: "江湖旧雨", genre: "武侠 · 江湖", tags: ["旧案", "师门", "重逢"], status: "completed", targetWordCount: 300000, currentWordCount: 312600, targetChapterCount: 48, completedChapterCount: 48, style: "温润江湖，余味悠长", targetReader: "传统武侠读者", createdBy: "user_writer", createdAt: "2025-11-01T10:00:00Z", updatedAt: "2026-05-10T08:00:00Z" },
];

export const novelSpecs: NovelSpec[] = [
  {
    id: "spec_demo",
    organizationId: "org_personal",
    projectId: "demo-project",
    premise: "失忆档案修复师在雾都地下库房中发现自己被抹除的家族案卷。",
    theme: "记忆、责任与被选择的真相。",
    genre: "都市悬疑",
    tone: "冷峻、潮湿、克制，保留轻微超现实感。",
    narrativePov: "第三人称有限视角，偶尔插入档案摘录。",
    styleGuide: "句式短促，重视物证细节和空间压迫感，反转前不泄露人物真实动机。",
    constraints: ["不得直接揭示归档计划主谋", "每章至少保留一处可回收伏笔", "人物记忆变化需写入 Memory Engine"],
  },
];

export const chapters: Chapter[] = [
  { id: "ch_11", organizationId: "org_personal", projectId: "demo-project", volumeIndex: 1, chapterIndex: 11, title: "迷雾中的信件", summary: "陆沉舟收到来自旧档案馆的匿名信。", goal: "引出地下库房入口", conflict: "信件内容和官方档案互相矛盾", endingHook: "信封背面出现他父亲的旧签名", status: "finalized", wordCount: 6200, progress: 100, updatedAt: "2026-05-12T08:20:00Z" },
  { id: "ch_12", organizationId: "org_personal", projectId: "demo-project", volumeIndex: 1, chapterIndex: 12, title: "档案馆的低语", summary: "苏晚协助陆沉舟解读禁阅索引。", goal: "确认档案馆存在被人为抹除的层级", conflict: "苏晚隐瞒了她与馆长的关系", endingHook: "禁阅索引自动补全了陆沉舟的名字", status: "drafted", wordCount: 6900, progress: 100, updatedAt: "2026-05-13T10:20:00Z" },
  { id: "ch_13", organizationId: "org_personal", projectId: "demo-project", volumeIndex: 1, chapterIndex: 13, title: "地下库房的秘密", summary: "二人进入地下库房，发现家族案卷残片。", goal: "取得第一份归档残片", conflict: "地下守门人启动清除协议", endingHook: "残片显示陆沉舟曾经亲手签署归档命令", status: "drafting", wordCount: 2158, progress: 40, updatedAt: "2026-05-15T14:20:00Z" },
  { id: "ch_14", organizationId: "org_personal", projectId: "demo-project", volumeIndex: 1, chapterIndex: 14, title: "失踪的记录", summary: "追查被调包的第 13 号卷宗。", goal: "定位失踪记录", conflict: "监控证词和人物记忆冲突", endingHook: "黑影出现在档案馆旧楼", status: "planned", wordCount: 0, progress: 0, updatedAt: "2026-05-15T08:00:00Z" },
];

export const scenes: Scene[] = [
  { id: "scene_13_1", organizationId: "org_personal", projectId: "demo-project", chapterId: "ch_13", sceneIndex: 1, title: "夜探档案馆", timeMarker: "午夜 00:42", location: "雾都旧档案馆", characters: ["陆沉舟", "苏晚"], goal: "潜入封存区", conflict: "警报系统识别到陆沉舟旧权限", emotionStart: "警觉", emotionEnd: "不安", status: "approved", draftVersionId: "dv_131", wordCount: 2480 },
  { id: "scene_13_2", organizationId: "org_personal", projectId: "demo-project", chapterId: "ch_13", sceneIndex: 2, title: "地下库房", timeMarker: "午夜 01:18", location: "地下库房 B7", characters: ["陆沉舟", "苏晚"], goal: "打开编号 713 的铁盒", conflict: "铁盒锁孔要求被删除的家族密钥", emotionStart: "犹疑", emotionEnd: "震惊", status: "writing", draftVersionId: "dv_132", wordCount: 2158 },
  { id: "scene_13_3", organizationId: "org_personal", projectId: "demo-project", chapterId: "ch_13", sceneIndex: 3, title: "尘封的箱子", timeMarker: "午夜 01:32", location: "地下库房 B7", characters: ["陆沉舟"], goal: "读取残片", conflict: "残片内容显示他曾主动删除证据", emotionStart: "期待", emotionEnd: "恐惧", status: "planned", wordCount: 0 },
  { id: "scene_13_4", organizationId: "org_personal", projectId: "demo-project", chapterId: "ch_13", sceneIndex: 4, title: "异动", timeMarker: "午夜 01:40", location: "地下库房 B7", characters: ["陆沉舟", "苏晚", "守门人"], goal: "逃离清除协议", conflict: "守门人只响应陆家血脉指令", emotionStart: "紧张", emotionEnd: "失控", status: "planned", wordCount: 0 },
  { id: "scene_13_5", organizationId: "org_personal", projectId: "demo-project", chapterId: "ch_13", sceneIndex: 5, title: "意外来客", timeMarker: "午夜 01:46", location: "地下库房入口", characters: ["陆沉舟", "苏晚", "馆长"], goal: "隐藏残片", conflict: "馆长提前知道二人的行动", emotionStart: "慌乱", emotionEnd: "悬疑", status: "planned", wordCount: 0 },
];

export const editorDraft = `地下库房比想象中更深。\n\n阶梯尽头是一扇厚重的铁门，表面布满锈斑，锁孔处嵌着一枚古老的徽记，像是某个早已被遗忘的家族印章。\n\n陆沉舟的手电光掠过墙壁，两侧的书架从地面延伸到天花板，上面密密麻麻放满了档案盒。空气里弥漫着纸张、灰尘和一种潮湿的霉味。\n\n“这里……就是父亲说的地方？”\n\n苏晚轻声问，声音在空旷的库房里显得格外清晰。\n\n陆沉舟没有回答。他走向书架，手指划过一排排编号，最终停在最底层的一个铁盒前。盒面刻着一行小字：禁启，涉案传承物。\n\n他皱眉看向苏晚：“你确定要打开？”\n\n苏晚点头：“如果这里记录的是我们家族被抹去的真相，那只能现在。”\n\n陆沉舟深吸一口气，插入钥匙，轻轻转动。\n\n咔哒——\n\n锁开了。`;

export const characters: Character[] = [
  { id: "char_lu", organizationId: "org_personal", projectId: "demo-project", name: "陆沉舟", role: "主角", archetype: "失忆档案修复师", status: "冷静 / 谨慎 / 好奇", currentGoal: "寻找父亲留下的真相", secret: "曾参与归档计划初版签署", relationshipTags: ["苏晚：盟友", "馆长：旧识", "守门人：血脉绑定"] },
  { id: "char_su", organizationId: "org_personal", projectId: "demo-project", name: "苏晚", role: "女主", archetype: "调查记者", status: "警觉 / 坚定", currentGoal: "协助陆沉舟揭开秘密", secret: "她与馆长有亲属关系", relationshipTags: ["陆沉舟：互信建立中", "馆长：隐秘血缘"] },
  { id: "char_curator", organizationId: "org_personal", projectId: "demo-project", name: "沈馆长", role: "关键阻力", archetype: "守密人", status: "温和 / 控制欲强", currentGoal: "维持归档秩序", secret: "曾亲自执行一次记忆清除", relationshipTags: ["苏晚：家族关系", "陆沉舟：监视对象"] },
];

export const worldItems: WorldItem[] = [
  { id: "world_1", organizationId: "org_personal", projectId: "demo-project", type: "location", name: "雾都旧档案馆", summary: "城市地下记忆网络的入口，负责保存被官方删除的案件副本。", references: ["第 11 章", "第 13 章"] },
  { id: "world_2", organizationId: "org_personal", projectId: "demo-project", type: "rule", name: "归档计划", summary: "可将重大事件从公共记忆中抹除，但会在地下库房保留一份物证残影。", references: ["故事圣经", "第 12 章"] },
  { id: "world_3", organizationId: "org_personal", projectId: "demo-project", type: "item", name: "713 铁盒", summary: "需要陆家密钥开启，盒内保存家族案卷残片。", references: ["第 13 章 场景 2"] },
  { id: "world_4", organizationId: "org_personal", projectId: "demo-project", type: "organization", name: "档案委员会", summary: "负责维护城市记忆秩序的半公开组织。", references: ["第 8 章", "第 14 章"] },
];

export const issues: ContinuityIssue[] = [
  { id: "issue_1", organizationId: "org_personal", projectId: "demo-project", severity: "high", type: "timeline", title: "时间线冲突：第24章与第18章事件时间重叠", location: "长安夜行录 · 第24章", status: "open", suggestion: "将第 24 章夜巡时间后移 1 天，或调整第 18 章回忆顺序。", createdAt: "2026-05-15T09:01:00Z" },
  { id: "issue_2", organizationId: "org_personal", projectId: "demo-project", severity: "medium", type: "character", title: "角色设定不一致：李玄在第12章使用了不属于其势力的称谓", location: "长安夜行录 · 第12章", status: "open", suggestion: "替换称谓，并在人物状态里记录其真实阵营。", createdAt: "2026-05-15T08:41:00Z" },
  { id: "issue_3", organizationId: "org_personal", projectId: "demo-project", severity: "low", type: "style", title: "用词建议：缓缓地重复出现 6 次", location: "雾都归档人 · 第9章", status: "fixed", suggestion: "替换 4 处重复副词，保留节奏需要的 2 处。", createdAt: "2026-05-14T12:12:00Z" },
];

export const jobs: GenerationJob[] = [
  { id: "job_scene_13_2", organizationId: "org_personal", projectId: "demo-project", title: "第13章：地下库房的秘密 / 场景2：地下库房", taskType: "scene", status: "running", queue: "high", progress: 72, reservedQuota: 5000, consumedQuota: 4532, releasedQuota: 468, workflowRunId: "wf-scene-20260515-132", currentStep: "生成正文", createdAt: "2026-05-15T14:08:00Z", updatedAt: "2026-05-15T14:12:00Z" },
  { id: "job_outline_star", organizationId: "org_personal", projectId: "star-king", title: "第2卷大纲：星海失落王座", taskType: "outline", status: "queued", queue: "normal", progress: 40, reservedQuota: 12000, consumedQuota: 0, releasedQuota: 0, workflowRunId: "wf-outline-20260515-star", currentStep: "等待队列", createdAt: "2026-05-15T13:58:00Z", updatedAt: "2026-05-15T13:58:00Z" },
  { id: "job_review_night", organizationId: "org_personal", projectId: "night-rail", title: "第24章审稿：长安夜行录", taskType: "review", status: "failed", queue: "normal", progress: 88, reservedQuota: 3000, consumedQuota: 2120, releasedQuota: 880, workflowRunId: "wf-review-20260515-night", currentStep: "连续性审稿", createdAt: "2026-05-15T13:02:00Z", updatedAt: "2026-05-15T13:18:00Z" },
  { id: "job_export_river", organizationId: "org_personal", projectId: "river-rain", title: "导出 final 版本：江湖旧雨", taskType: "export", status: "succeeded", queue: "normal", progress: 100, reservedQuota: 1, consumedQuota: 1, releasedQuota: 0, workflowRunId: "wf-export-20260514-river", currentStep: "已完成", createdAt: "2026-05-14T15:00:00Z", updatedAt: "2026-05-14T15:04:00Z" },
];

export const workflowSteps: WorkflowStep[] = [
  { id: "wf_1", name: "场景构建", status: "completed", durationMs: 1800 },
  { id: "wf_2", name: "召回记忆", status: "completed", durationMs: 1400 },
  { id: "wf_3", name: "生成正文", status: "running", durationMs: 28000 },
  { id: "wf_4", name: "内容审稿", status: "pending" },
  { id: "wf_5", name: "局部重写", status: "pending" },
  { id: "wf_6", name: "质量评估", status: "pending" },
];

export const reservations: QuotaReservation[] = [
  { id: "res_1", organizationId: "org_personal", generationJobId: "job_scene_13_2", quotaKey: "monthly_generated_words", reservedAmount: 5000, consumedAmount: 4532, status: "reserved", createdAt: "2026-05-15T14:08:00Z", updatedAt: "2026-05-15T14:12:00Z" },
  { id: "res_2", organizationId: "org_personal", generationJobId: "job_review_night", quotaKey: "monthly_review_count", reservedAmount: 1, consumedAmount: 1, status: "settled", createdAt: "2026-05-15T13:02:00Z", updatedAt: "2026-05-15T13:18:00Z" },
];

export const modelCalls: ModelCall[] = [
  { id: "mc_1", organizationId: "org_personal", projectId: "demo-project", generationJobId: "job_scene_13_2", taskType: "scene_context", model: "gpt-4o", inputTokens: 128000, outputTokens: 1800, latencyMs: 9120, status: "success", costUsd: 1.83, promptPreview: "根据故事圣经、人物状态和地下库房规则构建第13章场景2上下文...", responsePreview: "本场景应保持冷峻悬疑，重点召回陆家密钥、713 铁盒和苏晚隐瞒关系...", createdAt: "2026-05-15T14:08:30Z" },
  { id: "mc_2", organizationId: "org_personal", projectId: "demo-project", generationJobId: "job_scene_13_2", taskType: "scene_draft", model: "gpt-4o", inputTokens: 131200, outputTokens: 4532, latencyMs: 28000, status: "success", costUsd: 3.42, promptPreview: "请以 scene 为最小生成单位，生成第13章场景2 正文，目标 3000-5000 字...", responsePreview: "地下库房比想象中更深。阶梯尽头是一扇厚重的铁门...", createdAt: "2026-05-15T14:09:10Z" },
  { id: "mc_3", organizationId: "org_personal", projectId: "night-rail", generationJobId: "job_review_night", taskType: "continuity_review", model: "gpt-4o-mini", inputTokens: 58400, outputTokens: 900, latencyMs: 11200, status: "error", costUsd: 0.41, promptPreview: "审稿第24章并检查时间线、人物称谓、世界观规则冲突...", responsePreview: "模型调用中断，已释放剩余额度并标记任务可重试。", createdAt: "2026-05-15T13:17:00Z" },
  { id: "mc_4", organizationId: "org_moon", generationJobId: "job_platform_1", taskType: "outline", model: "gpt-4.1", inputTokens: 92000, outputTokens: 3200, latencyMs: 18100, status: "success", costUsd: 2.92, promptPreview: "为企业客户生成 50 章卷纲...", responsePreview: "卷一围绕记忆战争展开，前 10 章建立冲突...", createdAt: "2026-05-15T12:10:00Z" },
];

export const exportsData: ExportFile[] = [
  { id: "exp_1", organizationId: "org_personal", projectId: "river-rain", format: "DOCX", fileName: "江湖旧雨_全书_final_20260514.docx", source: "final_version", size: "1.8 MB", status: "ready", createdAt: "2026-05-14T15:04:00Z" },
  { id: "exp_2", organizationId: "org_personal", projectId: "demo-project", format: "DOCX", fileName: "雾都归档人_第1-12章_20260521.docx", source: "final_version", size: "235,640 字", status: "ready", createdAt: "2026-05-15T12:20:00Z" },
  { id: "exp_3", organizationId: "org_personal", projectId: "night-rail", format: "PDF", fileName: "长安夜行录_审稿报告_20260520.pdf", source: "draft_version", size: "1.2 MB", status: "ready", createdAt: "2026-05-15T11:48:00Z" },
];

export const usageEvents: UsageEvent[] = [
  { id: "use_1", organizationId: "org_personal", userId: "user_writer", projectId: "demo-project", generationJobId: "job_scene_13_2", eventType: "generate_words", amount: 4532, unit: "words", createdAt: "2026-05-15T14:12:00Z" },
  { id: "use_2", organizationId: "org_personal", userId: "user_writer", projectId: "night-rail", generationJobId: "job_review_night", eventType: "review", amount: 1, unit: "times", createdAt: "2026-05-15T13:18:00Z" },
  { id: "use_3", organizationId: "org_personal", userId: "user_writer", projectId: "river-rain", generationJobId: "job_export_river", eventType: "export", amount: 1, unit: "files", createdAt: "2026-05-14T15:04:00Z" },
  { id: "use_4", organizationId: "org_personal", userId: "user_admin", eventType: "manual_adjustment", amount: 20000, unit: "words", createdAt: "2026-05-13T09:30:00Z" },
];

export const auditLogs: AuditLog[] = [
  { id: "audit_1", actor: "admin@novelflow.ai", action: "quota.manual_adjust", resource: "quota_balance", target: "personal-workspace / monthly_generated_words", ip: "10.2.8.12", createdAt: "2026-05-15T12:41:00Z" },
  { id: "audit_2", actor: "admin@novelflow.ai", action: "plan_feature.update", resource: "plan_features", target: "Pro / export_epub", ip: "10.2.8.12", createdAt: "2026-05-15T11:20:00Z" },
  { id: "audit_3", actor: "system", action: "generation_job.cancelled", resource: "generation_jobs", target: "job_review_night", ip: "workflow", createdAt: "2026-05-15T10:08:00Z" },
  { id: "audit_4", actor: "admin@novelflow.ai", action: "system_setting.save", resource: "model_gateway", target: "gpt-4o default temperature", ip: "10.2.8.12", createdAt: "2026-05-14T18:05:00Z" },
];

export const platformTrend = [
  { day: "05/09", words: 118, jobs: 48, users: 22 },
  { day: "05/10", words: 146, jobs: 62, users: 28 },
  { day: "05/11", words: 132, jobs: 54, users: 26 },
  { day: "05/12", words: 171, jobs: 73, users: 33 },
  { day: "05/13", words: 188, jobs: 81, users: 39 },
  { day: "05/14", words: 176, jobs: 77, users: 42 },
  { day: "05/15", words: 214, jobs: 93, users: 51 },
];

export const platformUsers = [
  { id: "user_writer", name: "玄夜", email: "writer@example.com", role: "user", status: "active", organization: "personal-workspace", plan: "Pro", lastSeen: "刚刚" },
  { id: "user_admin", name: "Admin", email: "admin@novelflow.ai", role: "super_admin", status: "active", organization: "personal-workspace", plan: "Pro", lastSeen: "2 分钟前" },
  { id: "user_editor", name: "林棠", email: "editor@moon.ai", role: "user", status: "active", organization: "月见内容工作室", plan: "Team", lastSeen: "15 分钟前" },
  { id: "user_trial", name: "闻舟", email: "trial@example.com", role: "user", status: "suspended", organization: "星海档案社", plan: "Enterprise", lastSeen: "1 天前" },
];

export const contentReviews = [
  { id: "cr_1", title: "第24章疑似高风险暴力描写", organization: "月见内容工作室", project: "夜雨孤城", risk: "高", status: "待审核", model: "rule+llm", createdAt: "2026-05-15 13:58" },
  { id: "cr_2", title: "Prompt 中包含敏感现实人物影射", organization: "personal-workspace", project: "雾都归档人", risk: "中", status: "人工复核", model: "policy-v3", createdAt: "2026-05-15 12:42" },
  { id: "cr_3", title: "导出文件标题命中低风险词库", organization: "星海档案社", project: "王座战争", risk: "低", status: "已放行", model: "rule", createdAt: "2026-05-14 18:05" },
];

export const getProject = (projectId = "demo-project") => projects.find((project) => project.id === projectId) ?? projects[0];
export const getProjectChapters = (projectId = "demo-project") => chapters.filter((chapter) => chapter.projectId === projectId);
export const getChapterScenes = (chapterId = "ch_13") => scenes.filter((scene) => scene.chapterId === chapterId);
