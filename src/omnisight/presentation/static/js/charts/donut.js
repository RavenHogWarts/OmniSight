// 环形图：类别时长占比。只在总和有意义的场合用，不用于按键分布。
import { formatDurationShort } from '../domain/format.js';
import { Chart } from './canvas.js';

/** data: { slices: [{id, name, value, percent}] } */
export function donut(container, { height = 160, onSelect = null, label = '' } = {}) {
  return new Chart(container, { height, onSelect, label, draw, describe });
}

function draw(ctx, box, data, palette) {
  const slices = (data.slices || []).filter((slice) => (slice.value || 0) > 0);
  const total = slices.reduce((sum, slice) => sum + (slice.value || 0), 0);
  const cx = box.width / 2;
  const cy = box.height / 2;
  const outer = Math.max(10, Math.min(cx, cy) - 4);
  const inner = outer * 0.62;

  if (!total) {
    ctx.strokeStyle = palette.grid;
    ctx.lineWidth = outer - inner;
    ctx.beginPath();
    ctx.arc(cx, cy, (outer + inner) / 2, 0, Math.PI * 2);
    ctx.stroke();
    return;
  }

  let angle = -Math.PI / 2;
  for (const slice of slices) {
    const sweep = ((slice.value || 0) / total) * Math.PI * 2;
    ctx.beginPath();
    ctx.fillStyle = palette.categories[slice.id] || palette.categories.uncategorized;
    ctx.arc(cx, cy, outer, angle, angle + sweep);
    ctx.arc(cx, cy, inner, angle + sweep, angle, true);
    ctx.closePath();
    ctx.fill();
    // 命中区用扇形中点的小方块近似。环形图的悬停精度不值得写点在扇形内的判定。
    const mid = angle + sweep / 2;
    const radius = (outer + inner) / 2;
    box.hits.push({
      x: cx + Math.cos(mid) * radius - 12,
      y: cy + Math.sin(mid) * radius - 12,
      w: 24,
      h: 24,
      payload: slice,
    });
    angle += sweep;
  }
}

function describe(data) {
  const slices = data?.slices || [];
  if (!slices.length) return null;
  return {
    caption: data.caption || '类别占比',
    summary: data.summary || '各类别时长占比',
    columns: ['类别', '时长', '占比'],
    rows: slices.map((slice) => [
      slice.name || slice.id,
      formatDurationShort(slice.value || 0),
      `${(slice.percent || 0).toFixed(1)}%`,
    ]),
  };
}
