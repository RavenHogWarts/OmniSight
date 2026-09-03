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
// 上面板可以按类别堆叠（前身 TimeLens 的 renderHourlyBars 就是这么做的，合并时丢了）：
// 有 parts 就分层，没有就画单色柱。
import { formatCount, formatDurationShort } from '../domain/format.js';
import { BAR_MAX_WIDTH, Chart, MARK_GAP, bar, cssFont, hatchPattern, niceMax } from './canvas.js';

const PAD = { top: 10, right: 8, bottom: 18, left: 40 };
/** 两个面板之间的留白。共享 x 轴，所以中间只需要一条呼吸缝。 */
const SPLIT = 14;

/**
 * data: {
 *   buckets: [{bucket, label, seconds, presses, parts?: [{category, seconds}], gap}],
 *   mode: 'both' | 'seconds' | 'presses' | 'kpm',
 * }
 */
export function panelPair(container, { height = 220, onSelect = null, label = '' } = {}) {
  return new Chart(container, { height, onSelect, label, draw, describe });
}

function draw(ctx, box, data, palette) {
  const buckets = data.buckets || [];
  if (!buckets.length) return;
  const mode = data.mode || 'both';
  const plotX = PAD.left;
  const plotW = Math.max(1, box.width - PAD.left - PAD.right);
  const totalH = Math.max(1, box.height - PAD.top - PAD.bottom);

  // 「强度」是把两个量放到一根轴上的**合法**做法：取派生量 KPM，只画一条线一套刻度。
  if (mode === 'kpm') {
    drawKpm(ctx, box, buckets, palette, { x: plotX, y: PAD.top, w: plotW, h: totalH });
    drawXAxis(ctx, buckets, palette, plotX, plotW, PAD.top + totalH);
    return;
  }

  const both = mode === 'both';
  const topH = both ? Math.max(1, (totalH - SPLIT) * 0.56) : totalH;
  const bottomH = both ? Math.max(1, totalH - SPLIT - topH) : totalH;
  const topPanel = { x: plotX, y: PAD.top, w: plotW, h: topH };
  const bottomPanel = { x: plotX, y: PAD.top + topH + SPLIT, w: plotW, h: bottomH };

  const slot = plotW / buckets.length;
  const width = Math.max(1, Math.min(slot - MARK_GAP, BAR_MAX_WIDTH));
  const hatch = hatchPattern(ctx, palette.strong);

  if (both || mode === 'seconds') {
    drawPanel(ctx, buckets, palette, both ? topPanel : topPanel, {
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
  const hitTop = PAD.top;
  const hitH = totalH;
  buckets.forEach((item, index) => {
    box.hits.push({ x: plotX + slot * index, y: hitTop, w: slot, h: hitH, payload: item });
  });

  drawXAxis(ctx, buckets, palette, plotX, plotW, PAD.top + totalH);
}

/** 一个面板：自己的 y 刻度 + 柱。刻度只取 0 / 半 / 满三档，避免与另一面板争视觉。 */
function drawPanel(ctx, buckets, palette, plot, spec) {
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
      ctx.fillStyle = spec.hatch;
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

/** 输入强度：一条 KPM 折线，一套刻度。 */
function drawKpm(ctx, box, buckets, palette, plot) {
  const kpm = buckets.map((item) => {
    const minutes = (item.seconds || 0) / 60;
    return minutes > 0 ? (item.presses || 0) / minutes : 0;
  });
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

  const slot = plot.w / buckets.length;
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

function drawXAxis(ctx, buckets, palette, x, w, baseline) {
  ctx.fillStyle = palette.faint;
  ctx.font = cssFont(11);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const slot = w / buckets.length;
  const stride = Math.max(1, Math.ceil(buckets.length / Math.max(2, Math.floor(w / 48))));
  buckets.forEach((item, index) => {
    if (index % stride) return;
    ctx.fillText(String(item.label ?? ''), x + slot * (index + 0.5), baseline + 4);
  });
}

function describe(data) {
  const buckets = data?.buckets || [];
  if (!buckets.length) return null;
  const mode = data.mode || 'both';
  if (mode === 'kpm') {
    return {
      caption: data.caption || '输入强度',
      summary: data.summary || `${buckets.length} 个时间桶的输入强度`,
      columns: ['时间', 'KPM'],
      rows: buckets.map((item) => {
        const minutes = (item.seconds || 0) / 60;
        const value = minutes > 0 ? (item.presses || 0) / minutes : 0;
        return [String(item.label ?? item.bucket ?? ''), item.gap ? '无记录' : formatCount(Math.round(value))];
      }),
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
      const row = [String(item.label ?? item.bucket ?? '')];
      if (mode !== 'presses') row.push(item.gap ? '无记录' : formatDurationShort(item.seconds || 0));
      if (mode !== 'seconds') row.push(item.gap ? '无记录' : formatCount(item.presses || 0));
      return row;
    }),
  };
}
