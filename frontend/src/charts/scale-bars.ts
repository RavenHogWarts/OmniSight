// 单序列柱图：一个时间尺度上的一个指标（17 文档 §13 的「时间热力图改成筛选」）。
//
// 为什么不复用现有的三个：
//
//   `panel-pair`   上下两个面板 + 共享轴，它的下面板写死用 `formatCount` 格式化
//                  ——把"累计时长"塞进 `presses` 字段会让轴与浮层都读成"次数"
//   `stacked-bar`  只画 `parts`（按类别分层），没有 parts 时它什么都不画
//   `context-bars` 卡上的迷你对照条，没有轴也没有标签
//
// 这里要的是"一根轴 + 一组柱 + 会按当前指标格式化的刻度"，因此单独一支。格式化函数
// 由调用方注入（`domain/metrics.ts` 的 `formatMetric`），于是 次数 / 累计时长 / 均时长 /
// 最长按压 四个指标的刻度与浮层都说得对。
//
// 缺口仍然是斜纹而不是 0（06 文档 §4.2 规则 1）；柱只有数据端有圆角（14 文档 §5.1）。
import { BAR_MAX_WIDTH, bar, cssFont, hatchPattern, niceMax } from './canvas.ts';
import { AXIS_LEFT, drawTimeAxis } from './axis.ts';
import type { ChartDescription, DrawBox, DrawFn, Palette } from './canvas.ts';

// left 由 axis.ts 给（见 AXIS_LEFT）。原先是 48——按键数到五位数、或 "1.20s" 这类时长
// 都逼近它，而它与另两张图不同还会让标签密度对不上。
const PAD = { top: 10, right: 8, bottom: 20, left: AXIS_LEFT };

export interface ScaleBucket {
  bucket: string;
  label?: string;
  /** 已经按当前指标取好的值。图表不认识"指标"这件事。 */
  value: number;
  gap?: boolean;
}

export interface ScaleBarsData {
  buckets: readonly ScaleBucket[];
  /** 这一列数是什么（"次数" / "累计时长"…）。进浮层与 sr-only 表头。 */
  valueLabel: string;
  caption?: string;
  summary?: string;
}

export interface ScaleBarsOptions {
  /** 通常是 `(v) => formatMetric(metric, v)`。 */
  format: (value: number) => string;
  /** 度量色：按键是色阶中段，时长是蓝（14 文档 §3.2）。 */
  accent?: 'keys' | 'time';
}

export function scaleBarsDraw(options: ScaleBarsOptions): DrawFn<ScaleBarsData> {
  const { format, accent = 'keys' } = options;
  return (ctx, box, data, palette) => draw(ctx, box, data, palette, format, accent);
}

export function scaleBarsDescribe(
  options: ScaleBarsOptions,
): (data: ScaleBarsData) => ChartDescription | null {
  const { format } = options;
  return (data) => {
    const buckets = data?.buckets || [];
    if (!buckets.length) return null;
    return {
      caption: data.caption || '',
      summary: data.summary || '',
      columns: ['时间', data.valueLabel],
      rows: buckets.map((item) => [
        String(item.label ?? item.bucket ?? ''),
        item.gap ? '无记录' : format(item.value || 0),
      ]),
    };
  };
}

function draw(
  ctx: CanvasRenderingContext2D,
  box: DrawBox,
  data: ScaleBarsData,
  palette: Palette,
  format: (value: number) => string,
  accent: 'keys' | 'time',
): void {
  const buckets = data.buckets || [];
  if (!buckets.length) return;
  const plot = {
    x: PAD.left,
    y: PAD.top,
    w: Math.max(1, box.width - PAD.left - PAD.right),
    h: Math.max(1, box.height - PAD.top - PAD.bottom),
  };
  const max = niceMax(Math.max(...buckets.map((item) => item.value || 0)));
  const slot = plot.w / buckets.length;
  // 柱宽上限 24px（14 文档 §5.1）；下限 1px，让 365 根柱仍然各占一列而不是连成一片。
  const width = Math.max(1, Math.min(slot - 2, BAR_MAX_WIDTH));
  const hatch = hatchPattern(ctx, palette.strong);
  const fill = accent === 'time' ? palette.time : palette.keys;

  // ── y 轴：三条格线 + 右对齐刻度文字 ──────────────────────────────────
  ctx.font = cssFont(11);
  ctx.strokeStyle = palette.grid;
  ctx.fillStyle = palette.faint;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let step = 0; step <= 2; step += 1) {
    const y = plot.y + plot.h - (plot.h * step) / 2;
    ctx.beginPath();
    ctx.moveTo(plot.x, Math.round(y) + 0.5);
    ctx.lineTo(plot.x + plot.w, Math.round(y) + 0.5);
    ctx.stroke();
    ctx.fillText(format((max * step) / 2), plot.x - 6, y);
  }

  // ── 柱 ────────────────────────────────────────────────────────────
  buckets.forEach((item, index) => {
    const centre = plot.x + slot * (index + 0.5);
    const x = centre - width / 2;
    // 命中区占满整个槽位（含空桶）：0 也要能悬停，否则"那天到底是 0 还是没测"无从问起。
    box.hits.push({
      x: centre - slot / 2,
      y: plot.y,
      w: slot,
      h: plot.h,
      payload: {
        label: item.label ?? item.bucket,
        gap: item.gap,
        reading: { label: data.valueLabel, text: format(item.value || 0) },
      },
    });
    if (item.gap) {
      if (hatch) ctx.fillStyle = hatch;
      ctx.fillRect(x, plot.y, width, plot.h);
      return;
    }
    const value = item.value || 0;
    if (value <= 0) return;
    const height = Math.max(2, (value / max) * plot.h);
    ctx.fillStyle = fill;
    bar(ctx, x, plot.y + plot.h - height, width, height);
  });

  // ── x 轴标签（charts/axis.ts：实测宽度抽稀 + 末桶保号 + 首末贴边）──────
  // 字体已经在上面画 y 轴刻度时设成 cssFont(11)，抽稀量的就是那个字体的宽度。
  drawTimeAxis(
    ctx,
    buckets.map((item) => String(item.label ?? '')),
    plot,
    plot.y + plot.h + 5,
    palette.faint,
  );
}
