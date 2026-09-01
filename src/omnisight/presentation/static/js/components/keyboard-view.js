// 键盘热力图组件（06 文档 §7、07 文档 §6.4）。
//
// 着色写的是 CSS 变量 --heat，不是 style.background：深色模式换基色由 CSS 的 color-mix
// 负责，JS 因此完全不需要知道当前主题（现状 KeyTrace 的 blendHex() 在 JS 里硬算颜色，
// 无法适配主题）。
//
// 可访问性（07 文档 §9）：104 个键**不**全部进 Tab 序（会淹没导航），整块键盘是一个
// tabstop，方向键在键位间移动，当前键由 aria-activedescendant 指出。按键动画区
// aria-hidden 不适用（键面本身就是数据），但动画**不**进 live region——每秒数次播报
// 会让屏幕阅读器无法使用。
import { on as busOn } from '../core/bus.js';
import { h, mount } from '../core/dom.js';
import { buildKeyboard, keyRows } from '../domain/keyboard-layout.js';
import { formatCount, formatPercent } from '../domain/format.js';
import { formatMetric, heatLevel, heatRatio, isSaturated, metricOf } from '../domain/metrics.js';
import { prefersReducedMotion } from '../core/theme.js';
import { hide as hideTooltip, show as showTooltip } from './tooltip.js';

const PRESS_CLEAR_MS = 220;

export function keyboardView(container, { onSelectKey = null } = {}) {
  const board = h('div', { class: 'keyboard-wrap' });
  const legend = h('div', { class: 'heat-legend' });
  const orphans = h('div', { class: 'orphans', hidden: true });
  mount(container, board, legend, orphans);

  let nodes = new Map();
  let rows = [];
  let values = new Map();
  let scale = null;
  let metric = 'press_count';
  let total = 0;
  let cursor = { row: 0, col: 0 };
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
          x: event.clientX,
          y: event.clientY,
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

  function handleKeydown(event) {
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
      cap.style.setProperty('--heat', ratio.toFixed(4));
      cap.dataset.level = String(heatLevel(ratio));
      if (isSaturated(value, scale)) cap.dataset.saturated = 'true';
      else delete cap.dataset.saturated;
      // 键面上除填色外还印数值：色盲用户与打印场景都要可读（06 文档 §7 改进 2）。
      const valueNode = cap.querySelector('.key-cap__value');
      const text = value ? definition.format(value) : '';
      if (valueNode.textContent !== text) valueNode.textContent = text;
      const label = cap.querySelector('.key-cap__label').textContent;
      const share = total && metric === 'press_count' ? `，占比 ${formatPercent((value / total) * 100)}` : '';
      cap.setAttribute('aria-label', `${label}，${definition.name} ${definition.format(value)}${share}`);
    }
  }

  function renderLegend() {
    const definition = metricOf(metric);
    const top = Number(scale?.p95) || 0;
    const max = Number(scale?.max) || 0;
    mount(
      legend,
      h('span', { text: '0' }),
      h(
        'span',
        { class: 'heat-legend__scale', attrs: { 'aria-hidden': 'true' } },
        ...[0, 1, 2, 3, 4, 5].map((level) => h('span', { class: 'heat-legend__step', dataset: { level: String(level) } })),
      ),
      h('span', { text: definition.format(top) }),
      // p95 归一而不是最大值归一：空格键通常是第二名的 3 倍，用最大值会把其余键
      // 压成一片浅色，热力图读不出差异（06 文档 §7 改进 1）。
      h('span', {
        class: 'card__hint',
        text: `p95 归一 \u24d8`,
        attrs: {
          title: `色阶按 p95（${definition.format(top)}）归一，超出的键饱和到最深并加描边。最大值 ${definition.format(max)}。`,
        },
      }),
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
    /** payload 是 /keyboard/heatmap 的响应。 */
    update(payload, activeMetric) {
      metric = activeMetric || payload.metric || 'press_count';
      scale = payload.scale || null;
      total = Number(payload.totals?.press_count) || 0;
      values = new Map((payload.keys || []).map((key) => [key.id, key]));
      paint();
      renderLegend();
      renderOrphans(payload.orphan_keys);
    },
    destroy() {
      unsubscribePress();
      hideTooltip();
      container.replaceChildren();
    },
  };
}

function clamp(value, low, high) {
  if (high < low) return low;
  return Math.min(high, Math.max(low, value));
}
