-- Up Migration

CREATE SCHEMA IF NOT EXISTS iam;
CREATE SCHEMA IF NOT EXISTS tenant;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE iam.users (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email             text NOT NULL,
  display_name      text NOT NULL,
  password_hash     text NOT NULL,
  status            text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  is_platform_admin boolean NOT NULL DEFAULT false,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_email_lower_idx ON iam.users (lower(email));

CREATE TABLE tenant.tenants (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL,
  status     text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tenant.workspaces (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenant.tenants (id) ON DELETE CASCADE,
  name       text NOT NULL,
  status     text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, id)
);
CREATE INDEX workspaces_tenant_idx ON tenant.workspaces (tenant_id);

CREATE TABLE iam.roles (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenant.tenants (id) ON DELETE CASCADE,
  name       text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE iam.permissions (
  key         text PRIMARY KEY,
  description text NOT NULL
);

CREATE TABLE iam.role_permissions (
  role_id        uuid NOT NULL REFERENCES iam.roles (id) ON DELETE CASCADE,
  permission_key text NOT NULL REFERENCES iam.permissions (key) ON DELETE CASCADE,
  PRIMARY KEY (role_id, permission_key)
);

CREATE TABLE iam.memberships (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant.tenants (id) ON DELETE CASCADE,
  workspace_id uuid NOT NULL REFERENCES tenant.workspaces (id) ON DELETE CASCADE,
  user_id      uuid NOT NULL REFERENCES iam.users (id) ON DELETE CASCADE,
  role_id      uuid NOT NULL REFERENCES iam.roles (id) ON DELETE RESTRICT,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, workspace_id, user_id)
);
CREATE INDEX memberships_tenant_user_idx ON iam.memberships (tenant_id, user_id);

CREATE TABLE iam.refresh_tokens (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid NOT NULL REFERENCES iam.users (id) ON DELETE CASCADE,
  tenant_id  uuid REFERENCES tenant.tenants (id) ON DELETE CASCADE,
  family_id  uuid NOT NULL,
  token_hash text NOT NULL UNIQUE,
  status     text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'rotated', 'revoked')),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  rotated_at timestamptz,
  revoked_at timestamptz
);
CREATE INDEX refresh_tokens_family_idx ON iam.refresh_tokens (family_id);
CREATE INDEX refresh_tokens_user_idx ON iam.refresh_tokens (user_id);

CREATE TABLE audit.audit_logs (
  id            bigserial PRIMARY KEY,
  actor_type    text NOT NULL,
  actor_id      uuid,
  action        text NOT NULL,
  resource_type text NOT NULL,
  resource_id   text,
  tenant_id     uuid,
  workspace_id  uuid,
  decision      text NOT NULL CHECK (decision IN ('allow', 'deny')),
  details       jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_logs_tenant_idx ON audit.audit_logs (tenant_id, created_at DESC);

-- 审计表只允许追加：任何 UPDATE/DELETE 直接失败（事实源 §3.3）。
CREATE FUNCTION audit.reject_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_logs is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_logs_no_update BEFORE UPDATE ON audit.audit_logs
  FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();
CREATE TRIGGER audit_logs_no_delete BEFORE DELETE ON audit.audit_logs
  FOR EACH ROW EXECUTE FUNCTION audit.reject_mutation();

-- 0003 范围内的权限点。后续能力各自增量维护自己的权限点。
INSERT INTO iam.permissions (key, description) VALUES
  ('overview:read',   '查看工作台总览'),
  ('tenant:read',     '查看租户'),
  ('tenant:manage',   '管理租户'),
  ('workspace:read',  '查看工作空间'),
  ('workspace:manage','管理工作空间'),
  ('member:manage',   '管理工作空间成员'),
  ('audit:read',      '查看审计日志')
ON CONFLICT (key) DO NOTHING;

-- Down Migration

DROP TABLE IF EXISTS audit.audit_logs;
DROP FUNCTION IF EXISTS audit.reject_mutation();
DROP TABLE IF EXISTS iam.refresh_tokens;
DROP TABLE IF EXISTS iam.memberships;
DROP TABLE IF EXISTS iam.role_permissions;
DROP TABLE IF EXISTS iam.permissions;
DROP TABLE IF EXISTS iam.roles;
DROP TABLE IF EXISTS tenant.workspaces;
DROP TABLE IF EXISTS tenant.tenants;
DROP TABLE IF EXISTS iam.users;
DROP SCHEMA IF EXISTS audit;
DROP SCHEMA IF EXISTS tenant;
DROP SCHEMA IF EXISTS iam;
