-- Up Migration
-- 公开 Ingress 使用的最小权限角色：只能追加投递、事件与 outbox 记录，
-- 不能读取任何租户业务表（design D4）。

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'saas_ingress') THEN
    CREATE ROLE saas_ingress NOLOGIN;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA integration, support TO saas_ingress;

GRANT INSERT ON integration.webhook_deliveries TO saas_ingress;
GRANT INSERT ON support.support_events TO saas_ingress;
GRANT INSERT ON integration.outbox_events TO saas_ingress;

-- Down Migration

REVOKE INSERT ON integration.outbox_events FROM saas_ingress;
REVOKE INSERT ON support.support_events FROM saas_ingress;
REVOKE INSERT ON integration.webhook_deliveries FROM saas_ingress;
REVOKE USAGE ON SCHEMA integration, support FROM saas_ingress;
DROP ROLE IF EXISTS saas_ingress;
