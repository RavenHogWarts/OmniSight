// 应用范围选择器（06 文档 §7 改进 3、14 文档 §2.19 P3-4、§4.6 第 3 项）。
//
// "全部应用 / 某个应用"是同一张热力图的两种范围，不是两个功能。原 KeyTrace 把它放在
// 页面最下方一个独立面板里，还需要另外连上 TimeLens——合并后它只是筛选行上的一个按钮。
//
// **形式是图标网格而不是下拉框。** 选应用这件事本来是**认图标**而不是读文字：图标是
// 区分 Chrome 与 Edge 最快的线索，而 `<select>` 把它整个丢掉了。三个分组沿用前身
// KeyTrace 的那三个（最近使用 / 最多使用 / 正在运行）——它们分别回答"我刚才在用的那
// 个""我一直在用的那个""现在开着的那个"。
import { assetUrl } from '../core/api.js';
import { focusables, h, mount, setText } from '../core/dom.js';
import { getState, setState } from '../core/store.js';
import { formatDayTime, formatDuration, initialOf } from '../domain/format.js';
import { searchBox, segmented } from './controls.js';
import { icon } from './icon.js';

const GROUPS = [
  { id: 'recent', name: '最近使用' },
  { id: 'most_used', name: '最多使用' },
  { id: 'running', name: '正在运行' },
];
const FOCUSABLE = 'button:not([disabled]), input:not([disabled])';
/** 一屏最多铺多少格。再多就该用搜索，而不是往下滚一整屏图标。 */
const GRID_LIMIT = 60;

/**
 * @param {{ onChange?: ((appId: number | null) => void) | null }} [options]
 */
export function appPicker({ onChange = null } = {}) {
  /** @type {readonly any[]} */
  let apps = [];
  /** @type {ReadonlySet<number>} */
  let running = new Set();
  let group = 'recent';
  let query = '';

  const triggerIcon = h('span', { class: 'app-picker__mark' });
  const triggerText = h('span', { class: 'app-picker__name', text: '全部应用' });
  const trigger = h(
    'button',
    {
      class: 'button app-picker__trigger',
      type: 'button',
      attrs: { 'aria-haspopup': 'dialog', 'aria-expanded': 'false' },
      on: { click: () => (panel.hidden ? open() : close()) },
    },
    triggerIcon,
    triggerText,
    icon('down', { size: 14 }),
  );

  const search = searchBox({
    placeholder: '搜索应用',
    onInput: (value) => {
      query = value;
      renderGrid();
    },
  });
  const tabs = segmented(GROUPS, group, (id) => {
    group = id;
    tabs.setActive(id);
    renderGrid();
  }, { small: true, label: '应用分组' });
  const grid = h('div', { class: 'app-picker__grid' });
  const panel = h(
    'div',
    {
      class: 'app-picker__panel',
      hidden: true,
      attrs: { role: 'dialog', 'aria-label': '选择应用范围' },
    },
    h('div', { class: 'app-picker__head' }, search.root, tabs.root),
    grid,
  );
  const root = h(
    'div',
    { class: 'app-picker' },
    h('span', { class: 'muted text-sm', text: '范围' }),
    trigger,
    panel,
  );

  function open() {
    panel.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    // 每次打开都从完整网格开始：上一次的搜索词留着会让"全部应用"那一格不在场
    // （搜索时它按设计隐藏），于是想切回全部的人找不到入口。
    query = '';
    search.input.value = '';
    renderGrid();
    search.input.focus();
    document.addEventListener('keydown', onKeydown, true);
    document.addEventListener('pointerdown', onPointerDown, true);
  }

  function close() {
    if (panel.hidden) return;
    panel.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    document.removeEventListener('keydown', onKeydown, true);
    document.removeEventListener('pointerdown', onPointerDown, true);
    trigger.focus();
  }

  /** Esc 关闭、Tab 在弹层内循环——与抽屉同一套约定（06 文档 §13）。 */
  function onKeydown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'Tab') return;
    const items = focusables(panel, FOCUSABLE);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function onPointerDown(event) {
    if (!(event.target instanceof Node)) return;
    if (root.contains(event.target)) return;
    close();
  }

  function pick(appId) {
    setState('scopeAppId', appId);
    close();
    if (onChange) onChange(appId);
  }

  function ordered() {
    const list = [...apps];
    if (group === 'running') {
      // 只列**已记录过**的应用：running 里 app_id 为 null 的那些没有统计可看，
      // 拿它们去过滤热力图只会得到一张空图。
      return list
        .filter((app) => running.has(app.app_id))
        .sort((left, right) => stamp(right).localeCompare(stamp(left)));
    }
    if (group === 'most_used') {
      return list.sort((left, right) => num(right.total_seconds) - num(left.total_seconds));
    }
    return list.sort((left, right) => stamp(right).localeCompare(stamp(left)));
  }

  function renderGrid() {
    const needle = query.toLowerCase();
    const matched = ordered().filter((app) => !needle || haystack(app).includes(needle));
    const current = getState().scopeAppId;
    mount(
      grid,
      // "全部应用"是一个选项而不是一个清除按钮：它与其他格子并列，读者因此知道
      // 自己此刻处在两种范围中的哪一种。
      needle
        ? null
        : cell({
            key: 'all',
            active: !current,
            label: '全部应用',
            meta: `${apps.length} 个应用`,
            onPick: () => pick(null),
          }),
      ...matched.slice(0, GRID_LIMIT).map((app) =>
        cell({
          key: String(app.app_id),
          active: current === app.app_id,
          label: app.user_alias || app.display_name || app.process_name || `应用 ${app.app_id}`,
          meta: metaOf(app),
          iconUrl: app.icon_url ? assetUrl(app.icon_url) : '',
          onPick: () => pick(app.app_id),
        }),
      ),
      matched.length ? null : h('div', { class: 'app-picker__empty', text: emptyText(needle, group) }),
      matched.length > GRID_LIMIT
        ? h('div', { class: 'app-picker__empty', text: `还有 ${matched.length - GRID_LIMIT} 个，用搜索找` })
        : null,
    );
  }

  /** 副行随分组变：三个分组各自回答的问题不同，副行必须跟着换（KeyTrace 也是这样）。 */
  function metaOf(app) {
    if (group === 'running') return '窗口正在运行';
    if (group === 'most_used') return app.total_seconds_formatted || formatDuration(num(app.total_seconds));
    return app.last_seen_at ? `最近 ${formatDayTime(app.last_seen_at)}` : app.process_name || '';
  }

  function syncTrigger() {
    const current = getState().scopeAppId;
    const app = current ? apps.find((item) => item.app_id === current) : null;
    setText(triggerText, app ? app.user_alias || app.display_name : '全部应用');
    triggerIcon.replaceChildren();
    if (app) triggerIcon.append(markFor(app));
  }

  return {
    root,
    /**
     * `apps` 是 `/apps` 的行（带 icon_url / total_seconds / last_seen_at），
     * `runningIds` 是 `/apps/running` 里已记录应用的 id 集合。
     * @param {readonly any[]} nextApps
     * @param {Iterable<number>} [runningIds]
     */
    update(nextApps, runningIds = []) {
      apps = nextApps || [];
      running = new Set([...runningIds].filter((id) => typeof id === 'number'));
      const current = getState().scopeAppId;
      // 选中的应用在新周期里不存在了：如实回落到全部，而不是显示一个空的过滤。
      if (current && !apps.some((app) => app.app_id === current)) setState('scopeAppId', null);
      syncTrigger();
      if (!panel.hidden) renderGrid();
    },
    destroy() {
      close();
      root.replaceChildren();
    },
  };
}

/** @param {{ key: string, active: boolean, label: string, meta: string, iconUrl?: string, onPick: () => void }} spec */
function cell({ key, active, label, meta, iconUrl = '', onPick }) {
  const button = h(
    'button',
    {
      class: 'app-picker__cell',
      type: 'button',
      dataset: { key },
      attrs: { 'aria-pressed': String(active) },
      on: { click: onPick },
    },
    iconUrl || key !== 'all' ? markFor({ icon_url: iconUrl, display_name: label }) : icon('apps', { size: 18 }),
    h(
      'span',
      { class: 'app-picker__copy' },
      h('span', { class: 'app-picker__label', text: label }),
      h('span', { class: 'app-picker__meta', text: meta }),
    ),
  );
  return button;
}

/** 图标取不到就是首字母块——与应用列表同一条兜底路径。 */
function markFor(app) {
  const label = app.user_alias || app.display_name || '?';
  const url = app.icon_url ? (app.icon_url.startsWith('/') ? assetUrl(app.icon_url) : app.icon_url) : '';
  if (!url) return h('span', { class: 'app-picker__initial', text: initialOf(label) });
  const img = h('img', {
    class: 'app-picker__icon',
    src: url,
    attrs: { alt: '', loading: 'lazy', decoding: 'async' },
  });
  img.addEventListener('error', () => {
    img.replaceWith(h('span', { class: 'app-picker__initial', text: initialOf(label) }));
  });
  return img;
}

function emptyText(needle, group) {
  if (needle) return '没有匹配的应用';
  return group === 'running' ? '当前没有已记录的应用在运行' : '这段时间还没有应用记录';
}

function haystack(app) {
  return `${app.user_alias || ''} ${app.display_name || ''} ${app.process_name || ''}`.toLowerCase();
}

function stamp(app) {
  return String(app.last_seen_at || '');
}

function num(value) {
  return Number(value) || 0;
}
