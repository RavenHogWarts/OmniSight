// 活动带：**共享一条时间轴的上下两个面板**（14 文档 §2.1、§4.3）。
//
// 它替换的是双轴叠加。双轴的问题不是好不好看，是它会**编造相关性**：两套刻度各自
// niceMax 一次，对齐比例由两个最大值决定，也就是由数据决定——"这段时间两条线贴在
// 一起"是渲染巧合，换一个周期同样的关系会长成完全不同的样子。而且现状只标了时长
// 那一套刻度，按键折线根本没有轴。
//
// 上下两个面板各有自己的 y 刻度与刻度文字，共享 x 轴；一条十字准线贯穿两个面板，
// **一个浮层同时报两个值**。"看出两者关系"的正确实现是这个：读者对着一个时间点，
// 同时拿到两个数，而不是让两条线在一张图里假装可比。
//
// **准线画在两个面板之前**（`drawCrosshair`）：它的职责是把同一个 x 在两个面板之间连
// 起来，空白处与中缝里看得见就够了，柱子盖住的那一段不必显示。反过来把它压在最上层就是
// 在记号上多加一笔墨，与 §5.1「不给记号描边」是同一件事。
//
// 上面板可以按类别堆叠（前身 TimeLens 的 renderHourlyBars 就是这么做的，合并时丢了）：
// 有 parts 就分层，没有就画单色柱。
//
// **React 化只搬走了 DOM 那一半**：draw 与 describe 原样导出，由 charts/Chart.tsx 驱动。
import { formatCount, formatDurationShort } from '../domain/format.ts';
import { BAR_MAX_WIDTH, MARK_GAP, bar, cssFont, hatchPattern, niceMax } from './canvas.ts';
import { AXIS_LEFT, drawTimeAxis } from './axis.ts';
import type { ChartDescription, DrawBox, DrawFn, Palette } from './canvas.ts';
import type { MarkedBucket } from '../domain/buckets.ts';

// left 由 axis.ts 给（三张带轴的图共用一个数，否则标签密度会不一致——见 AXIS_LEFT）。
const PAD = { top: 10, right: 8, bottom: 18, left: AXIS_LEFT };
/** 两个面板之间的留白。共享 x 轴，所以中间只需要一条呼吸缝。 */
const SPLIT = 14;

export type PanelPairMode = 'both' | 'seconds' | 'presses' | 'kpm';

export interface PanelPairData {
  buckets: readonly MarkedBucket[];
  mode?: PanelPairMode;
  caption?: string;
  summary?: string;
}

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface PanelSpec {
  value: (item: MarkedBucket) => number;
  format: (value: number) => string;
  color: string;
  parts: boolean;
  slot: number;
  width: number;
  hatch: CanvasPattern | null;
}

export const drawPanelPair: DrawFn<PanelPairData> = (ctx, box, data, palette) => {
  const buckets = data.buckets || [];
  if (!buckets.length) return;
  const mode: PanelPairMode = data.mode || 'both';
  const plotX = PAD.left;
  const plotW = Math.max(1, box.width - PAD.left - PAD.right);
  const totalH = Math.max(1, box.height - PAD.top - PAD.bottom);
  const slot = plotW / buckets.length;
  // 数据换了而指针没动时上一帧的下标可能越界——那时不画准线，而不是把它画在错的位置上。
  const hover = box.hover >= 0 && box.hover < buckets.length ? box.hover : -1;

  // 「强度」是把两个量放到一根轴上的**合法**做法：取派生量 KPM，只画一条线一套刻度。
  if (mode === 'kpm') {
    const plot: Rect = { x: plotX, y: PAD.top, w: plotW, h: totalH };
    if (hover >= 0) drawCrosshair(ctx, palette, plot, slot, hover);
    drawKpm(ctx, box, buckets, palette, plot, slot, hover);
    drawXAxis(ctx, buckets, palette, plotX, plotW, PAD.top + totalH);
    return;
  }

  const both = mode === 'both';
  const topH = both ? Math.max(1, (totalH - SPLIT) * 0.56) : totalH;
  const bottomH = both ? Math.max(1, totalH - SPLIT - topH) : totalH;
  const topPanel: Rect = { x: plotX, y: PAD.top, w: plotW, h: topH };
  const bottomPanel: Rect = { x: plotX, y: PAD.top + topH + SPLIT, w: plotW, h: bottomH };

  const width = Math.max(1, Math.min(slot - MARK_GAP, BAR_MAX_WIDTH));
  const hatch = hatchPattern(ctx, palette.strong);

  // 贯穿上下两个面板与中缝，所以高度取 totalH 而不是某一个面板的高度。
  if (hover >= 0) {
    drawCrosshair(ctx, palette, { x: plotX, y: PAD.top, w: plotW, h: totalH }, slot, hover);
  }

  if (both || mode === 'seconds') {
    drawPanel(ctx, buckets, palette, topPanel, {
      value: (item) => item.seconds || 0,
      format: formatDurationShort,
      color: palette.time,
      parts: true,
      slot,
      width,
      hatch,
    });
  }
  if (both || mode === 'presses') {
    drawPanel(ctx, buckets, palette, both ? bottomPanel : topPanel, {
      value: (item) => item.presses || 0,
      format: formatCount,
      color: palette.keys,
      parts: false,
      slot,
      width,
      hatch,
    });
  }

  // 命中区跨越两个面板：一次悬停报出这个时间点上的所有值。
  buckets.forEach((item, index) => {
    box.hits.push({ x: plotX + slot * index, y: PAD.top, w: slot, h: totalH, payload: item });
  });

  drawXAxis(ctx, buckets, palette, plotX, plotW, PAD.top + totalH);
};

/** 一个面板：自己的 y 刻度 + 柱。刻度只取 0 / 半 / 满三档，避免与另一面板争视觉。 */
function drawPanel(
  ctx: CanvasRenderingContext2D,
  buckets: readonly MarkedBucket[],
  palette: Palette,
  plot: Rect,
  spec: PanelSpec,
): void {
  const max = niceMax(Math.max(...buckets.map(spec.value)));

  ctx.strokeStyle = palette.grid;
  ctx.lineWidth = 1;
  ctx.fillStyle = palette.faint;
  ctx.font = cssFont(11);
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let step = 0; step <= 2; step += 1) {
    const y = plot.y + plot.h - (plot.h * step) / 2;
    ctx.beginPath();
    ctx.moveTo(plot.x, Math.round(y) + 0.5);
    ctx.lineTo(plot.x + plot.w, Math.round(y) + 0.5);
    ctx.stroke();
    ctx.fillText(spec.format((max * step) / 2), plot.x - 6, y);
  }

  buckets.forEach((item, index) => {
    const centre = plot.x + spec.slot * (index + 0.5);
    const x = centre - spec.width / 2;
    // 缺口整格斜纹到顶，而不是画一根 0 高的柱子。测不到与没有必须长得不一样。
    if (item.gap) {
      if (spec.hatch) ctx.fillStyle = spec.hatch;
      ctx.fillRect(x, plot.y, spec.width, plot.h);
      return;
    }
    const value = spec.value(item);
    const barHeight = max ? (value / max) * plot.h : 0;
    if (barHeight <= 0) return;
    const parts = spec.parts ? item.parts || [] : [];
    if (parts.length) {
      // 类别堆叠：段间 2px 表面色间隙，不给记号描边（14 文档 §5.1）。
      let cursor = plot.y + plot.h;
      parts.forEach((part, partIndex) => {
        const partHeight = max ? ((part.seconds || 0) / max) * plot.h : 0;
        if (partHeight <= 0) return;
        ctx.fillStyle = palette.categories[part.category] || palette.categories.uncategorized;
        const isTop = partIndex === parts.length - 1;
        const gap = partIndex === 0 ? 0 : MARK_GAP;
        if (isTop) bar(ctx, x, cursor - partHeight, spec.width, partHeight - gap);
        else ctx.fillRect(x, cursor - partHeight, spec.width, Math.max(0, partHeight - gap));
        cursor -= partHeight;
      });
      return;
    }
    ctx.fillStyle = spec.color;
    bar(ctx, x, plot.y + plot.h - barHeight, spec.width, barHeight);
  });
}

function kpmOf(item: MarkedBucket): number {
  const minutes = (item.seconds || 0) / 60;
  return minutes > 0 ? (item.presses || 0) / minutes : 0;
}

/** 输入强度：一条 KPM 折线，一套刻度。 */
function drawKpm(
  ctx: CanvasRenderingContext2D,
  box: DrawBox,
  buckets: readonly MarkedBucket[],
  palette: Palette,
  plot: Rect,
  slot: number,
  hover: number,
): void {
  const kpm = buckets.map(kpmOf);
  const max = niceMax(Math.max(...kpm));

  ctx.strokeStyle = palette.grid;
  ctx.lineWidth = 1;
  ctx.fillStyle = palette.faint;
  ctx.font = cssFont(11);
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let step = 0; step <= 2; step += 1) {
    const y = plot.y + plot.h - (plot.h * step) / 2;
    ctx.beginPath();
    ctx.moveTo(plot.x, Math.round(y) + 0.5);
    ctx.lineTo(plot.x + plot.w, Math.round(y) + 0.5);
    ctx.stroke();
    ctx.fillText(formatCount(Math.round((max * step) / 2)), plot.x - 6, y);
  }

  ctx.strokeStyle = palette.keys;
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.beginPath();
  let started = false;
  buckets.forEach((item, index) => {
    const centre = plot.x + slot * (index + 0.5);
    // 缺口断线：把测不到的桶连起来等于编造数据。
    if (item.gap) {
      started = false;
      return;
    }
    const y = plot.y + plot.h - (max ? (kpm[index] / max) * plot.h : 0);
    if (!started) {
      ctx.moveTo(centre, y);
      started = true;
    } else ctx.lineTo(centre, y);
  });
  ctx.stroke();

  // 折线本身没有点标记，光有准线读者不知道这条线在这一刻落在哪个高度上。外圈用表面色把
  // 它从线里托出来，而不是给它描一圈墨（同 §5.1 那 2px 表面色间隙的思路）。
  if (hover >= 0 && !buckets[hover].gap) {
    const cx = plot.x + slot * (hover + 0.5);
    const cy = plot.y + plot.h - (max ? (kpm[hover] / max) * plot.h : 0);
    ctx.beginPath();
    ctx.arc(cx, cy, 4.5, 0, Math.PI * 2);
    ctx.fillStyle = palette.surface;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = palette.keys;
    ctx.fill();
  }

  buckets.forEach((item, index) => {
    box.hits.push({
      x: plot.x + slot * index,
      y: plot.y,
      w: slot,
      h: plot.h,
      payload: { ...item, kpm: kpm[index] },
    });
  });
}

/**
 * 十字准线（14 文档 §4.3）：一条竖线，贯穿上下两个面板与中间那道留白。
 *
 * 用 `--border-strong` 而不是度量色——它是参考线，不是数据。半像素偏移让这 1px 落在设备
 * 像素上，否则在 150% 缩放的 Windows 上会糊成两像素宽的灰带（同 canvas.ts 的格线）。
 */
function drawCrosshair(
  ctx: CanvasRenderingContext2D,
  palette: Palette,
  plot: Rect,
  slot: number,
  index: number,
): void {
  const x = Math.round(plot.x + slot * (index + 0.5)) + 0.5;
  ctx.strokeStyle = palette.strong;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x, plot.y);
  ctx.lineTo(x, plot.y + plot.h);
  ctx.stroke();
}

function drawXAxis(
  ctx: CanvasRenderingContext2D,
  buckets: readonly MarkedBucket[],
  palette: Palette,
  x: number,
  w: number,
  baseline: number,
): void {
  // 字体要在 drawTimeAxis 之前设好：抽稀按实测文字宽度做，而宽度取决于当前 ctx.font。
  ctx.font = cssFont(11);
  drawTimeAxis(
    ctx,
    buckets.map((item) => String(item.label ?? '')),
    { x, w },
    baseline + 4,
    palette.faint,
  );
}

export function describePanelPair(data: PanelPairData): ChartDescription | null {
  const buckets = data?.buckets || [];
  if (!buckets.length) return null;
  const mode: PanelPairMode = data.mode || 'both';
  if (mode === 'kpm') {
    return {
      caption: data.caption || '输入强度',
      summary: data.summary || `${buckets.length} 个时间桶的输入强度`,
      columns: ['时间', 'KPM'],
      rows: buckets.map((item) => [
        String(item.label ?? item.bucket ?? ''),
        item.gap ? '无记录' : formatCount(Math.round(kpmOf(item))),
      ]),
    };
  }
  const columns = ['时间'];
  if (mode !== 'presses') columns.push('屏幕时间');
  if (mode !== 'seconds') columns.push('按键');
  return {
    caption: data.caption || '活动带',
    summary: data.summary || `${buckets.length} 个时间桶的活动数据`,
    columns,
    rows: buckets.map((item) => {
      const row: (string | number)[] = [String(item.label ?? item.bucket ?? '')];
      if (mode !== 'presses') row.push(item.gap ? '无记录' : formatDurationShort(item.seconds || 0));
      if (mode !== 'seconds') row.push(item.gap ? '无记录' : formatCount(item.presses || 0));
      return row;
    }),
  };
}
