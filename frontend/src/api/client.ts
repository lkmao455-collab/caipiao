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
): Promise<{ count: number; tickets: Ticket[] }> {
  const r = await fetch(`${BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify({ profile_key: profileKey, strategy_id: strategyId, count }),
  });
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as { count: number; tickets: Ticket[] };
}
