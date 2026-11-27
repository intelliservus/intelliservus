-- Up Migration
-- 行级安全：租户隔离的纵深防御。仅覆盖平台表；业务表在引入时各自定义策略。

ALTER TABLE tenant.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant.tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant.tenants
  FOR ALL
  USING (
    current_setting('app.scope', true) = 'platform'
    OR id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  )
  WITH CHECK (
    current_setting('app.scope', true) = 'platform'
    OR id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  );

ALTER TABLE tenant.workspaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant.workspaces FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant.workspaces
  FOR ALL
  USING (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  )
  WITH CHECK (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  );

ALTER TABLE iam.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.roles FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON iam.roles
  FOR ALL
  USING (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  )
  WITH CHECK (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  );

ALTER TABLE iam.memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON iam.memberships
  FOR ALL
  USING (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  )
  WITH CHECK (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  );

ALTER TABLE iam.refresh_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE iam.refresh_tokens FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON iam.refresh_tokens
  FOR ALL
  USING (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  )
  WITH CHECK (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  );

ALTER TABLE audit.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit.audit_logs FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON audit.audit_logs
  FOR ALL
  USING (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  )
  WITH CHECK (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  );

-- Down Migration

DROP POLICY IF EXISTS tenant_isolation ON audit.audit_logs;
ALTER TABLE audit.audit_logs DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON iam.refresh_tokens;
ALTER TABLE iam.refresh_tokens DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON iam.memberships;
ALTER TABLE iam.memberships DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON iam.roles;
ALTER TABLE iam.roles DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON tenant.workspaces;
ALTER TABLE tenant.workspaces DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON tenant.tenants;
ALTER TABLE tenant.tenants DISABLE ROW LEVEL SECURITY;
