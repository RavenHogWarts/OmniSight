// 365 天日历热图。**DOM 而非 canvas**：一次 DocumentFragment 构建 + CSS 变量着色，
// 于是主题切换零成本、悬停命中由浏览器负责、屏幕阅读器能逐格读到 aria-label
// （06 文档 §14 的"365 天日历渲染 < 50ms"）。
import { closestFrom, h, renderKeyed } from '../core/dom.js';
import { formatCount } from '../domain/format.js';
import { fromISO } from '../domain/period.js';
import { heatLevel, heatRatio } from '../domain/metrics.js';

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];

/**
 * buckets: [{bucket: 'YYYY-MM-DD', press_count, ...}]，gaps 是 Set。
 * weekStartsOn 与后端 ui.week_starts_on 同义（0 = 周一）。
 */
/**
 * @param {Element} container
 * @param {{ weekStartsOn?: number, metric?: string, onSelect?: ((bucket: string) => void) | null }} [options]
 */
export function calendarHeatmap(container, { weekStartsOn = 0, metric = 'press_count', onSelect = null } = {}) {
  const months = h('div', { class: 'heatgrid__months', attrs: { 'aria-hidden': 'true' } });
  const axis = h('div', { class: 'weekday-axis' });
  const grid = h('div', {
    class: 'heatgrid',
    attrs: { role: 'group', 'aria-label': '每日活跃度' },
  });
  const wrap = h('div', { class: 'calendar' }, axis, h('div', { class: 'calendar__body' }, months, grid));
  container.replaceChildren(wrap);

  for (let index = 0; index < 7; index += 1) {
    const weekday = WEEKDAYS[(index + weekStartsOn) % 7];
    axis.append(h('span', { text: index % 2 === 0 ? weekday : '' }));
  }

  if (onSelect) {
    grid.addEventListener('click', (event) => {
      const cell = closestFrom(event, '.heat-cell');
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
      renderMonths(months, items);
    },
    destroy() {
      container.replaceChildren();
    },
  };
}

/**
 * 月份轴。365 个格子没有刻度就看不出六月在哪（14 文档 §5.2）。
 *
 * 格子是按列填的（`grid-auto-flow: column`，每列 7 天），所以第 n 个格子在第
 * `floor(n / 7) + 1` 列——每个月的第一天落在哪一列，标签就放在哪一列。
 */
function renderMonths(host, items) {
  /** @type {{ column: number, label: string }[]} */
  const marks = [];
  let previous = '';
  items.forEach((item, index) => {
    if (item.empty || !item.bucket) return;
    const month = item.bucket.slice(0, 7);
    if (month === previous) return;
    previous = month;
    marks.push({ column: Math.floor(index / 7) + 1, label: `${Number(month.slice(5, 7))} 月` });
  });
  // 相邻标签挨得太近会叠在一起（一个月约 4.3 列，标签约 3 列宽）。
  const spaced = marks.filter((mark, index) => index === 0 || mark.column - marks[index - 1].column >= 4);
  host.replaceChildren(
    ...spaced.map((mark) =>
      // style 走的是 setProperty（core/dom.js），它只认 dash-case——写 gridColumn
      // 会被静默丢弃，月份标签就会全部挤在第一列。
      h('span', { class: 'heatgrid__month', text: mark.label, style: { 'grid-column': String(mark.column) } }),
    ),
  );
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
  node.dataset.level = String(heatLevel(ratio));
  node.setAttribute(
    'aria-label',
    isGap ? `${item.bucket}：无记录` : `${item.bucket}：${formatCount(value)} 次`,
  );
}
