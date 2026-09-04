// 对照条（14 文档 §2.18 的 P2-7、§4.3 第 2 项）。
//
// 它回答屏幕时间工具最该回答的那个问题：**这段时间算多还是算少。** 指标卡原来那条
// 迷你趋势线画的是"本周期内部"的桶（看"日"时是 24 个小时），与它上方的活动带同源，
// 因此给不出任何跨周期的参照；delta 那行文字也只说"比上期多多少"，说不出"这在最近
// 七天里排第几"。
//
// 形式是 dataviz 的 **emphasis**：当前那一根用度量色，其余去强调灰。不学前身那顶
// 橙色帽（TimeLens renderTrendBars 在选中柱顶压一条 #ff9f43）——它编码的是"选中"，
// 而选中已经由颜色表达了（14 文档 §11.3）。
import type { ChartDescription, DrawBox, DrawFn, Palette } from './canvas.ts';

const PAD = { top: 4, right: 2, bottom: 2, left: 2 };
/** 柱宽上限（14 文档 §5.1 的记号规格给的是 ≤24px）。 */
const BAR_MAX = 20;

export interface ContextBucket {
  bucket: string;
  label?: string;
  seconds?: number;
  presses?: number;
}

export interface ContextBarsData {
  buckets: readonly ContextBucket[];
  /** 哪一根是"当前"。用 bucket id 比较，而不是下标——桶可能不连续。 */
  current?: string;
}

export interface ContextBarsOptions {
  accent?: 'time' | 'keys';
  metric?: 'seconds' | 'presses';
  format?: (value: number) => string;
  label?: string;
}

/** 绘制函数工厂。`Chart` 只接受 `(ctx, box, data, palette)`，选项在这里闭包进去。 */
export function contextBarsDraw(options: ContextBarsOptions = {}): DrawFn<ContextBarsData> {
  const { accent = 'time', metric = 'seconds' } = options;
  return (ctx, box, data, colors) => draw(ctx, box, data, colors, accent, metric);
}

export function contextBarsDescribe(
  options: ContextBarsOptions = {},
): (data: ContextBarsData) => ChartDescription | null {
  const { metric = 'seconds', format = String, label = '' } = options;
  return (data) => {
    const buckets = data?.buckets || [];
    if (!buckets.length) return null;
    return {
      caption: label || '对照条',
      columns: ['时间', metric === 'presses' ? '按键' : '时长', ''],
      rows: buckets.map((item) => [
        String(item.label ?? item.bucket ?? ''),
        format(Number(item[metric]) || 0),
        item.bucket === data.current ? '当前' : '',
      ]),
    };
  };
}

function draw(
  ctx: CanvasRenderingContext2D,
  box: DrawBox,
  data: ContextBarsData,
  colors: Palette,
  accent: 'time' | 'keys',
  metric: 'seconds' | 'presses',
): void {
  const buckets = data.buckets || [];
  if (!buckets.length) return;
  const values = buckets.map((item) => Number(item[metric]) || 0);
  const top = Math.max(...values);
  const plot = {
    x: PAD.left,
    y: PAD.top,
    w: Math.max(1, box.width - PAD.left - PAD.right),
    h: Math.max(1, box.height - PAD.top - PAD.bottom),
  };
  const slot = plot.w / buckets.length;
  const width = Math.max(2, Math.min(slot - 3, BAR_MAX));
  const emphasis = accent === 'keys' ? colors.keys : colors.time;
  // 去强调灰用 --cat-uncategorized：它在两个主题下都是"在场但不抢眼"那一档，
  // 而 --text-tertiary 是文字色，用作填充在深色下会比背景还亮。
  const quiet = colors.categories.uncategorized;

  buckets.forEach((item, index) => {
    const value = values[index];
    const centre = plot.x + slot * (index + 0.5);
    const x = centre - width / 2;
    // 命中区占满整个槽位（含空桶）：0 也要能悬停，否则"那天到底是 0 还是没测"无从问起。
    box.hits.push({ x: centre - slot / 2, y: plot.y, w: slot, h: plot.h, payload: item });
    const current = item.bucket === data.current;
    // 最小 2px：0 也留一道底线，让"这一格在场但是 0"与"这一格不存在"分得开。
    const barHeight = top > 0 ? Math.max(value > 0 ? 3 : 2, (value / top) * plot.h) : 2;
    ctx.fillStyle = current ? emphasis : quiet;
    ctx.globalAlpha = current ? 1 : 0.5;
    ctx.beginPath();
    ctx.roundRect(x, plot.y + plot.h - barHeight, width, barHeight, Math.min(2, width / 2));
    ctx.fill();
    ctx.globalAlpha = 1;
  });
}
