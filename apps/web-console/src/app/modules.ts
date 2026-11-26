export type AppModule = {
  path: string;
  title: string;
  description: string;
  permission: string;
};

export const appModules: readonly AppModule[] = [
  { path: 'overview', title: '工作台', description: '总览平台与企业客服运营情况', permission: 'overview:read' },
  { path: 'tenants', title: '租户', description: '租户信息与平台级资源管理', permission: 'tenant:read' },
  { path: 'workspaces', title: '工作空间', description: '工作空间、成员与角色', permission: 'workspace:read' },
  { path: 'channels', title: '渠道', description: '渠道配置与 Chatwoot Account / Inbox 映射', permission: 'channel:read' },
  { path: 'agents', title: 'Agent', description: '草稿、配置、版本、发布与回滚', permission: 'agent:read' },
  { path: 'knowledge', title: '知识库', description: '文档摄取、版本与发布', permission: 'knowledge:read' },
  { path: 'tools', title: '工具', description: '工具定义、版本、凭证与执行记录', permission: 'tool:read' },
  { path: 'models', title: '模型', description: '模型供应商与模型配置', permission: 'model:read' },
  { path: 'evaluation', title: '评测', description: '测试集、回归运行与质检', permission: 'evaluation:read' },
  { path: 'analytics', title: '运营', description: '解决结果、用量与成本', permission: 'analytics:read' },
  { path: 'audit', title: '审计', description: '管理操作与安全拒绝记录', permission: 'audit:read' },
  { path: 'runs', title: '运行', description: 'AgentRun 详情、Trace 与取消', permission: 'run:read' },
];
