INSERT INTO users (id, email, display_name, platform_role, is_platform_staff)
VALUES
  ('user_writer', 'writer@example.com', '玄夜', 'user', false)
ON CONFLICT (id) DO NOTHING;

INSERT INTO organizations (id, name, owner_user_id, status)
VALUES ('org_personal', 'personal-workspace', 'user_writer', 'active')
ON CONFLICT (id) DO NOTHING;

INSERT INTO organization_members (id, organization_id, user_id, role, status)
VALUES
  ('mem_writer', 'org_personal', 'user_writer', 'owner', 'active')
ON CONFLICT (organization_id, user_id) DO NOTHING;

INSERT INTO plans (id, code, name, description, price_monthly, status)
VALUES
  ('plan_free', 'Free', 'Free', '免费体验', 0, 'active'),
  ('plan_starter', 'Starter', 'Starter', '适合轻量连载作者', 49, 'active'),
  ('plan_pro', 'Pro', 'Pro', '长篇小说自动生产', 129, 'active'),
  ('plan_team', 'Team', 'Team', '团队协作与 API', 399, 'active'),
  ('plan_enterprise', 'Enterprise', 'Enterprise', '专属队列、合同额度和审计导出', 0, 'active')
ON CONFLICT (code) DO NOTHING;

WITH seed(code, feature_key, limit_value, limit_unit) AS (
  VALUES
    ('Free', 'monthly_generated_words', 50000, 'words'),
    ('Free', 'monthly_review_count', 10, 'times'),
    ('Starter', 'monthly_generated_words', 300000, 'words'),
    ('Starter', 'monthly_review_count', 80, 'times'),
    ('Pro', 'monthly_generated_words', 1000000, 'words'),
    ('Pro', 'monthly_review_count', 300, 'times'),
    ('Pro', 'monthly_rewrite_count', 180, 'times'),
    ('Team', 'monthly_generated_words', 5000000, 'words'),
    ('Team', 'monthly_review_count', 1500, 'times'),
    ('Team', 'api_keys', 10, 'keys'),
    ('Enterprise', 'monthly_generated_words', 999999999, 'words'),
    ('Enterprise', 'dedicated_queue', 1, 'boolean')
)
INSERT INTO plan_features (
  id, plan_id, feature_key, enabled, limit_value, limit_unit, created_at, updated_at
)
SELECT
  'pf_' || lower(seed.code) || '_' || seed.feature_key,
  plans.id,
  seed.feature_key,
  true,
  seed.limit_value,
  seed.limit_unit,
  now(),
  now()
FROM seed
JOIN plans ON plans.code = seed.code
WHERE NOT EXISTS (
  SELECT 1
  FROM plan_features existing
  WHERE existing.plan_id = plans.id
    AND existing.feature_key = seed.feature_key
);

INSERT INTO projects (id, organization_id, created_by, title, genre, target_word_count, target_chapter_count, style, status)
VALUES ('demo-project', 'org_personal', 'user_writer', '雾都归档人', '悬疑 · 都市', 300000, 48, '冷峻克制，细节密集', 'drafting')
ON CONFLICT (id) DO NOTHING;
