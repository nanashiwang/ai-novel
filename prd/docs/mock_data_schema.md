# Mock Data Schema

> 用途：交给 Codex/前端生成 Agent，统一第一阶段 mock 数据字段、状态枚举和示例数据。  
> 建议位置：`docs/mock_data_schema.md`

---

## 1. 设计原则

1. 第一阶段所有页面使用 mock 数据。
2. 字段名称尽量贴近未来后端 API。
3. 所有核心数据都必须带 `organizationId`。
4. 小说业务数据必须带 `projectId`。
5. 任务、模型调用、额度消耗必须能关联 `generationJobId`。
6. UI 中要体现 SaaS 架构：User、Organization、Plan、Entitlement、Quota、Usage、Project、Workflow、ModelCall。

---

## 2. TypeScript 类型定义

### 2.1 Auth / User / Organization

```ts
export type PlatformRole = 'user' | 'operator' | 'support' | 'finance_admin' | 'admin' | 'super_admin'

export type OrganizationRole = 'owner' | 'admin' | 'editor' | 'viewer' | 'billing_manager' | 'member'

export type UserStatus = 'active' | 'suspended' | 'deleted'

export type User = {
  id: string
  name: string
  email: string
  avatarUrl?: string
  platformRole: PlatformRole
  status: UserStatus
  currentOrganizationId: string
}

export type Organization = {
  id: string
  name: string
  ownerUserId: string
  planCode: PlanCode
  status: 'active' | 'suspended' | 'trialing' | 'cancelled'
  createdAt: string
}

export type OrganizationMember = {
  id: string
  organizationId: string
  userId: string
  role: OrganizationRole
  status: 'active' | 'invited' | 'removed'
  joinedAt: string
}
```

---

### 2.2 Plan / Feature / Entitlement / Quota

```ts
export type PlanCode = 'Free' | 'Starter' | 'Pro' | 'Team' | 'Enterprise' | 'Internal'

export type Plan = {
  code: PlanCode
  name: string
  description: string
  priceMonthly: number
  priceYearly?: number
  status: 'active' | 'archived' | 'hidden'
  queuePriority: 'low' | 'normal' | 'high' | 'enterprise' | 'internal'
  maxConcurrentJobs: number
  targetUser: string
}

export type PlanFeature = {
  id: string
  planCode: PlanCode
  featureKey: string
  featureName: string
  enabled: boolean
  limitValue: number | 'unlimited'
  limitUnit: 'words' | 'times' | 'projects' | 'members' | 'formats' | 'GB' | 'level' | 'boolean'
  description: string
}

export type QuotaKey =
  | 'monthly_generated_words'
  | 'monthly_review_count'
  | 'monthly_rewrite_count'
  | 'max_projects'
  | 'team_members'
  | 'concurrent_jobs'
  | 'export_docx'
  | 'export_epub'

export type QuotaBalance = {
  id: string
  organizationId: string
  quotaKey: QuotaKey
  periodStart: string
  periodEnd: string
  limitValue: number
  usedValue: number
  reservedValue: number
  resetAt: string
}

export type QuotaReservation = {
  id: string
  organizationId: string
  generationJobId: string
  quotaKey: QuotaKey
  reservedAmount: number
  consumedAmount: number
  status: 'reserved' | 'settled' | 'released' | 'expired'
  createdAt: string
  updatedAt: string
}

export type UsageEvent = {
  id: string
  organizationId: string
  userId: string
  projectId?: string
  generationJobId?: string
  eventType: 'generate_words' | 'review' | 'rewrite' | 'export' | 'manual_adjustment'
  amount: number
  unit: 'words' | 'times' | 'files'
  metadata?: Record<string, unknown>
  createdAt: string
}
```

---

### 2.3 Project / Novel / Chapter / Scene

```ts
export type ProjectStatus =
  | 'created'
  | 'bible_generating'
  | 'bible_ready'
  | 'outline_generating'
  | 'outline_ready'
  | 'drafting'
  | 'auditing'
  | 'rewriting'
  | 'completed'
  | 'exported'

export type Project = {
  id: string
  organizationId: string
  title: string
  coverUrl?: string
  genre: string
  tags: string[]
  status: ProjectStatus
  targetWordCount: number
  currentWordCount: number
  targetChapterCount: number
  completedChapterCount: number
  currentChapterIndex?: number
  style: string
  targetReader: string
  createdBy: string
  createdAt: string
  updatedAt: string
}

export type NovelSpec = {
  id: string
  organizationId: string
  projectId: string
  premise: string
  theme: string
  genre: string
  tone: string
  narrativePov: string
  styleGuide: string
  constraints: string[]
}

export type ChapterStatus = 'planned' | 'scenes_planned' | 'drafting' | 'drafted' | 'auditing' | 'needs_rewrite' | 'rewriting' | 'finalized'

export type Chapter = {
  id: string
  organizationId: string
  projectId: string
  volumeIndex: number
  chapterIndex: number
  title: string
  summary: string
  goal: string
  conflict: string
  endingHook: string
  status: ChapterStatus
  wordCount: number
  progress: number
  updatedAt: string
}

export type SceneStatus = 'planned' | 'writing' | 'drafted' | 'audited' | 'rewritten' | 'approved'

export type Scene = {
  id: string
  organizationId: string
  projectId: string
  chapterId: string
  sceneIndex: number
  title: string
  timeMarker: string
  location: string
  characters: string[]
  goal: string
  conflict: string
  emotionStart: string
  emotionEnd: string
  reveal: string
  hook: string
  status: SceneStatus
  wordCount: number
}
```

---

### 2.4 Character / World / Memory / Issues

```ts
export type Character = {
  id: string
  organizationId: string
  projectId: string
  name: string
  role: 'protagonist' | 'antagonist' | 'supporting' | 'minor'
  avatarUrl?: string
  description: string
  personality: string[]
  motivation: string
  secret: string
  arc: string
  currentState: {
    chapterIndex: number
    physicalState: string
    emotionalState: string
    knowledgeState: string
  }
  statusBadge: string
}

export type CharacterRelationship = {
  id: string
  projectId: string
  sourceCharacterId: string
  targetCharacterId: string
  relationType: 'trust' | 'suspicion' | 'enemy' | 'cooperation' | 'family' | 'neutral'
  strength: number
  description: string
}

export type WorldItem = {
  id: string
  organizationId: string
  projectId: string
  type: 'location' | 'organization' | 'item' | 'law' | 'magic_system' | 'technology' | 'event' | 'history' | 'custom'
  name: string
  description: string
  rules: string[]
  relatedCharacters: string[]
}

export type MemoryEntry = {
  id: string
  organizationId: string
  projectId: string
  sourceType: 'chapter' | 'scene' | 'character' | 'world_item' | 'plot_thread'
  sourceId: string
  memoryType: 'chapter_summary' | 'scene_summary' | 'character_state' | 'world_rule' | 'foreshadowing' | 'timeline_event' | 'style_rule'
  title: string
  content: string
  importance: 1 | 2 | 3 | 4 | 5
  createdAt: string
}

export type ContinuityIssue = {
  id: string
  organizationId: string
  projectId: string
  chapterId?: string
  sceneId?: string
  issueType: 'character_inconsistency' | 'timeline_conflict' | 'style_drift' | 'foreshadowing_unresolved' | 'repetition' | 'logic_issue'
  severity: 'low' | 'medium' | 'high'
  description: string
  suggestedFix: string
  status: 'open' | 'fixed' | 'ignored'
  createdAt: string
}
```

---

### 2.5 GenerationJob / Workflow / ModelCall

```ts
export type GenerationJobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export type GenerationJobType =
  | 'generate_bible'
  | 'generate_outline'
  | 'generate_chapter_plan'
  | 'generate_scene_plan'
  | 'write_scene'
  | 'audit_scene'
  | 'rewrite_scene'
  | 'audit_chapter'
  | 'export_novel'
  | 'update_character_state'
  | 'update_memory'

export type GenerationJob = {
  id: string
  organizationId: string
  userId: string
  projectId: string
  jobType: GenerationJobType
  title: string
  status: GenerationJobStatus
  priority: 'low' | 'normal' | 'high' | 'enterprise' | 'internal'
  planCode: PlanCode
  reservedQuota: number
  consumedQuota: number
  progress: number
  estimatedRemaining?: string
  createdAt: string
  startedAt?: string
  finishedAt?: string
  errorMessage?: string
}

export type WorkflowStep = {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  duration?: string
}

export type ModelCall = {
  id: string
  organizationId: string
  projectId?: string
  generationJobId?: string
  taskType: string
  model: string
  inputTokens: number
  outputTokens: number
  latencyMs: number
  status: 'success' | 'failed'
  createdAt: string
}
```

---

### 2.6 Export / AuditLog

```ts
export type ExportFile = {
  id: string
  organizationId: string
  projectId: string
  fileName: string
  format: 'Markdown' | 'TXT' | 'DOCX' | 'EPUB' | 'PDF'
  sizeLabel: string
  chapterRange: string
  status: 'completed' | 'failed' | 'processing'
  sourceVersion: 'final' | 'draft'
  createdAt: string
}

export type AuditLog = {
  id: string
  adminUserId: string
  adminName: string
  role: PlatformRole
  action: string
  objectType: string
  objectId: string
  reason: string
  ipAddress: string
  createdAt: string
}
```

---

## 3. Mock 数据建议

### 3.1 Mock Users

```ts
export const mockUsers: User[] = [
  {
    id: 'user_admin',
    name: 'Admin',
    email: 'admin@novelflow.ai',
    platformRole: 'super_admin',
    status: 'active',
    currentOrganizationId: 'org_personal'
  },
  {
    id: 'user_writer',
    name: '玄夜',
    email: 'writer@example.com',
    platformRole: 'user',
    status: 'active',
    currentOrganizationId: 'org_personal'
  }
]
```

### 3.2 Mock Organization

```ts
export const mockOrganizations: Organization[] = [
  {
    id: 'org_personal',
    name: 'personal-workspace',
    ownerUserId: 'user_writer',
    planCode: 'Pro',
    status: 'active',
    createdAt: '2024-05-01 10:00:00'
  },
  {
    id: 'org_sky_novel',
    name: 'sky-novel',
    ownerUserId: 'user_1024',
    planCode: 'Team',
    status: 'active',
    createdAt: '2024-04-20 09:30:00'
  }
]
```

### 3.3 Mock Projects

```ts
export const mockProjects: Project[] = [
  {
    id: 'project_fog_archive',
    organizationId: 'org_personal',
    title: '雾都归档人',
    genre: '悬疑 / 都市',
    tags: ['悬疑', '都市', '轻奇幻'],
    status: 'drafting',
    targetWordCount: 300000,
    currentWordCount: 182400,
    targetChapterCount: 60,
    completedChapterCount: 12,
    currentChapterIndex: 13,
    style: '冷峻、克制、电影感',
    targetReader: '18-35 岁悬疑读者',
    createdBy: 'user_writer',
    createdAt: '2024-05-10 14:32:00',
    updatedAt: '2024-05-17 10:21:00'
  },
  {
    id: 'project_star_throne',
    organizationId: 'org_personal',
    title: '星海失落王座',
    genre: '科幻 / 史诗',
    tags: ['科幻', '史诗'],
    status: 'outline_ready',
    targetWordCount: 500000,
    currentWordCount: 0,
    targetChapterCount: 80,
    completedChapterCount: 0,
    style: '宏大、冷峻、群像',
    targetReader: '科幻长篇读者',
    createdBy: 'user_writer',
    createdAt: '2024-05-12 09:12:00',
    updatedAt: '2024-05-16 18:40:00'
  },
  {
    id: 'project_changan_night',
    organizationId: 'org_personal',
    title: '长安夜行录',
    genre: '古风 / 探案',
    tags: ['古风', '探案'],
    status: 'auditing',
    targetWordCount: 260000,
    currentWordCount: 238900,
    targetChapterCount: 40,
    completedChapterCount: 24,
    style: '古典、诡谲、节奏紧凑',
    targetReader: '古风探案读者',
    createdBy: 'user_writer',
    createdAt: '2024-04-18 13:22:00',
    updatedAt: '2024-05-17 08:45:00'
  },
  {
    id: 'project_dark_tower',
    organizationId: 'org_personal',
    title: '黑塔继承者',
    genre: '奇幻 / 升级',
    tags: ['奇幻', '升级'],
    status: 'bible_ready',
    targetWordCount: 800000,
    currentWordCount: 0,
    targetChapterCount: 120,
    completedChapterCount: 0,
    style: '热血、暗黑、史诗',
    targetReader: '男频奇幻读者',
    createdBy: 'user_writer',
    createdAt: '2024-05-14 11:10:00',
    updatedAt: '2024-05-14 15:30:00'
  },
  {
    id: 'project_jianghu_rain',
    organizationId: 'org_personal',
    title: '江湖旧雨',
    genre: '武侠 / 群像',
    tags: ['武侠', '群像'],
    status: 'completed',
    targetWordCount: 420000,
    currentWordCount: 412000,
    targetChapterCount: 48,
    completedChapterCount: 48,
    style: '苍凉、江湖、群像',
    targetReader: '武侠读者',
    createdBy: 'user_writer',
    createdAt: '2024-03-02 16:20:00',
    updatedAt: '2024-05-01 09:00:00'
  }
]
```

### 3.4 Mock Chapters

```ts
export const mockChapters: Chapter[] = [
  {
    id: 'chapter_11',
    organizationId: 'org_personal',
    projectId: 'project_fog_archive',
    volumeIndex: 1,
    chapterIndex: 11,
    title: '迷雾中的信件',
    summary: '主角收到来自十年前的匿名信件。',
    goal: '引出地下档案库线索。',
    conflict: '信件内容与官方档案矛盾。',
    endingHook: '信纸背面出现父亲笔迹。',
    status: 'finalized',
    wordCount: 6320,
    progress: 100,
    updatedAt: '2024-05-17 09:10:00'
  },
  {
    id: 'chapter_12',
    organizationId: 'org_personal',
    projectId: 'project_fog_archive',
    volumeIndex: 1,
    chapterIndex: 12,
    title: '档案馆的低语',
    summary: '主角发现档案馆地下层存在被隐藏入口。',
    goal: '让主角接近真相入口。',
    conflict: '许知遥阻止主角深入。',
    endingHook: '地下层传来敲击声。',
    status: 'auditing',
    wordCount: 8732,
    progress: 100,
    updatedAt: '2024-05-17 08:45:00'
  },
  {
    id: 'chapter_13',
    organizationId: 'org_personal',
    projectId: 'project_fog_archive',
    volumeIndex: 1,
    chapterIndex: 13,
    title: '档案室深处',
    summary: '主角进入地下档案库，发现黑色档案盒。',
    goal: '揭示十年前失踪案存在补充卷。',
    conflict: '许知遥隐瞒真相，主角开始试探。',
    endingHook: '合照中出现十年前的许知遥。',
    status: 'drafting',
    wordCount: 3421,
    progress: 45,
    updatedAt: '2024-05-17 10:21:00'
  }
]
```

### 3.5 Mock Scenes

```ts
export const mockScenes: Scene[] = [
  {
    id: 'scene_13_1',
    organizationId: 'org_personal',
    projectId: 'project_fog_archive',
    chapterId: 'chapter_13',
    sceneIndex: 1,
    title: '回到档案馆',
    timeMarker: '深夜',
    location: '旧城区档案馆入口大厅',
    characters: ['陆沉舟', '苏晚'],
    goal: '让主角返回档案馆并发现入口异常。',
    conflict: '保安记录显示无人进入，但门锁被换过。',
    emotionStart: '警惕',
    emotionEnd: '不安',
    reveal: '档案馆地下层存在隐藏入口。',
    hook: '电梯显示不存在的 B3 层。',
    status: 'approved',
    wordCount: 2180
  },
  {
    id: 'scene_13_2',
    organizationId: 'org_personal',
    projectId: 'project_fog_archive',
    chapterId: 'chapter_13',
    sceneIndex: 2,
    title: '地下库房',
    timeMarker: '深夜',
    location: '档案馆地下二层库房',
    characters: ['陆沉舟', '苏晚'],
    goal: '发现黑色档案盒。',
    conflict: '苏晚阻止陆沉舟查看补充卷。',
    emotionStart: '怀疑',
    emotionEnd: '震惊',
    reveal: '十年前失踪案存在被删除的补充卷。',
    hook: '黑色档案盒中出现父亲和苏晚的旧合照。',
    status: 'writing',
    wordCount: 2158
  }
]
```

### 3.6 Mock Characters

```ts
export const mockCharacters: Character[] = [
  {
    id: 'char_lu',
    organizationId: 'org_personal',
    projectId: 'project_fog_archive',
    name: '陆沉舟',
    role: 'protagonist',
    description: '旧城区档案员，能读取旧物记忆。',
    personality: ['理性', '内敛', '执着', '不轻易信任他人'],
    motivation: '寻找父亲死亡背后的真相。',
    secret: '曾因读取记忆能力丢失一段重要记忆。',
    arc: '从逃避真相到主动揭开城市记忆系统。',
    currentState: {
      chapterIndex: 13,
      physicalState: '右肩旧伤隐隐作痛',
      emotionalState: '焦虑中带决心',
      knowledgeState: '知道归档计划与父亲死亡有关'
    },
    statusBadge: '活跃'
  },
  {
    id: 'char_su',
    organizationId: 'org_personal',
    projectId: 'project_fog_archive',
    name: '苏晚',
    role: 'supporting',
    description: '调查员，曾参与十年前失踪案调查。',
    personality: ['冷静', '克制', '防备', '负罪感强'],
    motivation: '阻止陆沉舟接近会伤害他的真相。',
    secret: '十年前见过陆沉舟的父亲。',
    arc: '从隐瞒者到共同揭露真相。',
    currentState: {
      chapterIndex: 13,
      physicalState: '轻微失眠',
      emotionalState: '紧张但克制',
      knowledgeState: '知道地下档案库的部分秘密'
    },
    statusBadge: '活跃'
  }
]
```

### 3.7 Mock Jobs

```ts
export const mockGenerationJobs: GenerationJob[] = [
  {
    id: 'job_scene_13_2',
    organizationId: 'org_personal',
    userId: 'user_writer',
    projectId: 'project_fog_archive',
    jobType: 'write_scene',
    title: '第13章 场景2：地下库房',
    status: 'running',
    priority: 'high',
    planCode: 'Pro',
    reservedQuota: 8000,
    consumedQuota: 6200,
    progress: 62,
    estimatedRemaining: '8 分钟',
    createdAt: '2024-05-17 10:32:08',
    startedAt: '2024-05-17 10:32:10'
  },
  {
    id: 'job_outline_volume_2',
    organizationId: 'org_personal',
    userId: 'user_writer',
    projectId: 'project_star_throne',
    jobType: 'generate_outline',
    title: '第2卷大纲',
    status: 'queued',
    priority: 'high',
    planCode: 'Pro',
    reservedQuota: 3000,
    consumedQuota: 0,
    progress: 40,
    estimatedRemaining: '15 分钟',
    createdAt: '2024-05-17 10:31:59'
  },
  {
    id: 'job_review_24',
    organizationId: 'org_personal',
    userId: 'user_writer',
    projectId: 'project_changan_night',
    jobType: 'audit_chapter',
    title: '第24章审稿',
    status: 'running',
    priority: 'normal',
    planCode: 'Pro',
    reservedQuota: 1,
    consumedQuota: 0,
    progress: 88,
    estimatedRemaining: '6 分钟',
    createdAt: '2024-05-17 10:26:33'
  }
]
```

### 3.8 Mock Workflow Steps

```ts
export const mockWorkflowSteps: WorkflowStep[] = [
  { id: 'step_1', name: '权限检查', status: 'completed', progress: 100, duration: '00:00:01' },
  { id: 'step_2', name: '额度预留', status: 'completed', progress: 100, duration: '00:00:03' },
  { id: 'step_3', name: '构建上下文', status: 'completed', progress: 100, duration: '00:00:18' },
  { id: 'step_4', name: '调用 GPT', status: 'running', progress: 62, duration: '00:01:42' },
  { id: 'step_5', name: '保存版本', status: 'pending', progress: 0 },
  { id: 'step_6', name: '结算用量', status: 'pending', progress: 0 },
  { id: 'step_7', name: '更新记忆', status: 'pending', progress: 0 }
]
```

### 3.9 Mock Model Calls

```ts
export const mockModelCalls: ModelCall[] = [
  {
    id: 'call_1',
    organizationId: 'org_personal',
    projectId: 'project_fog_archive',
    generationJobId: 'job_scene_13_2',
    taskType: 'generate_scene',
    model: 'gpt-4o',
    inputTokens: 12842,
    outputTokens: 6327,
    latencyMs: 12480,
    status: 'success',
    createdAt: '2024-05-17 10:33:52'
  },
  {
    id: 'call_2',
    organizationId: 'org_personal',
    projectId: 'project_fog_archive',
    generationJobId: 'job_outline_volume_2',
    taskType: 'outline_chapter',
    model: 'gpt-4o',
    inputTokens: 8231,
    outputTokens: 2114,
    latencyMs: 8210,
    status: 'success',
    createdAt: '2024-05-17 10:31:59'
  }
]
```

### 3.10 Mock Plans and Features

```ts
export const mockPlans: Plan[] = [
  {
    code: 'Free',
    name: '免费体验版',
    description: '适合体验和短篇测试',
    priceMonthly: 0,
    status: 'active',
    queuePriority: 'low',
    maxConcurrentJobs: 1,
    targetUser: '体验用户'
  },
  {
    code: 'Pro',
    name: '专业版',
    description: '适合个人长篇小说自动生成',
    priceMonthly: 99,
    priceYearly: 990,
    status: 'active',
    queuePriority: 'high',
    maxConcurrentJobs: 5,
    targetUser: '个人创作者 / 专业作者'
  },
  {
    code: 'Team',
    name: '团队版',
    description: '适合工作室与小团队协作',
    priceMonthly: 299,
    status: 'active',
    queuePriority: 'high',
    maxConcurrentJobs: 10,
    targetUser: '小说工作室 / 团队'
  },
  {
    code: 'Internal',
    name: '内部测试版',
    description: '内部测试，不受普通额度限制',
    priceMonthly: 0,
    status: 'hidden',
    queuePriority: 'internal',
    maxConcurrentJobs: 100,
    targetUser: '内部测试组织'
  }
]
```

---

## 4. 状态颜色建议

```ts
export const statusColors = {
  created: 'slate',
  bible_ready: 'blue',
  outline_ready: 'cyan',
  drafting: 'indigo',
  auditing: 'amber',
  rewriting: 'purple',
  completed: 'emerald',
  exported: 'emerald',

  queued: 'amber',
  running: 'blue',
  failed: 'red',
  cancelled: 'slate',

  low: 'emerald',
  medium: 'amber',
  high: 'red'
}
```

---

## 5. Mock Action 行为

建议实现以下 mock 行为：

```ts
createProject()
// 新建一个 Project，跳转 /studio/projects/project_fog_archive

startGenerationJob(jobType)
// 新建一个 queued job，1 秒后改 running

cancelJob(jobId)
// running/queued -> cancelled

retryJob(jobId)
// failed -> queued

startExport(format)
// 新建 processing export file，1 秒后改 completed

saveSystemSettings()
// 如果 user.platformRole !== 'super_admin'，按钮 disabled
// 如果是 super_admin，显示 toast: 已保存，操作已写入 audit_logs
```

---

## 6. 需要在 UI 中重点展示的架构概念

Codex 实现 UI 时，不需要实现真实业务逻辑，但必须通过界面体现这些概念：

```text
Organization-first 多租户
Role / Permission
Plan / Feature / Entitlement
Quota / Usage
Workflow 长任务
Model Gateway
Memory Engine
Auditor / Rewriter
final_draft_versions
Audit Logs
```

这些概念应通过 badge、表格列、说明文字、进度条、卡片和 mock 数据呈现。
