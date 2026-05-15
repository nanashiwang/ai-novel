INSERT INTO users (id, email, display_name, platform_role, is_platform_staff)
VALUES
  ('user_writer', 'writer@example.com', '玄夜', 'user', false),
  ('user_admin', 'admin@novelflow.ai', 'Admin', 'super_admin', true)
ON CONFLICT (id) DO NOTHING;

INSERT INTO organizations (id, name, owner_user_id, status)
VALUES ('org_personal', 'personal-workspace', 'user_writer', 'active')
ON CONFLICT (id) DO NOTHING;

INSERT INTO organization_members (id, organization_id, user_id, role, status)
VALUES
  ('mem_writer', 'org_personal', 'user_writer', 'owner', 'active'),
  ('mem_admin', 'org_personal', 'user_admin', 'owner', 'active')
ON CONFLICT (organization_id, user_id) DO NOTHING;

INSERT INTO plans (id, code, name, description, price_monthly, status)
VALUES
  ('plan_free', 'Free', 'Free', '免费体验', 0, 'active'),
  ('plan_pro', 'Pro', 'Pro', '长篇小说自动生产', 129, 'active'),
  ('plan_team', 'Team', 'Team', '团队协作与 API', 399, 'active')
ON CONFLICT (code) DO NOTHING;

INSERT INTO projects (id, organization_id, created_by, title, genre, target_word_count, target_chapter_count, style, status)
VALUES ('demo-project', 'org_personal', 'user_writer', '雾都归档人', '悬疑 · 都市', 300000, 48, '冷峻克制，细节密集', 'drafting')
ON CONFLICT (id) DO NOTHING;
