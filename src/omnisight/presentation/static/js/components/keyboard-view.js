// 键盘热力图组件（06 文档 §7、07 文档 §6.4、14 文档 §2.4/§2.5/§4.4）。
//
// 着色写的是 `data-level`，颜色由 CSS 按档位选（现状 KeyTrace 的 blendHex() 在 JS 里
// 硬算颜色，无法适配主题）。**离散五档而不是连续插值**：图例的色块与键面渲染的因此是
// 同一组值，读者能把一个键的颜色对回一个值区间。
//
// 可访问性（07 文档 §9）：104 个键**不**全部进 Tab 序（会淹没导航），整块键盘是一个
// tabstop，方向键在键位间移动，当前键由 aria-activedescendant 指出。按键动画区
// aria-hidden 不适用（键面本身就是数据），但动画**不**进 live region——每秒数次播报
// 会让屏幕阅读器无法使用。
import { on as busOn } from '../core/bus.js';
import { h, mount } from '../core/dom.js';
import { buildKeyboard, keyRows } from '../domain/keyboard-layout.js';
import { formatCount, formatPercent } from '../domain/format.js';
import { HEAT_BOUNDS, formatMetric, heatLevel, heatRatio, isSaturated, metricOf } from '../domain/metrics.js';
import { prefersReducedMotion } from '../core/theme.js';
import { icon } from './icon.js';
import { hide as hideTooltip, show as showTooltip } from './tooltip.js';

const PRESS_CLEAR_MS = 220;
/** 键面数值的字号地板。低于它宁可不印，也不印成 8px（14 文档 §2.5）。 */
const VALUE_MIN_PX = 11;
/** .key-cap__value 的字号系数，与 key-cap.css 里的 calc() 保持一致。 */
const VALUE_RATIO = 0.21;

/**
 * @param {Element} container
 * @param {{ onSelectKey?: ((keyId: string) => void) | null }} [options]
 */
export function keyboardView(container, { onSelectKey = null } = {}) {
  const board = h('div', { class: 'keyboard-wrap' });
  const legend = h('div', { class: 'heat-legend' });
  const orphans = h('div', { class: 'orphans', hidden: true });
  // 键盘是 DOM 而不是 canvas，所以它没有走 canvas.js 的 sr-only 表格孪生路径。
  // 这张折叠表补上，同时兜住"键面数值印不下"的场景（14 文档 §4.4）。
  const tableBody = h('tbody');
  const table = h(
    'details',
    { class: 'keyboard-table' },
    h('summary', { text: '表格视图' }),
    h(
      'div',
      { class: 'keyboard-table__scroll' },
      h(
        'table',
        { class: 'table' },
        h(
          'thead',
          null,
          h('tr', null, h('th', { text: '键位' }), h('th', { text: '次数' }), h('th', { text: '占比' }), h('th', { text: '均时长' })),
        ),
        tableBody,
      ),
    ),
  );
  mount(container, board, legend, orphans, table);

  /** @type {Map<string, HTMLElement>} */
  let nodes = new Map();
  /** @type {string[][]} */
  let rows = [];
  /** @type {Map<string, import('../types/api.js').HeatmapKey>} */
  let values = new Map();
  /** @type {import('../types/api.js').HeatScale | null} */
  let scale = null;
  let metric = 'press_count';
  let total = 0;
  let cursor = { row: 0, col: 0 };
  /** @type {HTMLElement | null} */
  let root = null;

  const reduced = prefersReducedMotion();

  const unsubscribePress = busOn('key:press', (keys) => {
    for (const keyId of keys) {
      const cap = nodes.get(keyId);
      if (!cap) continue;
      cap.classList.add('is-pressed');
      // 动画类在下一帧后移除。reduced-motion 下 CSS 已把过渡关掉，类照加不影响。
      window.setTimeout(() => cap.classList.remove('is-pressed'), reduced ? 60 : PRESS_CLEAR_MS);
    }
  });

  // --u 由 clamp(…, 3.0vw, …) 决定，窗口变化会改字号，因此值可见性要跟着重算。
  const resize = new ResizeObserver(() => syncValueVisibility());
  resize.observe(board);

  /** @param {import('../types/api.js').LayoutResponse | null | undefined} layout */
  function rebuild(layout) {
    const built = buildKeyboard(layout, {
      onKeyEnter: (keyId, cap, event) => {
        const entry = values.get(keyId);
        showTooltip({
          title: cap.getAttribute('aria-label') || keyId,
          rows: entry
            ? [
                ['次数', formatCount(entry.press_count)],
                ['占比', formatPercent(entry.percent)],
                ['均时长', formatMetric('duration_avg_ms', entry.duration_avg_ms)],
              ]
            : [['次数', '0']],
          x: /** @type {PointerEvent} */ (event).clientX,
          y: /** @type {PointerEvent} */ (event).clientY,
        });
      },
      onKeyLeave: () => hideTooltip(),
      onKeyActivate: onSelectKey ? (keyId) => onSelectKey(keyId) : null,
    });
    root = built.root;
    nodes = built.nodes;
    rows = keyRows(layout);
    cursor = { row: 0, col: 0 };
    root.addEventListener('keydown', handleKeydown);
    mount(board, root);
  }

  /** @param {KeyboardEvent} event */
  function handleKeydown(event) {
    /** @type {Record<string, [number, number]>} */
    const moves = {
      ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0],
    };
    if (event.key === 'Enter' || event.key === ' ') {
      const keyId = rows[cursor.row]?.[cursor.col];
      if (keyId && onSelectKey) {
        onSelectKey(keyId);
        event.preventDefault();
      }
      return;
    }
    const move = moves[event.key];
    if (!move) return;
    event.preventDefault();
    const nextRow = clamp(cursor.row + move[0], 0, rows.length - 1);
    const rowKeys = rows[nextRow] || [];
    const nextCol = clamp(cursor.col + move[1], 0, rowKeys.length - 1);
    cursor = { row: nextRow, col: nextCol };
    focusCursor();
  }

  function focusCursor() {
    const keyId = rows[cursor.row]?.[cursor.col];
    if (!keyId || !root) return;
    for (const cap of nodes.values()) cap.classList.remove('is-current');
    const cap = nodes.get(keyId);
    if (!cap) return;
    cap.classList.add('is-current');
    root.setAttribute('aria-activedescendant', `key-${keyId}`);
    // 焦点留在容器上，只移动 activedescendant——否则 Tab 序里会出现 104 个停靠点。
  }

  function paint() {
    const definition = metricOf(metric);
    for (const [keyId, cap] of nodes) {
      const entry = values.get(keyId);
      const value = entry ? Number(entry[metric]) || 0 : 0;
      const ratio = heatRatio(value, scale);
      // 档位直接决定颜色（CSS 按 data-level 选色）。0 是零态：键面不填色，
      // 于是"按过一次"与"从没按过"差 2.4:1 而不是 1.07:1（14 文档 §2.4）。
      cap.dataset.level = String(heatLevel(ratio));
      if (isSaturated(value, scale)) cap.dataset.saturated = 'true';
      else delete cap.dataset.saturated;
      // 键面上除填色外还印数值：色盲用户与打印场景都要可读（06 文档 §7 改进 2）。
      // 两个子节点由 domain/keyboard-layout.js 的 keyCap() 一起建出来，必然存在。
      const valueNode = /** @type {HTMLElement} */ (cap.querySelector('.key-cap__value'));
      const text = value ? definition.format(value) : '';
      if (valueNode.textContent !== text) valueNode.textContent = text;
      const label = /** @type {HTMLElement} */ (cap.querySelector('.key-cap__label')).textContent;
      const share = total && metric === 'press_count' ? `，占比 ${formatPercent((value / total) * 100)}` : '';
      cap.setAttribute('aria-label', `${label}，${definition.name} ${definition.format(value)}${share}`);
    }
    syncValueVisibility();
  }

  /**
   * 键面装不下 11px 的数值就整体藏起来（14 文档 §2.5）。
   *
   * 现状的判据是"窗口 < 1024px"，但真正决定字号的是 --u：1280px 窗口下键面数值只有
   * 8.6px、1100px 下 7.4px，都低于全站 11px 的下限，而窗口宽度那条规则一个都拦不住。
   * 这里改成按实际 --u 算，同一条规则管所有宽度。值印不下时，表格视图仍然给得出。
   */
  function syncValueVisibility() {
    if (!root) return;
    const unit = Number.parseFloat(getComputedStyle(root).getPropertyValue('--u')) || 0;
    // CSS 的 max() 会把字号托到 11px，但托上去就装不下——所以这里判断的是
    // "自然字号够不够 11px"，不够就不印。
    root.dataset.values = unit * VALUE_RATIO >= VALUE_MIN_PX ? 'on' : 'off';
  }

  function renderLegend() {
    const definition = metricOf(metric);
    const top = Number(scale?.p95) || 0;
    const max = Number(scale?.max) || 0;
    mount(
      legend,
      h('span', { text: '未按过' }),
      h(
        'span',
        { class: 'heat-legend__scale', attrs: { 'aria-hidden': 'true' } },
        ...[0, 1, 2, 3, 4, 5].map((level) =>
          h('span', {
            class: 'heat-legend__step',
            dataset: { level: String(level) },
            // 标出每一档的值区间上界：色块与键面是同一组变量，读者由此能把一个键的
            // 颜色对回一个值区间——这是离散五档相对连续插值的全部意义（14 文档 §2.4）。
            attrs: { title: level ? `≤ ${definition.format(top * HEAT_BOUNDS[level])}` : '未按过' },
          }),
        ),
      ),
      h('span', { text: definition.format(top) }),
      // p95 归一而不是最大值归一：空格键通常是第二名的 3 倍，用最大值会把其余键
      // 压成一片浅色，热力图读不出差异（06 文档 §7 改进 1）。
      h(
        'span',
        {
          class: 'card__hint',
          attrs: {
            title: `色阶按 p95（${definition.format(top)}）归一，超出的键饱和到最深并在右上角切一个缺口。最大值 ${definition.format(max)}。`,
            'aria-label': `色阶按 p95 归一，最大值 ${definition.format(max)}`,
          },
        },
        h('span', { text: 'p95 归一 ' }),
        icon('info', { size: 13 }),
      ),
    );
  }

  /** 表格孪生：每个键的完整读数，可复制（14 文档 §4.4）。 */
  function renderTable() {
    const definition = metricOf(metric);
    const list = [...values.values()]
      .filter((entry) => Number(entry[metric]) > 0)
      .sort((left, right) => Number(right[metric]) - Number(left[metric]));
    mount(
      tableBody,
      ...list.map((entry) =>
        h(
          'tr',
          null,
          h('td', { text: entry.label || entry.id }),
          h('td', { class: 'numeric', text: definition.format(Number(entry[metric]) || 0) }),
          h('td', { class: 'numeric', text: formatPercent(entry.percent) }),
          h('td', { class: 'numeric', text: formatMetric('duration_avg_ms', entry.duration_avg_ms) }),
        ),
      ),
    );
  }

  function renderOrphans(list) {
    if (!list?.length) {
      orphans.hidden = true;
      mount(orphans);
      return;
    }
    orphans.hidden = false;
    mount(
      orphans,
      h('div', { class: 'orphans__title', text: `不在当前布局中的键（${list.length}）` }),
      h(
        'div',
        { class: 'orphans__list' },
        ...list.map((key) =>
          h(
            'span',
            { class: 'key-chip' },
            h('b', { text: key.label || key.id }),
            h('span', { text: formatMetric(metric, key[metric] ?? key.press_count ?? 0) }),
          ),
        ),
      ),
    );
  }

  return {
    /** 布局变了才重建 DOM；热力数据不必重取——keys 按 id 匹配，与布局无关。 */
    setLayout(layout) {
      rebuild(layout);
      paint();
      focusCursor();
    },
    /** 键盘密度（标准 / 紧凑）。标准优先保证 11px 数值，紧凑优先不横向滚动。 */
    setDensity(density) {
      if (!root) return;
      if (density === 'compact') root.dataset.density = 'compact';
      else delete root.dataset.density;
      syncValueVisibility();
    },
    /** payload 是 /keyboard/heatmap 的响应。 */
    update(payload, activeMetric) {
      metric = activeMetric || payload.metric || 'press_count';
      scale = payload.scale || null;
      total = Number(payload.totals?.press_count) || 0;
      values = new Map((payload.keys || []).map((key) => [key.id, key]));
      paint();
      renderLegend();
      renderTable();
      renderOrphans(payload.orphan_keys);
    },
    destroy() {
      unsubscribePress();
      resize.disconnect();
      hideTooltip();
      container.replaceChildren();
    },
  };
}

function clamp(value, low, high) {
  if (high < low) return low;
  return Math.min(high, Math.max(low, value));
}
