// 唯一入口（07 文档 §3）。做五件事，别的都不做：
//   1. 交接令牌、恢复主题、装上全局框架（横幅 / 状态点 / 周期栏）。
//   2. 路由：按 route 动态 import 视图模块，创建、挂载、取数、订阅渲染。
//   3. 统一事件委托：全页只有一个 click 监听器分发 data-action（彻底移除内联 onclick）。
//   4. 键盘快捷键（06 文档 §4.1）。
//   5. SSE 连接与失效重取。
//
// 视图模块的契约只有三样：`needs(state)` 声明要哪些数据、`render()` 画、`destroy()` 拆。
import { adoptToken, get as apiGet, messageOf } from './core/api.js';
import { on as busOn } from './core/bus.js';
import { closestFrom, h, mount, mountPoint } from './core/dom.js';
import { abortPending, fetchInto } from './core/loader.js';
import { ROUTES, go, start as startRouter } from './core/router.js';
import { getState, setState, subscribe } from './core/store.js';
import { connect as connectStream, startPolling } from './core/stream.js';
import { restore as restoreTheme, cycle as cycleTheme, watchSystem } from './core/theme.js';
import { mountBanners } from './components/degraded.js';
import { mountImportBanner, openImportWizard } from './components/import-wizard.js';
import { maybeShowOnboarding, openAbout } from './components/onboarding.js';
import { mountPeriodNav, step as stepPeriod, goToday } from './components/period-nav.js';
import { mountStatus } from './components/status-dot.js';
import { hide as hideTooltip, show as showTooltip } from './components/tooltip.js';
import { fail } from './components/toast.js';
import { rangeFromDefaultView } from './domain/metrics.js';
import { formatCount, formatDurationShort } from './domain/format.js';

const VIEW_MODULES = {
  overview: () => import('./views/overview.js'),
  apps: () => import('./views/apps.js'),
  keyboard: () => import('./views/keyboard.js'),
  insights: () => import('./views/insights.js'),
};

const viewRoot = mountPoint('view-root');
let active = null;
let activeRoute = null;
/** @type {ReturnType<typeof mountPeriodNav> | null} */
let periodNav = null;

/** 切换视图。上一个视图先 destroy——图表持有 ResizeObserver 与总线订阅，不拆会泄漏。 */
async function mountRoute(route) {
  if (activeRoute === route) return;
  const load = VIEW_MODULES[route] || VIEW_MODULES.overview;
  let module;
  try {
    module = await load();
  } catch (error) {
    fail('视图加载失败，请刷新页面');
    return;
  }
  if (active) active.destroy();
  activeRoute = route;
  active = module.create(viewRoot);
  syncTabs(route);
  // 视图级筛选进周期栏的右段，切视图时整体替换（14 文档 §4.1）。视图没有
  // 视图级筛选就传空——总览就是这一类。
  if (periodNav) periodNav.setFilters(active.filters ? active.filters() : []);
  refresh();
  active.render();
  // 焦点移到新视图的标题（07 文档 §9）：否则键盘用户切完视图仍停在标签栏上。
  const heading = /** @type {HTMLElement | null} */ (viewRoot.querySelector('#view-title'));
  if (heading) heading.focus();
  document.title = `${module.title} · OmniSight`;
}

function syncTabs(route) {
  for (const id of ROUTES) {
    const tab = document.getElementById(`tab-${id}`);
    if (tab) tab.setAttribute('aria-selected', String(id === route));
  }
  const panel = document.getElementById('view-root');
  if (panel) panel.setAttribute('aria-labelledby', `tab-${route}`);
}

/** 按当前状态重新取数。周期变了要 abort 上一批，否则旧响应会覆盖新数据。 */
function refresh({ abort = true } = {}) {
  if (!active) return;
  if (abort) abortPending();
  for (const request of active.needs(getState())) {
    fetchInto(request.key, request.path, request.params || {}, request.options || {});
  }
}

/** data-action 分发表。声明式意图写在 HTML/DOM 上，处理集中在这里（07 文档 §7）。 */
const ACTIONS = {
  'route:go': (dataset) => go(dataset.route),
  'theme:cycle': () => cycleTheme(),
  'settings:open': () => openSettingsDrawer(),
  'import:open': () => openImportWizard(),
  'about:open': () => openAbout(),
  'period:prev': () => stepPeriod(-1),
  'period:next': () => stepPeriod(1),
  'period:today': () => goToday(),
};

function installDelegation() {
  document.addEventListener('click', (event) => {
    const target = closestFrom(event, '[data-action]');
    if (!target) return;
    const handler = ACTIONS[target.dataset.action];
    if (handler) handler(target.dataset, event);
  });
}

/** 快捷键（06 文档 §4.1）。输入框里一律不拦截，否则用户没法在搜索框里打 4。 */
function installShortcuts() {
  document.addEventListener('keydown', (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const tag = (/** @type {Element | null} */ (event.target)?.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    const index = ['1', '2', '3', '4'].indexOf(event.key);
    if (index >= 0) {
      go(ROUTES[index]);
      return;
    }
    if (event.key === 'ArrowLeft') stepPeriod(-1);
    else if (event.key === 'ArrowRight') stepPeriod(1);
    else if (event.key === 't' || event.key === 'T') goToday();
    else if (event.key === '/') {
      const search = /** @type {HTMLElement | null} */ (document.querySelector('.search input'));
      if (search) {
        event.preventDefault();
        search.focus();
      }
    } else if (event.key === '?') showShortcutHelp();
  });
}

function showShortcutHelp() {
  /** @type {[string, string][]} */
  const rows = [
    ['1 - 4', '切换视图'],
    ['左 / 右', '上一个 / 下一个周期'],
    ['T', '回到今天'],
    ['/', '聚焦搜索'],
    ['方向键', '在键盘热力图上移动'],
  ];
  showTooltip({
    title: '键盘快捷键',
    rows,
    x: window.innerWidth / 2 - 120,
    y: window.innerHeight / 2 - 80,
  });
  window.setTimeout(hideTooltip, 4000);
}

/** 图表 tooltip：命中检测在图表里，内容与定位在这里统一（单例，见 06 文档 §10）。 */
function installChartTooltips() {
  document.addEventListener('chart:hover', (event) => {
    const { payload, x, y } = /** @type {CustomEvent} */ (event).detail;
    if (!payload) return;
    /** @type {[string, string | number][]} */
    const rows = [];
    if (payload.seconds !== undefined) rows.push(['时长', formatDurationShort(payload.seconds)]);
    if (payload.total !== undefined) rows.push(['时长', formatDurationShort(payload.total)]);
    if (payload.presses !== undefined) rows.push(['按键', formatCount(payload.presses)]);
    if (payload.kpm !== undefined) rows.push(['输入强度', `${(Number(payload.kpm) || 0).toFixed(1)} KPM`]);
    if (payload.value !== undefined && payload.percent !== undefined) {
      rows.push(['时长', formatDurationShort(payload.value)]);
      rows.push(['占比', `${(payload.percent || 0).toFixed(1)}%`]);
    }
    // 堆叠柱：段的高度只能看出相对大小，具体是哪一类多少必须能读到（14 文档 §4.3
    // 的"一个悬停浮层同时报两个值"推到堆叠这一层）。名字由数据带来，前端不查表。
    for (const part of payload.parts || []) {
      if (!(Number(part.seconds) > 0)) continue;
      rows.push([part.name || part.category, formatDurationShort(part.seconds)]);
    }
    showTooltip({
      title: payload.label || payload.name || payload.bucket || '',
      rows,
      // 缺口必须在 tooltip 里说明原因，光有斜纹用户不知道那是什么（06 文档 §4.2）。
      note: payload.gap ? '该时段没有采集记录（不是 0）' : '',
      x,
      y,
    });
  });
  document.addEventListener('chart:leave', () => hideTooltip());
}

async function openSettingsDrawer() {
  try {
    const [settings, status] = await Promise.all([apiGet('/settings'), apiGet('/status')]);
    setState('settings', settings);
    setState('status', status);
    const module = await import('./views/settings.js');
    module.openSettings(settings, status, () => {
      loadStatus();
      refresh({ abort: false });
    });
  } catch (error) {
    fail(messageOf(error, '打开设置失败'));
  }
}

async function loadStatus() {
  try {
    const status = await apiGet('/status');
    setState('status', status);
    setState('capabilities', status.capabilities || null);
    setState('degraded', status.degraded || []);
    return status;
  } catch (error) {
    // 状态取不到时不要把整页变成错误：各面板自己的错误态更有用。
    setState('degraded', [
      {
        code: 'status_unreachable',
        severity: 'error',
        title: '无法读取运行状态',
        detail: '采集进程可能已退出，或访问令牌已失效。图表显示的可能是缓存数据。',
        hint: '从托盘菜单重新打开仪表盘',
        // 后端的 DegradedNotice 一定带 docs（可为 null）。这条是前端造的，也得对齐——
        // 否则 components/degraded.js 里读 `notice.docs` 时它是 undefined 而不是 null。
        docs: null,
      },
    ]);
    return null;
  }
}

/** 首屏读一次设置：周起始日、默认周期、键盘布局都是**后端配置**，前端不猜。 */
async function loadPrefs() {
  try {
    const payload = await apiGet('/settings');
    setState('settings', payload);
    const settings = payload.settings || {};
    setState('prefs', {
      weekStartsOn: Number(valueOf(settings, 'ui.week_starts_on', 0)),
      defaultRange: rangeFromDefaultView(valueOf(settings, 'ui.default_view', 'daily')),
      keyboardLayout: String(valueOf(settings, 'ui.keyboard_layout', 'auto')),
      titlesRecorded: Boolean(valueOf(settings, 'privacy.record_window_titles', false)),
    });
    const theme = String(valueOf(settings, 'ui.theme', 'system'));
    if (theme !== getState().theme) {
      const { set } = await import('./core/theme.js');
      set(theme);
    }
  } catch (error) {
    // 设置读不到就用默认值，界面照常可用。
  }
}

/**
 * 读一条设置的当前值。
 * @param {Record<string, import('./types/api.js').SettingField>} settings
 * @param {string} key
 * @param {import('./types/api.js').SettingValue} fallback
 * @returns {import('./types/api.js').SettingValue}
 */
function valueOf(settings, key, fallback) {
  const spec = settings[key];
  return spec && spec.value !== null && spec.value !== undefined ? spec.value : fallback;
}

function installSubscriptions() {
  // 数据到位就重画。渲染在 rAF 里合并，所以一次批量写入只画一帧（07 文档 §6.5）。
  const rerender = () => {
    if (active) active.render();
  };
  subscribe('data', rerender);
  subscribe('loading', rerender);
  subscribe('errors', rerender);
  subscribe('capabilities', rerender);
  subscribe('degraded', rerender);
  subscribe('coverage', rerender);

  // route 的订阅**不在这里装**：首屏要先把 status/settings 读回来，否则会先用默认周期
  // 取一遍数据、再用配置里的周期取第二遍。装配顺序见 main()。
  subscribe('period', () => refresh());
  subscribe('metric', () => refresh());
  subscribe('scopeAppId', () => refresh());
  subscribe('timelineView', rerender);
  subscribe('selectedAppId', () => {
    if (active && active.onSelect) active.onSelect(getState().selectedAppId);
    else rerender();
  });
  subscribe('selectedKeyId', rerender);

  // SSE 说"有新数据了"。它不知道前端在看哪个周期，所以由前端决定要不要重取
  // （07 文档 §5.3）。看历史周期时不重取：那些数据不会再变。
  busOn('data:invalidated', () => {
    const meta = getState().periodMeta;
    if (!meta || meta.is_current) refresh({ abort: false });
  });
}

async function main() {
  const script = /** @type {HTMLScriptElement | null} */ (document.querySelector('script[data-token]'));
  const token = adoptToken(script ? script.dataset.token : '');
  restoreTheme();
  watchSystem();

  mountBanners(mountPoint('banners'));
  // 检测旧数据不阻塞启动（09 文档 §2.1）：结果晚一点到也没关系。
  mountImportBanner(mountPoint('banners'));
  mountStatus(mountPoint('status-host'));
  periodNav = mountPeriodNav(mountPoint('periodbar'));
  installDelegation();
  installShortcuts();
  installChartTooltips();
  installSubscriptions();

  if (!token) {
    mount(
      viewRoot,
      h(
        'div',
        { class: 'card' },
        h('h2', { text: '缺少访问令牌' }),
        h('p', {
          class: 'muted',
          text: '请从托盘菜单重新打开仪表盘。令牌只在打开时经 URL 交接一次，刷新后仍然有效。',
        }),
      ),
    );
    return;
  }

  // 顺序是刻意的：先读状态与配置，再让路由填 store，最后才装 route 订阅并挂载视图。
  // 这时 active 还是 null，所以中间几次 setState 触发的 refresh() 都是空转。
  //
  // `#about` 必须在 startRouter() 之前读走：路由不认识它，会把 hash 改写成
  // `#/overview?range=day`，之后就再也看不出用户是从托盘的「关于与隐私说明」进来的。
  const wantsAbout = window.location.hash.replace(/^#\/?/, '') === 'about';
  await Promise.all([loadStatus(), loadPrefs()]);
  startRouter();
  // 首次进入且 URL 没带 range 时，用配置里的默认周期（ui.default_view）。
  if (!window.location.hash.includes('range=')) {
    setState('period', { ...getState().period, range: getState().prefs.defaultRange });
  }
  subscribe('route', (route) => mountRoute(route));
  await mountRoute(getState().route);
  const settings = getState().settings;
  if (settings && !valueOf(settings.settings || {}, 'privacy.realtime_stream', true)) {
    // 用户关掉了实时流：直接进轮询，不去敲一个必然 404 的端点。
    startPolling();
  } else {
    connectStream();
  }

  // 首启说明放在最后：仪表盘已经画完，说明浮在它上面。它自己判断要不要出现
  // （后端的 `required`），不在这里猜（08 文档 §6.1）。
  if (wantsAbout) openAbout();
  else maybeShowOnboarding();
}

main();
