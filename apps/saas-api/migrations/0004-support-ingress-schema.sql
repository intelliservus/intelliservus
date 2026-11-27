-- Up Migration
-- 接入侧数据模型：投递记录、标准化事件、outbox、处理幂等记录，
-- 以及企业会话/消息的最小存储（供 0005 解析映射后落库，0007 扩列）。

CREATE SCHEMA IF NOT EXISTS integration;
CREATE SCHEMA IF NOT EXISTS support;

CREATE TABLE integration.webhook_deliveries (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider     text NOT NULL,
  account_id   text NOT NULL,
  delivery_key text NOT NULL,
  event_type   text,
  -- 上游缺失 Delivery ID 时改用降级键，留痕以便事后审计（ADR-003）。
  degraded     boolean NOT NULL DEFAULT false,
  received_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, account_id, delivery_key)
);
CREATE INDEX webhook_deliveries_received_idx
  ON integration.webhook_deliveries (received_at DESC);

CREATE TABLE integration.outbox_events (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type     text NOT NULL,
  schema_version integer NOT NULL DEFAULT 1,
  tenant_id      uuid,
  workspace_id   uuid,
  trace_id       text NOT NULL DEFAULT '',
  occurred_at    timestamptz NOT NULL,
  attempt        integer NOT NULL DEFAULT 0,
  retry_of       uuid REFERENCES integration.outbox_events (id),
  payload        jsonb NOT NULL,
  status         text NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'processing', 'completed', 'dead_letter')),
  available_at   timestamptz NOT NULL DEFAULT now(),
  locked_at      timestamptz,
  locked_by      text,
  last_error     text,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX outbox_events_claim_idx ON integration.outbox_events (status, available_at);

CREATE TABLE support.support_events (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  delivery_id         uuid NOT NULL
                      REFERENCES integration.webhook_deliveries (id) ON DELETE CASCADE,
  -- 解析映射前允许为空：投递先落库，归属由 0005 的映射回填（design D5）。
  tenant_id           uuid,
  workspace_id        uuid,
  event_type          text NOT NULL,
  provider_created_at timestamptz,
  payload             jsonb NOT NULL,
  status              text NOT NULL DEFAULT 'received'
                      CHECK (status IN (
                        'received', 'pending_mapping', 'filtered', 'published', 'failed'
                      )),
  degraded            boolean NOT NULL DEFAULT false,
  trace_id            text NOT NULL DEFAULT '',
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX support_events_delivery_idx ON support.support_events (delivery_id);
CREATE INDEX support_events_status_idx ON support.support_events (status, created_at);

CREATE TABLE support.conversations (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL,
  workspace_id        uuid NOT NULL,
  -- inbox 归属由 0005 的渠道映射建立外键。
  channel_id          uuid,
  external_id         text NOT NULL,
  provider_created_at timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, external_id)
);
CREATE INDEX conversations_tenant_workspace_idx
  ON support.conversations (tenant_id, workspace_id);

CREATE TABLE support.messages (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL,
  workspace_id        uuid NOT NULL,
  conversation_id     uuid NOT NULL
                      REFERENCES support.conversations (id) ON DELETE CASCADE,
  external_id         text NOT NULL,
  direction           text NOT NULL CHECK (direction IN ('inbound', 'outbound')),
  provider_created_at timestamptz,
  sequence_no         bigint,
  -- 只存引用或摘要，不落完整消息体（事实源 §3.3、§13.2）。
  content_ref         text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (conversation_id, external_id)
);
CREATE INDEX messages_conversation_order_idx
  ON support.messages (conversation_id, provider_created_at);

CREATE TABLE integration.message_processing_records (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL,
  workspace_id    uuid NOT NULL,
  message_id      uuid NOT NULL REFERENCES support.messages (id) ON DELETE CASCADE,
  processing_type text NOT NULL,
  status          text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'completed', 'skipped_duplicate', 'failed')),
  agent_run_id    uuid,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (message_id, processing_type)
);

-- 已归属租户的表启用 RLS；接入侧三张表（投递、事件、outbox）在解析前无租户，
-- 权限由角色授权控制（design D4），0005 回填后再收紧。
ALTER TABLE support.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE support.conversations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON support.conversations
  FOR ALL
  USING (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  )
  WITH CHECK (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  );

ALTER TABLE support.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE support.messages FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON support.messages
  FOR ALL
  USING (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  )
  WITH CHECK (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  );

ALTER TABLE integration.message_processing_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE integration.message_processing_records FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON integration.message_processing_records
  FOR ALL
  USING (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  )
  WITH CHECK (
    current_setting('app.scope', true) = 'platform'
    OR tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid
  );

-- 应用角色 saas_app 需要读写新 schema（0003 的默认权限只覆盖 iam/tenant/audit）。
GRANT USAGE ON SCHEMA integration, support TO saas_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA integration, support TO saas_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA integration
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO saas_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA support
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO saas_app;

-- Down Migration

ALTER DEFAULT PRIVILEGES IN SCHEMA support
  REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM saas_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA integration
  REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM saas_app;
REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA integration, support FROM saas_app;
REVOKE USAGE ON SCHEMA integration, support FROM saas_app;

DROP TABLE IF EXISTS integration.message_processing_records;
DROP TABLE IF EXISTS support.messages;
DROP TABLE IF EXISTS support.conversations;
DROP TABLE IF EXISTS support.support_events;
DROP TABLE IF EXISTS integration.outbox_events;
DROP TABLE IF EXISTS integration.webhook_deliveries;
DROP SCHEMA IF EXISTS support;
DROP SCHEMA IF EXISTS integration;
