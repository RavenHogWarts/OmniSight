// hash 路由与 URL 同步（07 文档 §4.2）。
//
// 两种历史行为，刻意不同：
//   - 换视图用 pushState —— 用户期望返回键回到上一个页面。
//   - 换周期/指标用 replaceState —— 否则连点 20 次日期箭头后要按 20 次返回键。
import { getState, setState, subscribe } from './store.js';

export const ROUTES = ['overview', 'apps', 'keyboard', 'insights'];
const DEFAULT_ROUTE = 'overview';

let applying = false;

/** `#/keyboard?range=week&date=2026-08-31&metric=duration_avg_ms` */
export function parseHash(hash = window.location.hash) {
  const raw = String(hash || '').replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const route = ROUTES.includes(path) ? path : DEFAULT_ROUTE;
  const params = new URLSearchParams(query);
  return { route, params };
}

export function currentQuery() {
  const { period, metric, scopeAppId, selectedAppId, timelineView } = getState();
  const params = new URLSearchParams();
  params.set('range', period.range);
  if (period.range === 'custom') {
    if (period.start) params.set('start', period.start);
    if (period.end) params.set('end', period.end);
  } else if (period.date) {
    params.set('date', period.date);
  }
  if (metric !== 'press_count') params.set('metric', metric);
  if (timelineView && timelineView !== 'hours') params.set('tl', timelineView);
  if (scopeAppId) params.set('scope', String(scopeAppId));
  if (selectedAppId) params.set('app', String(selectedAppId));
  return params;
}

function hashFor(route) {
  const query = currentQuery().toString();
  return `#/${route}${query ? `?${query}` : ''}`;
}

/** URL -> store。用户手改地址、前进后退都走这里。 */
export function applyFromHash() {
  const { route, params } = parseHash();
  applying = true;
  try {
    const range = params.get('range') || 'day';
    setState('period', {
      range,
      date: params.get('date') || null,
      start: params.get('start') || null,
      end: params.get('end') || null,
    });
    setState('metric', params.get('metric') || 'press_count');
    setState('timelineView', params.get('tl') || 'hours');
    setState('scopeAppId', toId(params.get('scope')));
    setState('selectedAppId', toId(params.get('app')));
    setState('route', route);
  } finally {
    applying = false;
  }
}

function toId(value) {
  const id = Number.parseInt(value ?? '', 10);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export function go(route) {
  if (!ROUTES.includes(route) || getState().route === route) return;
  history.pushState(null, '', hashFor(route));
  setState('route', route);
}

/** store -> URL，静默。视图切换之外的一切状态变化都用它。 */
function syncHash() {
  if (applying) return;
  const next = hashFor(getState().route);
  if (next !== window.location.hash) history.replaceState(null, '', next);
}

export function start() {
  window.addEventListener('hashchange', applyFromHash);
  window.addEventListener('popstate', applyFromHash);
  // 数组字面量的元素类型要收窄成切片名，否则 subscribe 收到的是 string。
  const slices = /** @type {const} */ ([
    'period', 'metric', 'timelineView', 'scopeAppId', 'selectedAppId',
  ]);
  for (const slice of slices) {
    subscribe(slice, syncHash);
  }
  subscribe('route', syncHash);
  applyFromHash();
}
