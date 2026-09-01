// 应用视图（06 文档 §6）。
//
// 取数的一个刻意选择：**一次取回该周期的应用列表，搜索/排序/分页在前端做**。
//
// 理由是数量级——一个周期内出现过的应用是几十个（重度用户一年也就几百个），而
// `/usage/period` 没有 `q` 参数。若靠服务端分页，搜索就得走另一个端点（`/apps` 是
// 全期口径），于是"搜索结果的时长"与"列表里的时长"会是两个口径。前端过滤是让两者
// 一致的唯一办法，代价只是一次 500 行的响应。
//
// 管理元数据（excluded / merged_into / category_source）来自 `/apps`，按 app_id 合并。
// 这是旧版完全没有的能力：分类规则原先硬编码在 web_app.py 与 app-categories.js 两处，
// 用户改不了。
import { del, patch } from '../core/api.js';
import { h, mount, setText } from '../core/dom.js';
import { getState, setState } from '../core/store.js';
import { fetchInto } from '../core/loader.js';
import { formatCount } from '../domain/format.js';
import { renderAppRows } from '../components/app-list.js';
import { chip, checkbox, searchBox, segmented, switchControl } from '../components/controls.js';
import { capabilityNotice, emptyState, errorState, skeletonRows } from '../components/states.js';
import { capabilityOf, noticeFor } from '../components/degraded.js';
import { fail, ok } from '../components/toast.js';
import { card } from '../components/card.js';
import { periodParams } from '../domain/period.js';

export const title = '应用';

const PAGE_SIZE = 25;
const SORTS = [
  { id: 'seconds', name: '时长' },
  { id: 'presses', name: '按键' },
  { id: 'sessions', name: '次数' },
  { id: 'name', name: '名称' },
];

/** 把周期列表与管理元数据合并成一份。派生结果不入 store（07 文档 §4.3）。 */
function joinApps(periodPayload, appsPayload, { includeExcluded }) {
  const meta = new Map();
  for (const app of (appsPayload && appsPayload.apps) || []) meta.set(app.app_id, app);
  const rows = [];
  for (const app of (periodPayload && periodPayload.apps) || []) {
    rows.push({ ...(meta.get(app.app_id) || {}), ...app });
  }
  if (includeExcluded) {
    // 被排除的应用在周期列表里不存在（AppLens 已经把它们折走）。要让用户能取消排除，
    // 必须从 /apps 那一侧补进来，时长按 0 显示。
    const seen = new Set(rows.map((row) => row.app_id));
    for (const app of meta.values()) {
      if (app.excluded && !seen.has(app.app_id)) rows.push({ ...app, seconds: 0, presses: 0, percent: 0 });
    }
  }
  return rows;
}

function applyFilters(rows, { query, category, sort }) {
  const needle = query.toLowerCase();
  let items = rows;
  if (needle) {
    items = items.filter((row) => {
      const name = (row.user_alias || row.display_name || '').toLowerCase();
      const process = (row.process_name || '').toLowerCase();
      return name.includes(needle) || process.includes(needle);
    });
  }
  if (category) items = items.filter((row) => (row.category || 'uncategorized') === category);
  const sorted = [...items];
  sorted.sort((left, right) => {
    switch (sort) {
      case 'presses': return num(right.presses) - num(left.presses);
      case 'sessions': return num(right.session_count) - num(left.session_count);
      case 'name': return nameOf(left).localeCompare(nameOf(right), 'zh-CN');
      default: return num(right.seconds) - num(left.seconds);
    }
  });
  return sorted;
}

function num(value) {
  return Number(value) || 0;
}

function nameOf(row) {
  return row.user_alias || row.display_name || row.process_name || '';
}

export function create(root) {
  let query = '';
  let category = '';
  let sort = 'seconds';
  let includeExcluded = false;
  let page = 0;

  const search = searchBox({
    placeholder: '搜索应用',
    onInput: (value) => {
      query = value;
      page = 0;
      render();
    },
  });
  const sortTabs = segmented(SORTS, sort, (id) => {
    sort = id;
    page = 0;
    sortTabs.setActive(id);
    render();
  }, { small: true, label: '排序' });
  const excludedToggle = checkbox({
    label: '显示已排除',
    onChange: (value) => {
      includeExcluded = value;
      page = 0;
      reloadApps();
      render();
    },
  });
  const chipHost = h('div', { class: 'row row--wrap' });
  const count = h('span', { class: 'apps__count' });
  const listHost = h('div', { class: 'app-list' });
  const detailHost = h('div');
  const pager = h('div', { class: 'pager' });

  mount(
    root,
    h('h1', { class: 'view__title sr-only', text: '应用', attrs: { tabindex: '-1', id: 'view-title' } }),
    card(
      '应用',
      h('div', null, listHost, detailHost, pager),
      [search.root, sortTabs.root, excludedToggle],
      h('div', { class: 'row row--wrap' }, chipHost, h('span', { class: 'spacer' }), count),
    ),
  );

  // 事件委托：动态生成的行不必逐行绑定，重建 DOM 后也不必重新绑（07 文档 §7）。
  listHost.addEventListener('click', (event) => {
    const row = event.target.closest('.app-row');
    if (!row) return;
    const appId = Number.parseInt(row.dataset.appId, 10);
    setState('selectedAppId', getState().selectedAppId === appId ? null : appId);
  });
  listHost.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const row = event.target.closest('.app-row');
    if (!row) return;
    event.preventDefault();
    row.click();
  });

  function reloadApps() {
    fetchInto('appsMeta', '/apps', { limit: 500, include_excluded: includeExcluded });
  }

  function renderChips(catalog) {
    const items = [{ id: '', name: '全部' }, ...catalog];
    mount(
      chipHost,
      ...items.map((item) =>
        chip(item, (category || '') === item.id, (id) => {
          category = id;
          page = 0;
          render();
        }),
      ),
    );
  }

  function render() {
    const state = getState();
    const period = state.data.appsPeriod;
    const meta = state.data.appsMeta;
    const error = state.errors.appsPeriod || state.errors.appsMeta;

    if (!capabilityOf(state.capabilities, 'foreground')) {
      const notice = noticeFor(state.degraded, 'foreground');
      mount(listHost, capabilityNotice({
        title: (notice && notice.title) || '当前环境不支持识别前台应用',
        detail: (notice && notice.detail) || '键盘统计不受影响。这个面板依赖前台窗口信息，因此无法显示。',
        hint: (notice && notice.hint) || '',
      }));
      mount(detailHost);
      mount(pager);
      setText(count, '');
      return;
    }
    if (error) {
      mount(listHost, errorState({ message: error.message, onRetry: () => reload() }));
      return;
    }
    if (!period) {
      if (state.loading.appsPeriod) mount(listHost, skeletonRows(6));
      return;
    }

    renderChips((meta && meta.categories) || []);

    const rows = applyFilters(joinApps(period, meta, { includeExcluded }), { query, category, sort });
    const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    if (page >= pages) page = pages - 1;
    const slice = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
    const maxSeconds = Math.max(0, ...rows.map((row) => num(row.seconds)));
    const maxKpm = Math.max(0, ...rows.map((row) => num(row.kpm)));

    setText(count, `${rows.length} 个应用，合计 ${period.total_seconds_formatted || ''}`);
    if (!slice.length) {
      mount(listHost, emptyState({
        title: query ? '没有匹配的应用' : '这段时间没有使用记录',
        detail: query ? '换一个关键词试试' : '把范围切到全部即可查看历史数据',
      }));
    } else {
      renderAppRows(listHost, slice, { maxSeconds, maxKpm, expandedId: state.selectedAppId });
    }
    renderPager(pages);
    renderDetail(state, slice);
  }

  function renderPager(pages) {
    if (pages <= 1) {
      mount(pager);
      return;
    }
    mount(
      pager,
      h('button', {
        class: 'button', type: 'button', text: '上一页', disabled: page === 0,
        on: { click: () => { page -= 1; render(); } },
      }),
      h('span', { text: `${page + 1} / ${pages}` }),
      h('button', {
        class: 'button', type: 'button', text: '下一页', disabled: page >= pages - 1,
        on: { click: () => { page += 1; render(); } },
      }),
    );
  }

  /** 详情同页展开，插在被选中的那一行之后（06 文档 §6：不跳转）。 */
  function renderDetail(state, visible) {
    const appId = state.selectedAppId;
    if (!appId || !visible.some((row) => row.app_id === appId)) {
      mount(detailHost);
      return;
    }
    const detail = state.data.appDetail;
    const sessions = state.data.appSessions;
    if (!detail || detail.app.app_id !== appId) {
      mount(detailHost, h('div', { class: 'app-detail' }, skeletonRows(3)));
      return;
    }
    const app = detail.app;
    const catalog = (state.data.appsMeta && state.data.appsMeta.categories) || [];
    mount(
      detailHost,
      h(
        'div',
        { class: 'app-detail' },
        app.exe_path ? h('div', { class: 'app-detail__path', text: app.exe_path }) : null,
        renderTotals(detail.totals),
        renderKeyboardSummary(detail.keyboard),
        renderSessions(sessions),
        renderEditor(app, catalog),
      ),
    );
  }

  function renderTotals(totals) {
    const labels = [['day', '今天'], ['week', '本周'], ['month', '本月'], ['total', '总计']];
    return h(
      'dl',
      { class: 'app-detail__totals' },
      ...labels.map(([key, label]) => {
        const part = (totals && totals[key]) || {};
        return h(
          'div',
          { class: 'app-detail__total' },
          h('dt', { text: label }),
          h('dd', { text: part.seconds_formatted || '0秒' }),
          h('div', { class: 'text-xs dim numeric', text: `${formatCount(part.presses || 0)} 次按键` }),
        );
      }),
    );
  }

  function renderKeyboardSummary(keyboard) {
    if (!keyboard) return null;
    const keys = keyboard.top_keys || [];
    return h(
      'div',
      null,
      h('div', { class: 'text-sm muted', text: `键盘概况：${(keyboard.kpm || 0).toFixed(1)} KPM` }),
      h(
        'div',
        { class: 'app-detail__keys' },
        ...keys.map((key) =>
          h('span', { class: 'key-chip' }, h('b', { text: key.label }), h('span', { text: formatCount(key.press_count) })),
        ),
      ),
      h('button', {
        class: 'button',
        type: 'button',
        text: '查看完整键盘热力图',
        // 下钻到键盘视图并预设 app_id 过滤——原来这需要开两个程序（06 文档 §6）。
        on: {
          click: () => {
            setState('scopeAppId', getState().selectedAppId);
            setState('route', 'keyboard');
          },
        },
      }),
    );
  }

  function renderSessions(payload) {
    const sessions = (payload && payload.sessions) || [];
    if (!sessions.length) return null;
    return h(
      'div',
      null,
      h('div', { class: 'text-sm muted', text: `最近 ${sessions.length} 次访问` }),
      h(
        'div',
        { class: 'session-list' },
        // 一次访问一行，不是一个心跳切段一行——后者在重度使用下是每 10 秒一条
        // （03 文档的访问与会话段之分）。`/usage/sessions` 默认就按访问返回。
        ...sessions.map((session) =>
          h(
            'div',
            { class: 'session-row' },
            h('span', { text: clockRange(session) }),
            // 窗口标题只在 titles_included 为真时才有内容，后端决定，前端不猜。
            h('span', { class: 'truncate', text: session.window_title || '' }),
            h('span', { class: 'numeric', text: session.seconds_formatted }),
          ),
        ),
      ),
      payload.titles_included ? null : h('div', {
        class: 'card__hint',
        text: '窗口标题未记录（隐私设置默认关闭）',
      }),
    );
  }

  /** 管理操作。写操作会让缓存整体失效并递增 data_version，因此改完立刻能看到新名字。 */
  function renderEditor(app, catalog) {
    const alias = h('input', {
      class: 'control',
      type: 'text',
      value: app.user_alias || '',
      attrs: { placeholder: app.display_name || '', 'aria-label': '自定义名称', maxlength: '120' },
    });
    const categorySelect = h(
      'select',
      { class: 'control', attrs: { 'aria-label': '分类' } },
      ...catalog.map((item) =>
        h('option', { value: item.id, text: item.name, selected: item.id === app.category }),
      ),
    );
    const excluded = switchControl({
      checked: Boolean(app.excluded),
      label: '排除此应用',
      onChange: (value) => write({ excluded: value }, value ? '已排除' : '已取消排除'),
    });

    return h(
      'div',
      { class: 'app-actions' },
      h('label', { class: 'row' }, h('span', { class: 'text-sm muted', text: '别名' }), alias),
      h('button', {
        class: 'button button--primary',
        type: 'button',
        text: '保存别名',
        on: { click: () => write({ user_alias: alias.value.trim() || null }, '已更新名称') },
      }),
      h('label', { class: 'row' }, h('span', { class: 'text-sm muted', text: '分类' }), categorySelect),
      h('button', {
        class: 'button',
        type: 'button',
        text: '保存分类',
        on: { click: () => write({ category: categorySelect.value }, '已更新分类') },
      }),
      h('label', { class: 'row' }, h('span', { class: 'text-sm muted', text: '排除' }), excluded.root),
      app.merged_into
        ? h('button', {
            class: 'button',
            type: 'button',
            text: '取消合并',
            on: { click: () => unmerge(app.app_id) },
          })
        : null,
      app.merged_members && app.merged_members.length
        ? h('span', { class: 'text-xs dim', text: `已合并 ${app.merged_members.length} 个来源` })
        : null,
    );
  }

  async function write(body, message) {
    const appId = getState().selectedAppId;
    if (!appId) return;
    try {
      await patch(`/apps/${appId}`, body);
      ok(message);
      reload();
    } catch (error) {
      // field 由后端给（05 文档 §9），直接显示比"操作失败"有用得多。
      fail(error.field ? `${error.field}：${error.message}` : error.message);
    }
  }

  async function unmerge(appId) {
    try {
      await del(`/apps/${appId}/merge`);
      ok('已取消合并');
      reload();
    } catch (error) {
      fail(error.message);
    }
  }

  function reload() {
    const state = getState();
    const period = periodParams(state.period);
    fetchInto('appsPeriod', '/usage/period', { ...period, limit: 500 });
    reloadApps();
    if (state.selectedAppId) loadDetail(state.selectedAppId);
  }

  function loadDetail(appId) {
    fetchInto('appDetail', `/apps/${appId}`);
    fetchInto('appSessions', '/usage/sessions', {
      ...periodParams(getState().period),
      app_id: appId,
      limit: 20,
    });
  }

  return {
    needs(state) {
      const period = periodParams(state.period);
      const requests = [
        { key: 'appsPeriod', path: '/usage/period', params: { ...period, limit: 500 } },
        { key: 'appsMeta', path: '/apps', params: { limit: 500, include_excluded: includeExcluded } },
      ];
      if (state.selectedAppId) {
        requests.push({ key: 'appDetail', path: `/apps/${state.selectedAppId}` });
        requests.push({
          key: 'appSessions',
          path: '/usage/sessions',
          params: { ...period, app_id: state.selectedAppId, limit: 20 },
        });
      }
      return requests;
    },
    render,
    onSelect(appId) {
      if (appId) loadDetail(appId);
      render();
    },
    destroy() {
      root.replaceChildren();
    },
  };
}

function clockRange(session) {
  const start = String(session.start || '').slice(11, 16);
  const end = String(session.end || '').slice(11, 16);
  return start && end ? `${start}-${end}` : start || end;
}

export { joinApps, applyFilters };
