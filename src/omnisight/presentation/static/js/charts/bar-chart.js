// 柱状图 / 双轴叠加（06 文档 §5 要点 1：时长面积 + 按键折线画在同一时间轴上）。
//
// 双轴是合并后独有的表达：用户能直接看到"这段时间开着但没在动"。单独任一项目都画不出。
import { formatCount, formatDurationShort } from '../domain/format.js';
import { Chart, hatchPattern, niceMax } from './canvas.js';

const PAD = { top: 8, right: 8, bottom: 16, left: 34 };

/** data: { buckets: [{bucket, label, seconds, presses, gap}], mode: seconds|presses|both } */
export function barChart(container, { height = 150, onSelect = null, label = '' } = {}) {
  return new Chart(container, { height, onSelect, label, draw, describe });
}

function draw(ctx, box, data, palette) {
  const buckets = data.buckets || [];
  if (!buckets.length) return;
  const mode = data.mode || 'seconds';
  const plot = {
    x: PAD.left,
    y: PAD.top,
    w: Math.max(1, box.width - PAD.left - PAD.right),
    h: Math.max(1, box.height - PAD.top - PAD.bottom),
  };

  const showSeconds = mode === 'seconds' || mode === 'both';
  const showPresses = mode === 'presses' || mode === 'both';
  const maxSeconds = niceMax(Math.max(...buckets.map((item) => item.seconds || 0)));
  const maxPresses = niceMax(Math.max(...buckets.map((item) => item.presses || 0)));

  ctx.strokeStyle = palette.grid;
  ctx.lineWidth = 1;
  ctx.fillStyle = palette.faint;
  ctx.font = '10px sans-serif';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let step = 0; step <= 2; step += 1) {
    const y = plot.y + plot.h - (plot.h * step) / 2;
    ctx.beginPath();
    ctx.moveTo(plot.x, Math.round(y) + 0.5);
    ctx.lineTo(plot.x + plot.w, Math.round(y) + 0.5);
    ctx.stroke();
    const primary = showSeconds ? maxSeconds : maxPresses;
    const text = showSeconds
      ? formatDurationShort((primary * step) / 2)
      : formatCount((primary * step) / 2);
    ctx.fillText(text, plot.x - 6, y);
  }

  const slot = plot.w / buckets.length;
  const barWidth = Math.max(1, Math.min(slot * 0.7, 26));
  const hatch = hatchPattern(ctx, palette.strong);

  if (showSeconds) {
    buckets.forEach((item, index) => {
      const value = item.seconds || 0;
      const centre = plot.x + slot * (index + 0.5);
      const barHeight = maxSeconds ? (value / maxSeconds) * plot.h : 0;
      const x = centre - barWidth / 2;
      const y = plot.y + plot.h - barHeight;
      // 缺口整格斜纹到顶，而不是画一根 0 高的柱子。测不到与没有必须长得不一样。
      if (item.gap) {
        ctx.fillStyle = hatch;
        ctx.fillRect(x, plot.y, barWidth, plot.h);
      } else if (barHeight > 0) {
        ctx.fillStyle = palette.accent;
        roundRect(ctx, x, y, barWidth, barHeight, Math.min(3, barWidth / 2));
        ctx.fill();
      }
      box.hits.push({ x: centre - slot / 2, y: plot.y, w: slot, h: plot.h, payload: item });
    });
  }

  if (showPresses) {
    ctx.strokeStyle = palette.categories.communication;
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    buckets.forEach((item, index) => {
      const centre = plot.x + slot * (index + 0.5);
      const value = item.presses || 0;
      const y = plot.y + plot.h - (maxPresses ? (value / maxPresses) * plot.h : 0);
      if (index === 0) ctx.moveTo(centre, y);
      else ctx.lineTo(centre, y);
    });
    ctx.stroke();
    if (!showSeconds) {
      buckets.forEach((item, index) => {
        const centre = plot.x + slot * (index + 0.5);
        box.hits.push({ x: centre - slot / 2, y: plot.y, w: slot, h: plot.h, payload: item });
      });
    }
  }

  ctx.fillStyle = palette.faint;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const stride = Math.max(1, Math.ceil(buckets.length / Math.max(2, Math.floor(plot.w / 48))));
  buckets.forEach((item, index) => {
    if (index % stride) return;
    ctx.fillText(String(item.label ?? ''), plot.x + slot * (index + 0.5), plot.y + plot.h + 4);
  });
}

function roundRect(ctx, x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + w - radius, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
  ctx.lineTo(x + w, y + h);
  ctx.lineTo(x, y + h);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

function describe(data) {
  const buckets = data?.buckets || [];
  if (!buckets.length) return null;
  const mode = data.mode || 'seconds';
  const columns = ['时间'];
  if (mode !== 'presses') columns.push('时长');
  if (mode !== 'seconds') columns.push('按键');
  return {
    caption: data.caption || '活动时间线',
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
