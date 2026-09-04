// Canvas 图表的公共底座（06 文档 §11、07 文档 §6.3）。
//
// 修掉现状四个问题，每一个都在这一个文件里解决一次：
//   1. HiDPI 模糊 —— 现状 <canvas width="720">，在 150% 缩放的 Windows 上是糊的。
//   2. 固定宽度 —— 现状窗口变窄就被压扁；ResizeObserver 在 Chart.tsx 里重绘。
//   3. 颜色硬编码在 JS —— 现状深色模式下图表还是浅色；这里从 CSS 变量读。
//   4. 无文字替代 —— 每个图配一张 sr-only 表格，屏幕阅读器可读、也能复制数据。
//
// **React 化之后这一层一行绘制代码都没改**（15 文档：用户选的"先包 React，再换
// ECharts"）。原先的 `Chart` 类拆成两半：DOM 与生命周期归 `Chart.tsx`，几何与取色
// 留在这里。好处是 14 文档 §5.1 那套记号规格（柱宽上限 24px、只有数据端圆角、2px
// 记号间隙）不必重新验收——画的是同一份代码。

/** 从 CSS 变量取色。主题切换后重新取一次，JS 因此不需要知道当前是深色还是浅色。 */
export function cssColor(name: string, fallback = '#888'): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/**
 * canvas 的字体串。轴标签必须与全站同源：现状写死 `10px sans-serif`，字号低于 11px
 * 下限、字族在 Windows 上落到 Arial，与 Segoe 不同源（14 文档 §2.7）。
 *
 * `--font-small` 是 ≤12px 的光学尺寸档（14 文档 §3.3），轴标签正属于这一档。
 */
export function cssFont(size = 11, weight: number | string = 400): string {
  return `${weight} ${size}px ${cssColor('--font-small', 'system-ui, sans-serif')}`;
}

/** 图表里柱子的统一宽度上限与圆角（14 文档 §5.1 的记号规格）。 */
export const BAR_MAX_WIDTH = 24;
export const BAR_RADIUS = 4;
/** 相邻记号之间留 2px 表面色间隙，而不是给记号描边。 */
export const MARK_GAP = 2;

/**
 * 只有数据端有圆角的柱子。基线端保持方角——柱子是从基线"长"出来的，
 * 两端都圆会让它看起来是漂浮的胶囊（14 文档 §5.1）。
 */
export function bar(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  radius = BAR_RADIUS,
): void {
  if (h <= 0) return;
  const r = Math.min(radius, w / 2, h);
  ctx.beginPath();
  ctx.moveTo(x, y + h);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h);
  ctx.closePath();
  ctx.fill();
}

export interface CanvasSurface {
  ctx: CanvasRenderingContext2D;
  width: number;
  height: number;
}

export function setupCanvas(canvas: HTMLCanvasElement): CanvasSurface {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  // 拿不到 2d 上下文的浏览器不在基线内（07 文档 §2）。
  const ctx = canvas.getContext('2d') as CanvasRenderingContext2D;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return { ctx, width, height };
}

/** 斜纹填充：能力缺失区间的唯一视觉编码（06 文档 §4.2 规则 1）。 */
export function hatchPattern(ctx: CanvasRenderingContext2D, color: string): CanvasPattern | null {
  const tile = document.createElement('canvas');
  tile.width = 6;
  tile.height = 6;
  // 6×6 的离屏 canvas 必然拿得到 2d 上下文，断言掉那个 null 分支。
  const tileCtx = tile.getContext('2d') as CanvasRenderingContext2D;
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

/** 一块命中区。`draw` 把它推进 `box.hits`，悬停与点击都按这个矩形判定。 */
export interface HitArea {
  x: number;
  y: number;
  w: number;
  h: number;
  /** 交给 tooltip 与 onSelect 的原始数据 */
  payload: unknown;
}

/** sr-only 表格的内容（06 文档 §11 第 3 点）。 */
export interface ChartDescription {
  caption?: string;
  summary?: string;
  columns: readonly string[];
  rows: readonly (readonly (string | number)[])[];
}

/** 绘制上下文：`setupCanvas` 的返回值加上一个待填的命中区数组。 */
export interface DrawBox extends CanvasSurface {
  hits: HitArea[];
}

export type Palette = ReturnType<typeof palette>;

/** 绘制函数的签名。所有图表模块导出的都是这个形状。 */
export type DrawFn<T> = (
  ctx: CanvasRenderingContext2D,
  box: DrawBox,
  data: T,
  colors: Palette,
) => void;

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
    // 度量色：时间是蓝，按键是色阶中段。--accent 只做交互，从不做图表填充
    // ——键帽上"蓝填色 = 高频"与"蓝描边 = 选中"本来是同一种蓝（14 文档 §3.2）。
    time: color('--data-time', '#2f7cf6'),
    keys: color('--data-keys', '#7e438c'),
    heat: [
      color('--heat-0', '#eeeef1'),
      color('--heat-1', '#cf8fde'),
      color('--heat-2', '#b375c2'),
      color('--heat-3', '#995ba6'),
      color('--heat-4', '#7e438c'),
      color('--heat-5', '#652a72'),
    ],
    categories: {
      development: color('--cat-development', '#be2038'),
      productivity: color('--cat-productivity', '#2f7cf6'),
      communication: color('--cat-communication', '#16a394'),
      entertainment: color('--cat-entertainment', '#d37819'),
      system: color('--cat-system', '#57575c'),
      uncategorized: color('--cat-uncategorized', '#919197'),
    } as Record<string, string>,
  };
}

/**
 * 轴刻度：只取 3 到 5 个整齐的值，不做通用的 nice-number 算法。
 */
export function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const scaled = value / magnitude;
  const step = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return step * magnitude;
}
