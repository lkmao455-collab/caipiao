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


