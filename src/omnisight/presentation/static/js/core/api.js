// 取数层（07 文档 §5.1）。解决四个现状问题：请求乱序、重复请求、每秒轮询、304 未利用。
import { emit } from './bus.js';

const BASE = '/api/v1';
const TOKEN_HEADER = 'X-OmniSight-Token';
const TOKEN_KEY = 'omnisight.token';

const inflight = new Map();
const cache = new Map();

let token = '';

export class ApiError extends Error {
  constructor(body, status) {
    super(body?.message || `HTTP ${status}`);
    this.name = 'ApiError';
    this.code = body?.code || 'http_error';
    this.field = body?.field || null;
    this.status = status;
  }
}

/** 令牌只经 URL 交接一次，随后存 sessionStorage 并从地址栏抹掉（08 文档 §3.2b）。 */
export function adoptToken(fromPage) {
  if (fromPage) {
    token = fromPage;
    try {
      sessionStorage.setItem(TOKEN_KEY, fromPage);
    } catch (error) {
      // 隐私模式下写不进去：本次会话的内存副本仍然可用。
    }
    history.replaceState(null, '', window.location.pathname + window.location.hash);
    return token;
  }
  try {
    token = sessionStorage.getItem(TOKEN_KEY) || '';
  } catch (error) {
    token = '';
  }
  return token;
}

export function hasToken() {
  return Boolean(token);
}

/** SSE 用得到：EventSource 无法设置请求头，只能把令牌放查询串。 */
export function tokenParam() {
  return token;
}

export function buildUrl(path, params = {}) {
  const url = new URL(BASE + path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue;
    url.searchParams.set(key, String(value));
  }
  return url.pathname + url.search;
}

export async function get(path, params = {}, { signal, maxAge = 0 } = {}) {
  const url = buildUrl(path, params);
  const cached = cache.get(url);
  if (cached && maxAge && Date.now() - cached.at < maxAge) return cached.data;
  if (inflight.has(url)) return inflight.get(url);

  const headers = { [TOKEN_HEADER]: token };
  if (cached?.etag) headers['If-None-Match'] = cached.etag;

  const promise = fetch(url, { signal, headers, credentials: 'omit' })
    .then(async (response) => {
      if (response.status === 304 && cached) return cached.data;
      if (response.status === 204) return null;
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new ApiError(body?.error, response.status);
      cache.set(url, { data: body, at: Date.now(), etag: response.headers.get('ETag') });
      return body;
    })
    .finally(() => inflight.delete(url));

  inflight.set(url, promise);
  return promise;
}

async function write(method, path, body) {
  const response = await fetch(buildUrl(path), {
    method,
    credentials: 'omit',
    headers: { [TOKEN_HEADER]: token, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(payload?.error, response.status);
  // 写操作会改变数据：清掉整个读缓存，别猜哪些 key 受影响。
  invalidate();
  emit('data:changed', { path });
  return payload;
}

export const patch = (path, body) => write('PATCH', path, body);
export const post = (path, body) => write('POST', path, body);
export const del = (path, body) => write('DELETE', path, body);

/** 清缓存。传前缀只清匹配的（周期变化时不必丢弃布局与设置）。 */
export function invalidate(prefix = '') {
  if (!prefix) {
    cache.clear();
    return;
  }
  for (const key of [...cache.keys()]) {
    if (key.startsWith(BASE + prefix)) cache.delete(key);
  }
}

/** 图标 URL 后端已给（`icon_url`），这里只补令牌——<img> 发不出自定义头。 */
export function assetUrl(path) {
  if (!path) return '';
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}token=${encodeURIComponent(token)}`;
}

export const BASE_PATH = BASE;
