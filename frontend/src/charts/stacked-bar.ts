// 分类堆叠柱：每小时的时长按应用类别分层（06 文档 §5 的活动时间线）。
import { formatDurationShort } from '../domain/format.ts';
import { cssFont, hatchPattern, niceMax } from './canvas.ts';
import { AXIS_LEFT, drawTimeAxis } from './axis.ts';
import type { ChartDescription, DrawFn } from './canvas.ts';
import type { MarkedBucket } from '../domain/buckets.ts';

// left 由 axis.ts 给（见 AXIS_LEFT）。原先是 44，比 panel-pair 少 8px——于是同一屏上
// 这张图与它的活动带在 1024px 下给出的小时刻度数不同（24 vs 12）。
const PAD = { top: 8, right: 8, bottom: 16, left: AXIS_LEFT };

export interface StackedBarData {
  buckets: readonly (MarkedBucket & { total?: number })[];
  caption?: string;
  summary?: string;
}

export const drawStackedBar: DrawFn<StackedBarData> = (ctx, box, data, palette) => {
  const buckets = data.buckets || [];
  if (!buckets.length) return;
  const plot = {
    x: PAD.left,
    y: PAD.top,
    w: Math.max(1, box.width - PAD.left - PAD.right),
    h: Math.max(1, box.height - PAD.top - PAD.bottom),
  };
  const max = niceMax(Math.max(...buckets.map((item) => item.total || 0)));

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
    ctx.fillText(formatDurationShort((max * step) / 2), plot.x - 6, y);
  }

  const slot = plot.w / buckets.length;
  const width = Math.max(1, Math.min(slot * 0.72, 30));
  const hatch = hatchPattern(ctx, palette.strong);

  buckets.forEach((item, index) => {
    const centre = plot.x + slot * (index + 0.5);
    const x = centre - width / 2;
    box.hits.push({ x: centre - slot / 2, y: plot.y, w: slot, h: plot.h, payload: item });
    if (item.gap) {
      if (hatch) ctx.fillStyle = hatch;
      ctx.fillRect(x, plot.y, width, plot.h);
      return;
    }
    let cursor = plot.y + plot.h;
    for (const part of item.parts || []) {
      const partHeight = max ? ((part.seconds || 0) / max) * plot.h : 0;
      if (partHeight <= 0) continue;
      ctx.fillStyle = palette.categories[part.category] || palette.categories.uncategorized;
      ctx.fillRect(x, cursor - partHeight, width, partHeight);
      cursor -= partHeight;
    }
  });

  drawTimeAxis(
    ctx,
    buckets.map((item) => String(item.label ?? '')),
    plot,
    plot.y + plot.h + 4,
    palette.faint,
  );
};

export function describeStackedBar(data: StackedBarData): ChartDescription | null {
  const buckets = data?.buckets || [];
  if (!buckets.length) return null;
  return {
    caption: data.caption || '每小时使用时长',
    summary: data.summary || '按类别分层的每小时使用时长',
    columns: ['时间', '时长'],
    rows: buckets.map((item) => [
      String(item.label ?? ''),
      item.gap ? '无记录' : formatDurationShort(item.total || 0),
    ]),
  };
}
