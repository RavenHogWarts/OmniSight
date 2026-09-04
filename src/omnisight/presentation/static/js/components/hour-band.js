// 每小时应用图标带（16 文档 §A1，前身 TimeLens 的「每小时」面板）。
//
// **为什么它不能被类别堆叠替代**：堆叠柱回答"这一小时是哪一类"，图标带回答"是哪一
// 个"。一天里 Code / Cursor / 终端同属"开发"，在堆叠柱上是一根同色柱子，而"上午在
// Cursor、下午在终端"恰是用户要看的那件事。
//
// 与前身的三处差异：
//   1. 不做 3D 翻转。前身把它藏在「所有使用」卡的背面、靠右键翻面（14 文档 §4.1 末
//      已否掉那个交互：窄屏妥协，且 prefers-reduced-motion 下无从降级）。
//   2. 图标地址由后端的 `icon_url` 给（前端不拼），它是 null 时直接首字母块——不发
//      一个注定 204 的请求（04 文档 §6 结尾）。
//   3. `+N` 的时长与后端的 `other_seconds` 同源，不在前端二次求和。
import { assetUrl } from '../core/api.js';
import { h, mount, renderKeyed, setText } from '../core/dom.js';
import { formatDurationShort, formatPercent, initialOf } from '../domain/format.js';
import { hide as hideTooltip, show as showTooltip } from './tooltip.js';

/** 一个图标槽的宽度（图标 26px + 间距 8px），与 hour-band.css 里的值一致。 */
const ICON_SLOT = 34;
/** `+N` 那一格预留的宽度。 */
const MORE_SLOT = 40;
/** 还没量到宽度时的容量（面板隐藏、或 ResizeObserver 第一次回调之前）。 */
const CAPACITY_FALLBACK = 8;
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

/**
 * @param {Element} container
 * @returns {{ update: (data: { hours?: readonly any[], gap?: boolean }) => void, destroy: () => void }}
 */
export function hourBand(container) {
  const root = h('div', { class: 'hour-band' });
  mount(container, root);

  /** @type {readonly any[]} */
  let hours = [];
  let gap = false;
  let frame = 0;

  // 一行放几个图标要按实测宽度算，因此宽度一变就得重算（前身在 resize 里做同一件事）。
  const observer = new ResizeObserver(() => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      render();
    });
  });
  observer.observe(root);

  root.addEventListener('pointerover', (event) => {
    const target = /** @type {HTMLElement} */ (event.target);
    const cell = target.closest('[data-tip-title]');
    if (!(cell instanceof HTMLElement)) return;
    showTooltip({
      title: cell.dataset.tipTitle || '',
      rows: rowsFrom(cell),
      x: event.clientX,
      y: event.clientY,
    });
  });
  root.addEventListener('pointerleave', () => hideTooltip());

  function render() {
    if (gap) {
      mount(root, h('div', { class: 'hour-band__gap', text: '该时段没有采集记录（不是 0）' }));
      return;
    }
    const byHour = new Map(hours.map((item) => [item.hour, item]));
    // 容量按 apps 列的宽度算：整行减去小时标签那一列（CSS 里是 52px + 8px 间距）。
    // 量不到宽度时用兜底值而不是算出 NaN——面板在隐藏容器里渲染是常态（切视图的
    // 那一帧），而 NaN 会让整行的图标全折进 `+N`。
    const width = Math.max(0, (root.clientWidth || 0) - 60);
    const capacity = width
      ? Math.max(1, Math.floor((width - MORE_SLOT) / ICON_SLOT))
      : CAPACITY_FALLBACK;
    renderKeyed(
      root,
      HOURS.map((hour) => byHour.get(hour) || { hour, total_seconds: 0, apps: [], other_seconds: 0 }),
      (item) => item.hour,
      createRow,
      (node, item) => updateRow(node, item, capacity),
    );
  }

  return {
    /** hours 直接来自 `/usage/timeline`；gap 为真时整块换成说明，绝不画一片 0。 */
    update(data) {
      hours = data.hours || [];
      gap = Boolean(data.gap);
      render();
    },
    destroy() {
      if (frame) cancelAnimationFrame(frame);
      observer.disconnect();
      hideTooltip();
      root.replaceChildren();
    },
  };
}

function createRow() {
  return h(
    'div',
    { class: 'hour-band__row' },
    h('span', { class: 'hour-band__hour numeric' }),
    h('div', { class: 'hour-band__apps' }),
  );
}

function updateRow(node, item, capacity) {
  const [label, apps] = node.children;
  setText(label, `${String(item.hour).padStart(2, '0')}:00`);
  node.dataset.empty = String(!(Number(item.total_seconds) > 0));

  const list = [...(item.apps || [])].sort((left, right) => num(right.seconds) - num(left.seconds));
  const visible = list.slice(0, capacity);
  const hiddenCount = Math.max(0, list.length - visible.length);
  const otherSeconds = num(item.other_seconds);
  // `+N` 同时代表"这一行装不下的"和"后端 top 之外的"：两者都是"还有别的应用"，
  // 分成两个记号只会让人以为是两件事。
  const moreCount = hiddenCount + (otherSeconds > 0 ? 1 : 0);
  const moreSeconds = list.slice(capacity).reduce((sum, app) => sum + num(app.seconds), 0) + otherSeconds;

  mount(
    apps,
    ...visible.map((app) => iconCell(app, item)),
    moreCount
      ? h('span', {
          class: 'hour-band__more',
          text: `+${moreCount}`,
          dataset: {
            tipTitle: `另外 ${moreCount} 个应用`,
            tipDuration: formatDurationShort(moreSeconds),
          },
        })
      : null,
  );
}

/** 图标取不到就是首字母块——`icons` 能力缺失的机器上这是常态，不是异常。 */
function iconCell(app, hour) {
  const label = app.display_name || `应用 ${app.app_id}`;
  const cell = h('span', {
    class: 'hour-band__app',
    dataset: {
      tipTitle: label,
      tipDuration: formatDurationShort(num(app.seconds)),
      tipShare: formatPercent(num(app.percent)),
      appId: String(app.app_id),
    },
    attrs: { 'aria-label': `${String(hour.hour).padStart(2, '0')}:00 ${label} ${formatDurationShort(num(app.seconds))}` },
  });
  const url = app.icon_url ? assetUrl(app.icon_url) : '';
  if (!url) {
    cell.append(h('span', { class: 'hour-band__initial', text: initialOf(label) }));
    return cell;
  }
  const img = h('img', {
    class: 'hour-band__icon',
    src: url,
    attrs: { alt: '', loading: 'lazy', decoding: 'async' },
  });
  img.addEventListener('error', () => {
    img.replaceWith(h('span', { class: 'hour-band__initial', text: initialOf(label) }));
  });
  cell.append(img);
  return cell;
}

/** @param {HTMLElement} cell */
function rowsFrom(cell) {
  /** @type {[string, string][]} */
  const rows = [];
  if (cell.dataset.tipDuration) rows.push(['时长', cell.dataset.tipDuration]);
  if (cell.dataset.tipShare) rows.push(['占这一小时', cell.dataset.tipShare]);
  return rows;
}

function num(value) {
  return Number(value) || 0;
}
