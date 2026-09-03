// Canvas 图表的公共底座（06 文档 §11、07 文档 §6.3）。
//
// 修掉现状四个问题，每一个都在这一个文件里解决一次：
//   1. HiDPI 模糊 —— 现状 <canvas width="720">，在 150% 缩放的 Windows 上是糊的。
//   2. 固定宽度 —— 现状窗口变窄就被压扁；这里用 ResizeObserver 重绘。
//   3. 颜色硬编码在 JS —— 现状深色模式下图表还是浅色；这里从 CSS 变量读。
//   4. 无文字替代 —— 每个图配一张 sr-only 表格，屏幕阅读器可读、也能复制数据。
import { on as busOn } from '../core/bus.js';
import { h } from '../core/dom.js';

/** 从 CSS 变量取色。主题切换后重新取一次，JS 因此不需要知道当前是深色还是浅色。 */
export function cssColor(name, fallback = '#888') {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export function setupCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  // 主 canvas 同理：拿不到 2d 上下文的浏览器不在基线内（07 文档 §2）。
  const ctx = /** @type {CanvasRenderingContext2D} */ (canvas.getContext('2d'));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return { ctx, width, height };
}

/** 斜纹填充：能力缺失区间的唯一视觉编码（06 文档 §4.2 规则 1）。 */
export function hatchPattern(ctx, color) {
  const tile = document.createElement('canvas');
  tile.width = 6;
  tile.height = 6;
  // 6×6 的离屏 canvas 必然拿得到 2d 上下文，断言掉那个 null 分支。
  const tileCtx = /** @type {CanvasRenderingContext2D} */ (tile.getContext('2d'));
  tileCtx.strokeStyle = color;
  tileCtx.lineWidth = 1.2;
  tileCtx.beginPath();
  tileCtx.moveTo(-1, 7);
  tileCtx.lineTo(7, -1);
  tileCtx.moveTo(2, 8);
  tileCtx.lineTo(8, 2);
  tileCtx.stroke();
  return ctx.createPattern(tile, 'repeat');
}

/**
 * 一块命中区。`draw` 把它推进 `box.hits`，悬停与点击都按这个矩形判定。
 * @typedef {object} HitArea
 * @property {number} x
 * @property {number} y
 * @property {number} w
 * @property {number} h
 * @property {any} payload 交给 tooltip 与 onSelect 的原始数据
 */

/**
 * sr-only 表格的内容（06 文档 §11 第 3 点）。
 * @typedef {object} ChartDescription
 * @property {string} [caption]
 * @property {string} [summary]
 * @property {readonly string[]} columns
 * @property {readonly (readonly (string | number)[])[]} rows
 */

/**
 * 绘制上下文：`setupCanvas` 的返回值加上一个待填的命中区数组。
 * @typedef {object} DrawBox
 * @property {CanvasRenderingContext2D} ctx
 * @property {number} width
 * @property {number} height
 * @property {HitArea[]} hits
 */

/**
 * @typedef {object} ChartOptions
 * @property {(ctx: CanvasRenderingContext2D, box: DrawBox, data: any, colors: ReturnType<typeof palette>) => void} draw
 * @property {((data: any) => ChartDescription | null) | null} [describe]
 * @property {number} [height]
 * @property {((payload: any) => void) | null} [onSelect]
 * @property {string} [label]
 */

/**
 * 一个图表实例。
 *
 * `draw(ctx, box, data, palette)` 负责画，并把命中区推进 `box.hits`；
 * `describe(data)` 返回 `{ caption, columns, rows }` 供 sr-only 表格用。
 */
export class Chart {
  /**
   * @param {Element} container
   * @param {ChartOptions} options
   */
  constructor(container, { draw, describe, height = 150, onSelect = null, label = '' }) {
    this.container = container;
    this.draw = draw;
    this.describe = describe;
    this.onSelect = onSelect;
    /** @type {any} */
    this.data = null;
    /** @type {HitArea[]} */
    this.hits = [];
    /** @type {HitArea | null} */
    this.hovered = null;

    this.canvas = h('canvas', {
      attrs: { role: 'img', 'aria-label': label || '图表' },
      style: { height: `${height}px` },
    });
    this.table = h('div', { class: 'sr-only' });
    container.replaceChildren(this.canvas, this.table);

    this.observer = new ResizeObserver(() => this.render());
    this.observer.observe(this.canvas);
    // 主题切换后 CSS 变量变了，canvas 不会自己跟着变（06 文档 §11 第 2 点）。
    this.unsubscribeTheme = busOn('theme:changed', () => this.render());

    this.canvas.addEventListener('pointermove', (event) => this.handleMove(event));
    this.canvas.addEventListener('pointerleave', () => this.handleLeave());
    if (onSelect) {
      this.canvas.addEventListener('click', (event) => {
        const hit = this.hitAt(event);
        if (hit) onSelect(hit.payload);
      });
      this.canvas.style.cursor = 'pointer';
    }
  }

  /** @param {any} data */
  update(data) {
    this.data = data;
    this.render();
    this.renderTable();
  }

  render() {
    if (!this.data) return;
    /** @type {DrawBox} */
    const box = { ...setupCanvas(this.canvas), hits: [] };
    try {
      this.draw(box.ctx, box, this.data, palette());
    } catch (error) {
      console.error('图表绘制失败', error);
    }
    this.hits = box.hits;
  }

  renderTable() {
    if (!this.describe) return;
    const spec = this.describe(this.data);
    if (!spec) {
      this.table.replaceChildren();
      return;
    }
    const table = h(
      'table',
      null,
      h('caption', { text: spec.caption || '' }),
      h('thead', null, h('tr', null, ...spec.columns.map((name) => h('th', { text: name })))),
      h('tbody', null, ...spec.rows.map((row) => h('tr', null, ...row.map((cell) => h('td', { text: String(cell) }))))),
    );
    this.table.replaceChildren(table);
    // canvas 的 aria-label 给摘要，详细数据在紧邻的表格里（06 文档 §11 第 3 点）。
    if (spec.summary) this.canvas.setAttribute('aria-label', spec.summary);
  }

  /**
   * @param {{ clientX: number, clientY: number }} event
   * @returns {HitArea | null}
   */
  hitAt(event) {
    const rect = this.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    for (const hit of this.hits) {
      if (x >= hit.x && x <= hit.x + hit.w && y >= hit.y && y <= hit.y + hit.h) return hit;
    }
    return null;
  }

  /** @param {PointerEvent} event */
  handleMove(event) {
    const hit = this.hitAt(event);
    if (hit === this.hovered) {
      if (hit) this.emitTooltip(hit, event);
      return;
    }
    this.hovered = hit;
    if (hit) this.emitTooltip(hit, event);
    else this.handleLeave();
  }

  /**
   * @param {HitArea} hit
   * @param {{ clientX: number, clientY: number }} event
   */
  emitTooltip(hit, event) {
    this.container.dispatchEvent(
      new CustomEvent('chart:hover', {
        bubbles: true,
        detail: { payload: hit.payload, x: event.clientX, y: event.clientY },
      }),
    );
  }

  handleLeave() {
    this.hovered = null;
    this.container.dispatchEvent(new CustomEvent('chart:leave', { bubbles: true }));
  }

  destroy() {
    this.observer.disconnect();
    this.unsubscribeTheme();
    this.container.replaceChildren();
  }
}

/** 一次取齐所有会用到的颜色，避免在绘制循环里反复读 computed style。 */
export function palette() {
  const color = cssColor;
  return {
    accent: color('--accent', '#2f7cf6'),
    accentSubtle: color('--accent-subtle', '#e8f1fe'),
    text: color('--text-primary', '#1d1d1f'),
    muted: color('--text-secondary', '#5f5f66'),
    faint: color('--text-tertiary', '#6b6b73'),
    grid: color('--border-subtle', 'rgba(0,0,0,.1)'),
    strong: color('--border-strong', 'rgba(0,0,0,.28)'),
    surface: color('--surface-card', '#fff'),
    sunken: color('--surface-sunken', '#eee'),
    heat: [
      color('--heat-0', '#eee'),
      color('--heat-1', '#dbe8fb'),
      color('--heat-2', '#a8caf7'),
      color('--heat-3', '#6ba6f2'),
      color('--heat-4', '#2f7cf6'),
      color('--heat-5', '#1a56b8'),
    ],
    categories: {
      productivity: color('--cat-productivity', '#2f7cf6'),
      communication: color('--cat-communication', '#16a394'),
      entertainment: color('--cat-entertainment', '#f2933c'),
      development: color('--cat-development', '#7c62e0'),
      system: color('--cat-system', '#8b8b91'),
      uncategorized: color('--cat-uncategorized', '#b4b4bb'),
    },
  };
}

/**
 * 轴刻度：只取 3 到 5 个整齐的值，不做通用的 nice-number 算法。
 * @param {number} value
 * @returns {number}
 */
export function niceMax(value) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const scaled = value / magnitude;
  const step = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return step * magnitude;
}
