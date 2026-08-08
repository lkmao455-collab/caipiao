// 轻量 API 客户端（基于 fetch，无额外依赖）。
const BASE = import.meta.env.VITE_API_BASE ?? "";

export interface Profile {
  key: string;
  name: string;
  category: string;
  subtitle: string;
  group_keys: string[];
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  configurable: boolean;
  config_schema: Record<string, unknown> | null;
}

export interface Ticket {
  [key: string]: unknown;
}

function authHeader(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function register(username: string, password: string): Promise<void> {
  const r = await fetch(`${BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function login(username: string, password: string): Promise<string> {
  const r = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username, password }).toString(),
  });
  if (!r.ok) throw new Error("登录失败");
  const data = (await r.json()) as { access_token: string };
  return data.access_token;
}

export async function listProfiles(token: string): Promise<Profile[]> {
  const r = await fetch(`${BASE}/profiles`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Profile[];
}

export async function listStrategies(token: string, key: string): Promise<Strategy[]> {
  const r = await fetch(`${BASE}/profiles/${key}/strategies`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Strategy[];
}

export async function generate(
  token: string,
  profileKey: string,
  strategyId: string,
  count: number,
  postFilters: { name: string; params: Record<string, unknown> }[] = [],
): Promise<{ count: number; filtered_count: number; tickets: Ticket[] }> {
  const r = await fetch(`${BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({
      profile_key: profileKey,
      strategy_id: strategyId,
      count,
      post_filters: postFilters,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as { count: number; filtered_count: number; tickets: Ticket[] };
}

export interface FilterParamMeta {
  name: string;
  type: string;
  default: unknown;
  min: number | null;
  max: number | null;
  description: string;
}

export async function getFilters(
  token: string,
  profileKey: string,
): Promise<{ profile_key: string; available: boolean; params: FilterParamMeta[] }> {
  const r = await fetch(`${BASE}/profiles/${profileKey}/filters`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as { profile_key: string; available: boolean; params: FilterParamMeta[] };
}

export interface GroupStats {
  key: string;
  name: string;
  lo: number;
  hi: number;
  count: number;
  color: string;
  frequency: Record<string, number>;
  hot: number[];
  cold: number[];
  missing: [number, number][];
}

export interface ProfileStats {
  profile_key: string;
  total_records: number;
  groups: Record<string, GroupStats>;
  summary: Record<string, unknown>;
  odd_even_ratio: [number, number];
  high_low_ratio: [number, number];
  sum_statistics: Record<string, number>;
  span: Record<string, number>;
  zone_distribution: Record<string, number>;
  common_pairs: { pair: number[]; count: number }[];
  primary_group: string;
}

export async function getStats(token: string, profileKey: string): Promise<ProfileStats> {
  const r = await fetch(`${BASE}/profiles/${profileKey}/stats`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ProfileStats;
}

// --- 遗漏值深度分析 ---
export interface MissingAnalysisTrend {
  number: number;
  current_gap: number;
  recent_gap: number;
  trend: "up" | "down" | "stable";
  change: number;
}

export interface MissingAnalysisResponse {
  profile_key: string;
  primary_group: string;
  windows: number[];
  missing_by_window: Record<number, { number: number; gap: number }[]>;
  trend_data: MissingAnalysisTrend[];
  hot_signals: number[];
  cold_signals: number[];
  gap_distribution: Record<number, number>;
}

export async function getMissingAnalysis(
  token: string,
  profileKey: string,
  windows: string = "10,30,50,100",
): Promise<MissingAnalysisResponse> {
  const params = new URLSearchParams({ windows });
  const r = await fetch(`${BASE}/profiles/${profileKey}/missing-analysis?${params}`, {
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as MissingAnalysisResponse;
}

// --- 常见组合分析 ---
export interface CommonCombo {
  combo: number[];
  count: number;
  frequency: number;
  last_seen: string;
}

export interface ComboAnalysisResponse {
  profile_key: string;
  total_records: number;
  common_pairs: { pair: number[]; count: number }[];
  common_triples: { triple: number[]; count: number }[];
  zone_distribution: Record<string, number>;
  consecutive_frequency: number;
}

export async function getComboAnalysis(
  token: string,
  profileKey: string,
): Promise<ComboAnalysisResponse> {
  const r = await fetch(`${BASE}/profiles/${profileKey}/combo-analysis`, {
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ComboAnalysisResponse;
}

// --- 号码趋势分析 ---
export interface TrendDataPoint {
  draw_date: string;
  issue: string;
  numbers: Record<string, number[]>;
}

export interface TrendAnalysisResponse {
  profile_key: string;
  total_rounds: number;
  trends: TrendDataPoint[];
}

export async function getTrendAnalysis(
  token: string,
  profileKey: string,
  rounds: number = 30,
): Promise<TrendAnalysisResponse> {
  const params = new URLSearchParams({ rounds: String(rounds) });
  const r = await fetch(`${BASE}/profiles/${profileKey}/trend-analysis?${params}`, {
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as TrendAnalysisResponse;
}

// --- 数据导出 ---
export async function exportData(
  token: string,
  profileKey: string,
  format: "csv" | "excel" = "csv",
): Promise<Blob> {
  const params = new URLSearchParams({ format });
  const r = await fetch(`${BASE}/profiles/${profileKey}/export?${params}`, {
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.blob();
}

// --- 智能推荐 ---
export interface Recommendation {
  strategy_id: string;
  strategy_name: string;
  score: number;
  reason: string;
  suggested_params: Record<string, unknown>;
  tags: string[];
}

export async function getRecommendations(
  token: string,
  profileKey: string,
  topN: number = 5,
): Promise<Recommendation[]> {
  const params = new URLSearchParams({ top_n: String(topN) });
  const r = await fetch(`${BASE}/profiles/${profileKey}/recommendations?${params}`, {
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Recommendation[];
}

// --- 多期联合分析 ---
export interface MultiPeriodPair {
  pair: number[];
  count: number;
}

export interface MultiPeriodConsecutive {
  number: number;
  appearances: number;
  positions: number[];
  streak: boolean;
}

export interface MultiPeriodSuggestion {
  strategy: string;
  numbers: number[];
  reason: string;
}

export interface MultiPeriodAnalysisResponse {
  profile_key: string;
  periods_analyzed: number;
  common_pairs: MultiPeriodPair[];
  consecutive_appearances: MultiPeriodConsecutive[];
  zone_history: { date: string; zone1: number; zone2: number; zone3: number }[];
  suggestions: MultiPeriodSuggestion[];
}

export async function getMultiPeriodAnalysis(
  token: string,
  profileKey: string,
  periods: number = 5,
): Promise<MultiPeriodAnalysisResponse> {
  const params = new URLSearchParams({ periods: String(periods) });
  const r = await fetch(`${BASE}/profiles/${profileKey}/multi-period-analysis?${params}`, {
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as MultiPeriodAnalysisResponse;
}

// --- 自动化任务 ---
export interface ScheduledTask {
  id: string;
  name: string;
  task_type: string;
  profile_key: string;
  strategy_id: string | null;
  interval_minutes: number;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
  status: string;
  result: Record<string, unknown> | null;
}

export interface TaskResult {
  task_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  data: Record<string, unknown> | null;
  error: string | null;
}

export async function listTasks(token: string): Promise<ScheduledTask[]> {
  const r = await fetch(`${BASE}/tasks`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ScheduledTask[];
}

export async function createTask(
  token: string,
  task: {
    name: string;
    task_type: string;
    profile_key: string;
    strategy_id?: string;
    interval_minutes?: number;
    params?: Record<string, unknown>;
  },
): Promise<ScheduledTask> {
  const r = await fetch(`${BASE}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify(task),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ScheduledTask;
}

export async function deleteTask(token: string, taskId: string): Promise<void> {
  const r = await fetch(`${BASE}/tasks/${taskId}`, {
    method: "DELETE",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function toggleTask(
  token: string,
  taskId: string,
  enabled: boolean,
): Promise<void> {
  const r = await fetch(`${BASE}/tasks/${taskId}/toggle?enabled=${enabled}`, {
    method: "PATCH",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function runTask(
  token: string,
  taskId: string,
): Promise<TaskResult> {
  const r = await fetch(`${BASE}/tasks/${taskId}/run`, {
    method: "POST",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as TaskResult;
}

// --- 审计日志 ---
export interface AuditLog {
  timestamp: string;
  user_id: string;
  action: string;
  resource: string;
  details: Record<string, unknown>;
  ip_address: string;
  success: boolean;
  error_message: string;
}

export interface AuditStats {
  total_logs: number;
  action_counts: Record<string, number>;
  user_counts: Record<string, number>;
  recent_errors: number;
}

export async function getAuditLogs(
  token: string,
  userId?: string,
  action?: string,
  limit: number = 100,
): Promise<AuditLog[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (userId) params.set("user_id", userId);
  if (action) params.set("action", action);
  const r = await fetch(`${BASE}/audit/logs?${params}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as AuditLog[];
}

export async function getAuditStats(token: string): Promise<AuditStats> {
  const r = await fetch(`${BASE}/audit/stats`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as AuditStats;
}

// --- 多彩种对比 ---
export interface LotteryComparison {
  key: string;
  name: string;
  category: string;
  total_records: number;
  hot_numbers: number[];
  cold_numbers: number[];
  odd_even_ratio: number[];
  high_low_ratio: number[];
  sum_mean: number;
  sum_span: number;
}

export interface ComparisonInsight {
  type: string;
  description: string;
}

export interface LotteryComparisonResponse {
  comparisons: LotteryComparison[];
  insights: ComparisonInsight[];
}

export async function compareLotteries(
  token: string,
  keys: string[],
): Promise<LotteryComparisonResponse> {
  const params = new URLSearchParams({ keys: keys.join(",") });
  const r = await fetch(`${BASE}/profiles/compare-lotteries?${params}`, {
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as LotteryComparisonResponse;
}

// --- 社区互动 ---
export interface Prediction {
  id: string;
  user_id: string;
  username: string;
  profile_key: string;
  strategy_id: string;
  numbers: number[][];
  description: string;
  tags: string[];
  likes: number;
  comments_count: number;
  created_at: string;
  liked_by_me: boolean;
}

export interface Comment {
  id: string;
  user_id: string;
  username: string;
  content: string;
  created_at: string;
  likes: number;
}

export interface LeaderboardEntry {
  rank: number;
  user_id: string;
  username: string;
  score: number;
  predictions_count: number;
  likes_received: number;
}

export async function listPredictions(
  token: string,
  profileKey?: string,
  limit: number = 20,
): Promise<Prediction[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (profileKey) params.set("profile_key", profileKey);
  const r = await fetch(`${BASE}/community/predictions?${params}`, {
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Prediction[];
}

export async function sharePrediction(
  token: string,
  data: {
    profile_key: string;
    strategy_id: string;
    numbers: number[][];
    description?: string;
    tags?: string[];
  },
): Promise<Prediction> {
  const r = await fetch(`${BASE}/community/predictions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Prediction;
}

export async function likePrediction(token: string, predId: string): Promise<void> {
  const r = await fetch(`${BASE}/community/predictions/${predId}/like`, {
    method: "POST",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function getComments(token: string, predId: string): Promise<Comment[]> {
  const r = await fetch(`${BASE}/community/predictions/${predId}/comments`, {
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Comment[];
}

export async function addComment(
  token: string,
  predId: string,
  content: string,
): Promise<Comment> {
  const r = await fetch(`${BASE}/community/predictions/${predId}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ content }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Comment;
}

export async function getLeaderboard(
  token: string,
  limit: number = 10,
): Promise<LeaderboardEntry[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const r = await fetch(`${BASE}/community/leaderboard?${params}`, {
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as LeaderboardEntry[];
}

// --- AI 深度分析 ---
export interface PatternDetection {
  pattern_type: string;
  description: string;
  confidence: number;
  numbers: number[];
  frequency: number;
}

export interface AnomalyDetection {
  draw_date: string;
  issue: string;
  anomaly_type: string;
  description: string;
  severity: string;
}

export interface PredictionConfidence {
  numbers: number[];
  confidence: number;
  factors: string[];
}

export interface AIAnalysisResponse {
  profile_key: string;
  patterns: PatternDetection[];
  anomalies: AnomalyDetection[];
  predictions: PredictionConfidence[];
  model_accuracy: number;
  analysis_summary: string;
}

export async function getAIAnalysis(
  token: string,
  profileKey: string,
  depth: number = 3,
): Promise<AIAnalysisResponse> {
  const params = new URLSearchParams({ depth: String(depth) });
  const r = await fetch(`${BASE}/profiles/${profileKey}/ai-analysis?${params}`, {
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as AIAnalysisResponse;
}

// --- 性能监控 ---
export interface APICallStats {
  total_calls: number;
  avg_duration: number;
  error_rate: number;
  status_counts: Record<string, number>;
  top_paths: { path: string; count: number; avg_ms: number }[];
  slowest_calls: { path: string; duration_ms: number; timestamp: string }[];
}

export interface ErrorStats {
  total_errors: number;
  error_types: Record<string, number>;
  recent_errors: { timestamp: string; path: string; error_type: string; message: string }[];
}

export interface SystemStats {
  memory_mb: number;
  cpu_percent: number;
  threads: number;
  uptime_seconds: number;
}

export async function getAPIStats(token: string, minutes: number = 60): Promise<APICallStats> {
  const params = new URLSearchParams({ minutes: String(minutes) });
  const r = await fetch(`${BASE}/monitoring/api-stats?${params}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as APICallStats;
}

export async function getErrorStats(token: string, minutes: number = 60): Promise<ErrorStats> {
  const params = new URLSearchParams({ minutes: String(minutes) });
  const r = await fetch(`${BASE}/monitoring/error-stats?${params}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ErrorStats;
}

export async function getSystemStats(token: string): Promise<SystemStats> {
  const r = await fetch(`${BASE}/monitoring/system-stats`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as SystemStats;
}

// --- 插件管理 ---
export interface PluginMeta {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  enabled: boolean;
  hooks: string[];
}

export async function getPlugins(token: string): Promise<PluginMeta[]> {
  const r = await fetch(`${BASE}/plugins`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as PluginMeta[];
}

export async function enablePlugin(token: string, pluginId: string): Promise<void> {
  const r = await fetch(`${BASE}/plugins/${pluginId}/enable`, {
    method: "POST",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function disablePlugin(token: string, pluginId: string): Promise<void> {
  const r = await fetch(`${BASE}/plugins/${pluginId}/disable`, {
    method: "POST",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function installPlugin(token: string, pluginDir: string): Promise<void> {
  const r = await fetch(`${BASE}/plugins/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ plugin_dir: pluginDir }),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function uninstallPlugin(token: string, pluginId: string): Promise<void> {
  const r = await fetch(`${BASE}/plugins/${pluginId}`, {
    method: "DELETE",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
}

// --- 实时监控 ---
export interface RealtimeMetrics {
  cpu_percent: number;
  memory_mb: number;
  memory_percent: number;
  network_sent: number;
  network_recv: number;
  timestamp: number;
}

export async function getMetricsHistory(token: string, minutes: number = 5): Promise<RealtimeMetrics[]> {
  const params = new URLSearchParams({ minutes: String(minutes) });
  const r = await fetch(`${BASE}/monitor/history?${params}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  const data = await r.json();
  return data.metrics;
}

// --- 协作系统 ---
export interface CollaborationSession {
  id: string;
  name: string;
  owner_id: string;
  collaborators: number;
}

export async function createCollabSession(token: string, name: string): Promise<CollaborationSession> {
  const r = await fetch(`${BASE}/collab/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as CollaborationSession;
}

export async function listCollabSessions(token: string): Promise<CollaborationSession[]> {
  const r = await fetch(`${BASE}/collab/sessions`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as CollaborationSession[];
}

export async function joinCollabSession(token: string, sessionId: string): Promise<void> {
  const r = await fetch(`${BASE}/collab/sessions/${sessionId}/join`, {
    method: "POST",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
}

// --- 报表系统 ---
export interface ReportConfig {
  id: string;
  name: string;
  description: string;
  columns: { key: string; label: string; type: string }[];
  filters: { field: string; operator: string; value: any }[];
  sort_by: string;
  sort_order: string;
  group_by: string;
  chart_type: string;
}

export async function createReport(token: string, config: Partial<ReportConfig>): Promise<ReportConfig> {
  const r = await fetch(`${BASE}/reports`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify(config),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ReportConfig;
}

export async function listReports(token: string): Promise<ReportConfig[]> {
  const r = await fetch(`${BASE}/reports`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ReportConfig[];
}

export async function generateReport(token: string, reportId: string): Promise<any> {
  const r = await fetch(`${BASE}/reports/${reportId}/generate`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- AI 预测引擎 ---
export async function aiPredict(token: string, profileKey: string, modelName?: string, count?: number): Promise<any> {
  const r = await fetch(`${BASE}/ai/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ profile_key: profileKey, model_name: modelName || "ensemble", count: count || 6 }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function aiBatchPredict(token: string, profileKey: string, modelNames?: string[]): Promise<any> {
  const r = await fetch(`${BASE}/ai/batch-predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ profile_key: profileKey, model_names: modelNames || ["frequency", "markov", "ensemble"] }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 工作流 ---
export interface WorkflowDef {
  id: string;
  name: string;
  description: string;
  nodes: number;
}

export async function createWorkflow(token: string, name: string, nodes?: any[]): Promise<WorkflowDef> {
  const r = await fetch(`${BASE}/workflows`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name, nodes: nodes || [] }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as WorkflowDef;
}

export async function listWorkflows(token: string): Promise<WorkflowDef[]> {
  const r = await fetch(`${BASE}/workflows`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as WorkflowDef[];
}

export async function runWorkflow(token: string, workflowId: string, context?: Record<string, any>): Promise<any> {
  const r = await fetch(`${BASE}/workflows/${workflowId}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ context: context || {} }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 可视化平台 ---
export interface DashboardDef {
  id: string;
  name: string;
  description: string;
  charts: number;
}

export async function createDashboard(token: string, name: string): Promise<DashboardDef> {
  const r = await fetch(`${BASE}/viz/dashboards`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as DashboardDef;
}

export async function listDashboards(token: string): Promise<DashboardDef[]> {
  const r = await fetch(`${BASE}/viz/dashboards`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as DashboardDef[];
}

export async function getVizTemplates(token: string): Promise<any[]> {
  const r = await fetch(`${BASE}/viz/templates`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 任务调度 ---
export interface ScheduledTask {
  id: string;
  name: string;
  task_type: string;
  enabled: boolean;
}

export async function createScheduledTask(token: string, name: string, taskType: string, payload?: Record<string, any>): Promise<ScheduledTask> {
  const r = await fetch(`${BASE}/scheduler/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name, task_type: taskType, payload: payload || {} }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ScheduledTask;
}

export async function listScheduledTasks(token: string): Promise<ScheduledTask[]> {
  const r = await fetch(`${BASE}/scheduler/tasks`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ScheduledTask[];
}

export async function submitScheduledTask(token: string, taskId: string): Promise<any> {
  const r = await fetch(`${BASE}/scheduler/tasks/${taskId}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({}),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 用户行为分析 ---
export async function startBehaviorSession(token: string, device?: string, browser?: string): Promise<string> {
  const r = await fetch(`${BASE}/behavior/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ device, browser }),
  });
  if (!r.ok) throw new Error(await r.text());
  const data = await r.json();
  return data.session_id;
}

export async function trackPageview(token: string, sessionId: string, page: string, title?: string): Promise<void> {
  const r = await fetch(`${BASE}/behavior/pageview`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ session_id: sessionId, page, title }),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function getBehaviorOverview(token: string, minutes?: number): Promise<any> {
  const params = minutes ? new URLSearchParams({ minutes: String(minutes) }) : new URLSearchParams();
  const r = await fetch(`${BASE}/behavior/overview?${params}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function getRetention(token: string, days?: number): Promise<any> {
  const params = days ? new URLSearchParams({ days: String(days) }) : new URLSearchParams();
  const r = await fetch(`${BASE}/behavior/retention?${params}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 国际化管理 ---
export interface LocaleConfig {
  code: string;
  name: string;
  native_name: string;
  direction: string;
  enabled: boolean;
}

export async function listLocales(token: string): Promise<LocaleConfig[]> {
  const r = await fetch(`${BASE}/i18n/locales`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as LocaleConfig[];
}

export async function getTranslations(token: string, namespace: string, locale: string): Promise<Record<string, string>> {
  const r = await fetch(`${BASE}/i18n/translations/${namespace}/${locale}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function setTranslation(token: string, namespace: string, key: string, locale: string, value: string): Promise<void> {
  const r = await fetch(`${BASE}/i18n/translations`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ namespace, key, locale, value }),
  });
  if (!r.ok) throw new Error(await r.text());
}

// --- 消息队列 ---
export async function createMQTopic(token: string, name: string, description?: string): Promise<any> {
  const r = await fetch(`${BASE}/mq/topics`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name, description }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function listMQTopics(token: string): Promise<any[]> {
  const r = await fetch(`${BASE}/mq/topics`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function publishMessage(token: string, topic: string, payload: any): Promise<any> {
  const r = await fetch(`${BASE}/mq/topics/${topic}/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ payload }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 用户画像 ---
export async function addUserTag(token: string, userId: string, name: string, value: string): Promise<void> {
  const r = await fetch(`${BASE}/profile/tags`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ user_id: userId, name, value }),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function getUserTags(token: string, userId: string): Promise<Record<string, string>> {
  const r = await fetch(`${BASE}/profile/tags/${userId}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function getUserProfileSummary(token: string, userId: string): Promise<any> {
  const r = await fetch(`${BASE}/profile/summary/${userId}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function getProfileAnalytics(token: string): Promise<any> {
  const r = await fetch(`${BASE}/profile/analytics`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 数据备份 ---
export interface BackupConfig {
  id: string;
  name: string;
  backup_type: string;
  enabled: boolean;
}

export async function createBackupConfig(token: string, name: string, sourcePaths: string[]): Promise<BackupConfig> {
  const r = await fetch(`${BASE}/backup/configs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name, source_paths: sourcePaths }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as BackupConfig;
}

export async function listBackupConfigs(token: string): Promise<BackupConfig[]> {
  const r = await fetch(`${BASE}/backup/configs`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as BackupConfig[];
}

export async function runBackup(token: string, configId: string): Promise<any> {
  const r = await fetch(`${BASE}/backup/configs/${configId}/run`, {
    method: "POST",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 多租户 ---
export interface Tenant {
  id: string;
  name: string;
  plan: string;
  status: string;
}

export async function createTenant(token: string, name: string, plan?: string): Promise<Tenant> {
  const r = await fetch(`${BASE}/tenants`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name, plan }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Tenant;
}

export async function listTenants(token: string): Promise<Tenant[]> {
  const r = await fetch(`${BASE}/tenants`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Tenant[];
}

// --- 日志分析 ---
export async function searchLogs(token: string, query?: string, level?: string): Promise<any[]> {
  const r = await fetch(`${BASE}/logs/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ query, level }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function getLogStats(token: string, minutes?: number): Promise<any> {
  const params = minutes ? new URLSearchParams({ minutes: String(minutes) }) : new URLSearchParams();
  const r = await fetch(`${BASE}/logs/stats?${params}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 分布式组件 ---
export async function acquireLock(token: string, resource: string, owner: string): Promise<any> {
  const r = await fetch(`${BASE}/distributed/lock/acquire`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ resource, owner }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function releaseLock(token: string, resource: string, lockId: string): Promise<void> {
  const r = await fetch(`${BASE}/distributed/lock/release?resource=${resource}&lock_id=${lockId}`, {
    method: "POST",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function generateDistributedId(token: string): Promise<{ id: number; id_str: string }> {
  const r = await fetch(`${BASE}/distributed/id/next`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 发布管理 ---
export interface FeatureFlag {
  key: string;
  name: string;
  enabled: boolean;
  rollout_percentage: number;
}

export async function createFeatureFlag(token: string, key: string, name: string, enabled?: boolean): Promise<FeatureFlag> {
  const r = await fetch(`${BASE}/release/flags`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ key, name, enabled }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as FeatureFlag;
}

export async function listFeatureFlags(token: string): Promise<FeatureFlag[]> {
  const r = await fetch(`${BASE}/release/flags`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as FeatureFlag[];
}

export async function checkFeatureFlag(token: string, key: string, userId?: string): Promise<boolean> {
  const r = await fetch(`${BASE}/release/flags/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ key, user_id: userId }),
  });
  if (!r.ok) throw new Error(await r.text());
  const data = await r.json();
  return data.enabled;
}

// --- 数据治理 ---
export async function createDataset(token: string, name: string, description?: string): Promise<any> {
  const r = await fetch(`${BASE}/governance/datasets`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name, description }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function listDatasets(token: string): Promise<any[]> {
  const r = await fetch(`${BASE}/governance/datasets`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function getDataLineage(token: string, datasetId: string): Promise<any> {
  const r = await fetch(`${BASE}/governance/lineage/${datasetId}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 质量保障 ---
export async function createTestCase(token: string, name: string, testType: string): Promise<any> {
  const r = await fetch(`${BASE}/qa/cases`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name, test_type: testType }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function listTestCases(token: string): Promise<any[]> {
  const r = await fetch(`${BASE}/qa/cases`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function getSecuritySummary(token: string): Promise<any> {
  const r = await fetch(`${BASE}/qa/security/summary`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- DevOps ---
export interface Pipeline {
  id: string;
  name: string;
  status: string;
  trigger: string;
}

export async function createPipeline(token: string, name: string, stages?: any[]): Promise<Pipeline> {
  const r = await fetch(`${BASE}/devops/pipelines`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name, stages }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Pipeline;
}

export async function listPipelines(token: string): Promise<Pipeline[]> {
  const r = await fetch(`${BASE}/devops/pipelines`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Pipeline[];
}

export async function runPipeline(token: string, pipelineId: string, branch?: string): Promise<any> {
  const r = await fetch(`${BASE}/devops/pipelines/${pipelineId}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ branch }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function listDeploymentTargets(token: string): Promise<any[]> {
  const r = await fetch(`${BASE}/devops/targets`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 服务治理 ---
export async function registerService(token: string, name: string, host: string, port: number): Promise<any> {
  const r = await fetch(`${BASE}/services/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ name, host, port }),
  });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function listServices(token: string): Promise<Record<string, any[]>> {
  const r = await fetch(`${BASE}/services/list`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function discoverService(token: string, serviceName: string): Promise<any> {
  const r = await fetch(`${BASE}/services/discover/${serviceName}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 配置管理 ---
export interface ConfigItem {
  key: string;
  value: any;
  value_type: string;
  description: string;
  category: string;
}

export async function listConfigs(token: string, category?: string): Promise<ConfigItem[]> {
  const params = category ? new URLSearchParams({ category }) : new URLSearchParams();
  const r = await fetch(`${BASE}/config?${params}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ConfigItem[];
}

export async function setConfig(token: string, key: string, value: any, description?: string): Promise<void> {
  const r = await fetch(`${BASE}/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ key, value, description }),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function getConfigVersions(token: string): Promise<any[]> {
  const r = await fetch(`${BASE}/config/versions/list`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 开发者门户 ---
export async function getDeveloperDocs(token: string): Promise<any[]> {
  const r = await fetch(`${BASE}/developer/docs`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

export async function getOpenAPISpec(): Promise<any> {
  const r = await fetch(`${BASE}/developer/openapi.json`);
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 分析平台 ---
export async function trackEvent(token: string, eventType: string, eventName: string, properties?: Record<string, any>): Promise<void> {
  const r = await fetch(`${BASE}/analytics/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ event_type: eventType, event_name: eventName, properties }),
  });
  if (!r.ok) throw new Error(await r.text());
}

export async function getAnalyticsOverview(token: string, minutes?: number): Promise<any> {
  const params = minutes ? new URLSearchParams({ minutes: String(minutes) }) : new URLSearchParams();
  const r = await fetch(`${BASE}/analytics/overview?${params}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

// --- 智能客服 ---
export interface ChatResponse {
  reply: string;
  suggestions: string[];
  action: string | null;
}

export async function sendChatMessage(
  token: string,
  message: string,
): Promise<ChatResponse> {
  const r = await fetch(`${BASE}/chatbot`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ message }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ChatResponse;
}

// --- 用户收藏 ---
export interface Favorite {
  id: string;
  profile_key: string;
  strategy_id: string;
  name: string;
  params: Record<string, unknown>;
  created_at: string;
}

export async function getFavorites(token: string): Promise<Favorite[]> {
  const r = await fetch(`${BASE}/favorites`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Favorite[];
}

export async function addFavorite(
  token: string,
  profileKey: string,
  strategyId: string,
  name: string,
  params: Record<string, unknown> = {},
): Promise<Favorite> {
  const r = await fetch(`${BASE}/favorites`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({
      profile_key: profileKey,
      strategy_id: strategyId,
      name,
      params,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Favorite;
}

export async function deleteFavorite(token: string, id: string): Promise<void> {
  const r = await fetch(`${BASE}/favorites/${id}`, {
    method: "DELETE",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
}

export interface FetchResult {
  profile_key: string;
  mode: string;
  fetched: number;
  added: number;
  total: number;
  latest: Record<string, unknown> | null;
}

export async function fetchProfileData(
  token: string,
  profileKey: string,
  mode: "latest" | "all" = "latest",
): Promise<FetchResult> {
  const r = await fetch(`${BASE}/profiles/${profileKey}/fetch`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ mode }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as FetchResult;
}

export interface BacktestRound {
  target_date: string;
  issue: string;
  matches: Record<string, number>;
  hit: boolean;
  best_tier: string | null;
  round_fixed_prize: number;
  round_float_count: number;
}

export interface BacktestSummary {
  total_rounds: number;
  hit_count: number;
  first_ticket_hit_count: number;
  profit: number;
  total_cost: number;
  total_fixed_prize: number;
  float_prize_count: number;
  tier_breakdown: Record<string, number>;
}

export interface BacktestRecord {
  id: number;
  created_at: string | null;
  profile_key: string;
  strategy_id: string;
  target_date: string;
  start_date: string;
  end_date: string;
  total_rounds: number;
  tickets_count: number;
  total_cost: number;
  total_fixed_prize: number;
  float_prize_count: number;
  hit_count: number;
  profit: number;
  kind: string;
}

export interface BacktestTicket {
  ticket_index: number;
  groups: Record<string, number[]>;
  hits: Record<string, number>;
  prize_name: string;
  prize_amount: number | null;
  is_first: boolean;
}

export async function runBacktest(
  token: string,
  profileKey: string,
  strategyId: string,
  count: number,
  rounds: number,
  postFilters: { name: string; params: Record<string, unknown> }[] = [],
): Promise<{ batch_id: number; rounds: BacktestRound[]; summary: BacktestSummary }> {
  const r = await fetch(`${BASE}/backtest`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({
      profile_key: profileKey,
      strategy_id: strategyId,
      count,
      rounds,
      post_filters: postFilters,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as { batch_id: number; rounds: BacktestRound[]; summary: BacktestSummary };
}

export async function listBacktests(token: string): Promise<BacktestRecord[]> {
  const r = await fetch(`${BASE}/backtest`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as BacktestRecord[];
}

export async function getBacktest(
  token: string,
  id: number,
  kind: string,
): Promise<Record<string, unknown>> {
  const r = await fetch(`${BASE}/backtest/${id}?kind=${kind}`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as Record<string, unknown>;
}

export async function deleteBacktest(token: string, id: number, kind: string): Promise<void> {
  const r = await fetch(`${BASE}/backtest/${id}?kind=${kind}`, {
    method: "DELETE",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
}

// --- 批量策略对比回测 ---
export interface StrategyCompareRequest {
  profile_key: string;
  strategy_ids: string[];
  count?: number;
  rounds?: number;
  history_window?: number;
  start_date?: string;
  end_date?: string;
  options?: Record<string, unknown>;
}

export interface StrategyCompareResult {
  strategy_id: string;
  strategy_name: string;
  total_rounds: number;
  hit_count: number;
  hit_rate: number;
  first_ticket_hit_count: number;
  profit: number;
  total_cost: number;
  total_fixed_prize: number;
  float_prize_count: number;
  tier_breakdown: Record<string, number>;
  profit_per_round: number;
  roi: number;
  max_drawdown: number;
}

export interface StrategyCompareResponse {
  profile_key: string;
  rounds_run: number;
  strategies: StrategyCompareResult[];
  ranking: string[];
}

export async function compareStrategies(
  token: string,
  req: StrategyCompareRequest,
): Promise<StrategyCompareResponse> {
  const r = await fetch(`${BASE}/backtest/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify(req),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as StrategyCompareResponse;
}

// --- 参数优化建议 ---
export interface ParameterSuggestion {
  strategy_id: string;
  strategy_name: string;
  current_params: Record<string, unknown>;
  suggested_params: Record<string, unknown>;
  reason: string;
  expected_improvement: number;
}

export interface ParameterSuggestionResponse {
  profile_key: string;
  strategy_id: string;
  suggestions: ParameterSuggestion[];
  based_on_rounds: number;
}

export async function suggestParameters(
  token: string,
  profileKey: string,
  strategyId: string,
  rounds: number = 30,
): Promise<ParameterSuggestionResponse> {
  const params = new URLSearchParams({
    profile_key: profileKey,
    strategy_id: strategyId,
    rounds: String(rounds),
  });
  const r = await fetch(`${BASE}/backtest/suggest-params?${params}`, {
    method: "POST",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as ParameterSuggestionResponse;
}

// --- 管理后台（P5.E） ---
export interface CurrentUser {
  id: string;
  username: string;
  role: string;
  created_at: string;
}

export interface AdminUser {
  id: string;
  username: string;
  role: string;
  created_at: string;
}

export interface AdminStats {
  user_count: number;
  admin_count: number;
  api_key_count: number;
  total_usage: number;
}

export async function getMe(token: string): Promise<CurrentUser> {
  const r = await fetch(`${BASE}/me`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as CurrentUser;
}

export async function getAdminStats(token: string): Promise<AdminStats> {
  const r = await fetch(`${BASE}/admin/stats`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as AdminStats;
}

export async function listAdminUsers(token: string): Promise<AdminUser[]> {
  const r = await fetch(`${BASE}/admin/users`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as AdminUser[];
}

export async function setUserRole(token: string, id: string, role: string): Promise<AdminUser> {
  const r = await fetch(`${BASE}/admin/users/${id}/role`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ role }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as AdminUser;
}

export async function deleteUser(token: string, id: string): Promise<void> {
  const r = await fetch(`${BASE}/admin/users/${id}`, {
    method: "DELETE",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
}

// --- 缓存管理 ---
export interface CacheStats {
  memory_cache_count: number;
  engine_cache_count: number;
  redis_available: boolean;
}

export async function getCacheStats(token: string): Promise<CacheStats> {
  const r = await fetch(`${BASE}/admin/cache/stats`, { headers: authHeader(token) });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as CacheStats;
}

export async function clearCache(token: string, pattern: string = ""): Promise<{ memory_cache_cleared: number; engine_cache_cleared: number; message: string }> {
  const r = await fetch(`${BASE}/admin/cache/clear?pattern=${encodeURIComponent(pattern)}`, {
    method: "POST",
    headers: authHeader(token),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as { memory_cache_cleared: number; engine_cache_cleared: number; message: string };
}


