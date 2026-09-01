// 365 天日历热图。**DOM 而非 canvas**：一次 DocumentFragment 构建 + CSS 变量着色，
// 于是主题切换零成本、悬停命中由浏览器负责、屏幕阅读器能逐格读到 aria-label
// （06 文档 §14 的"365 天日历渲染 < 50ms"）。
import { h, renderKeyed } from '../core/dom.js';
import { formatCount } from '../domain/format.js';
import { fromISO } from '../domain/period.js';
import { heatLevel, heatRatio } from '../domain/metrics.js';

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];

/**
 * buckets: [{bucket: 'YYYY-MM-DD', press_count, ...}]，gaps 是 Set。
 * weekStartsOn 与后端 ui.week_starts_on 同义（0 = 周一）。
 */
export function calendarHeatmap(container, { weekStartsOn = 0, metric = 'press_count', onSelect = null } = {}) {
  const axis = h('div', { class: 'weekday-axis' });
  const grid = h('div', {
    class: 'heatgrid',
    attrs: { role: 'group', 'aria-label': '每日活跃度' },
  });
  const wrap = h('div', { class: 'calendar' }, axis, grid);
  container.replaceChildren(wrap);

  for (let index = 0; index < 7; index += 1) {
    const weekday = WEEKDAYS[(index + weekStartsOn) % 7];
    axis.append(h('span', { text: index % 2 === 0 ? weekday : '' }));
  }

  if (onSelect) {
    grid.addEventListener('click', (event) => {
      const cell = event.target.closest('.heat-cell');
      if (cell?.dataset.bucket) onSelect(cell.dataset.bucket);
    });
  }

  return {
    update(buckets, scale, gaps) {
      const items = padToWeeks(buckets || [], weekStartsOn);
      renderKeyed(
        grid,
        items,
        (item) => item.key,
        () => h('div', { class: 'heat-cell' }),
        (node, item) => paint(node, item, scale, gaps, metric),
      );
    },
    destroy() {
      container.replaceChildren();
    },
  };
}

/** 首尾补空格子，让第一列从"周起始日"开始，否则整张图会错位一天。 */
function padToWeeks(buckets, weekStartsOn) {
  if (!buckets.length) return [];
  const first = fromISO(buckets[0].bucket);
  if (!first) return buckets.map((item) => ({ ...item, key: item.bucket }));
  // getDay(): 0 = 周日。转成"周一 = 0"再套用 weekStartsOn。
  const mondayIndex = (first.getDay() + 6) % 7;
  const offset = (mondayIndex - weekStartsOn + 7) % 7;
  const padded = [];
  for (let index = 0; index < offset; index += 1) {
    padded.push({ key: `pad-${index}`, empty: true });
  }
  for (const item of buckets) padded.push({ ...item, key: item.bucket });
  return padded;
}

function paint(node, item, scale, gaps, metric) {
  if (item.empty) {
    node.dataset.empty = 'true';
    node.removeAttribute('aria-label');
    delete node.dataset.bucket;
    return;
  }
  delete node.dataset.empty;
  node.dataset.bucket = item.bucket;
  const isGap = Boolean(gaps?.has(item.bucket));
  if (isGap) node.dataset.gap = 'true';
  else delete node.dataset.gap;
  const value = Number(item[metric]) || 0;
  const ratio = isGap ? 0 : heatRatio(value, scale);
  node.style.setProperty('--heat', ratio.toFixed(4));
  node.dataset.level = String(heatLevel(ratio));
  node.setAttribute(
    'aria-label',
    isGap ? `${item.bucket}：无记录` : `${item.bucket}：${formatCount(value)} 次`,
  );
}
