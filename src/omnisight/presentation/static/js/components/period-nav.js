// 周期栏（06 文档 §4.1、14 文档 §2.12/§4.1）。**在所有视图间共享状态**——从总览切到
// 键盘时选中的日期不变。这是旧版两个应用最割裂的地方：各自维护独立的日期状态，切换
// 程序等于重新选一次日期。
//
// 两处相对现状的改动：
//
// 1. **阅读顺序**。现状的挂载顺序是「翻页器 → 今天 → 自定义日期 → 范围预设」，也就是
//    用户最先要伸手的控件（范围预设）在最右边，而更细的自定义日期在它左边——先看到细
//    的、后看到粗的。现在是「范围 → 翻页器 → 今天 → 自定义…」，从粗到细。
// 2. **视图级筛选插槽**。键盘的范围/指标、应用的搜索/排序原本长在卡片头上，作用域却是
//    整个视图——看起来是那张卡的开关，实际改了整屏（14 文档 §2.8）。它们现在挂进这一
//    行的右段。界线：**改请求参数的控件在筛选行，改渲染方式的控件留在卡头。**
import { h, mount, setText } from '../core/dom.js';
import { formatClock } from '../domain/format.js';
import { getState, setState, subscribe } from '../core/store.js';
import { RANGES } from '../domain/metrics.js';
import { canGoForward, isPageable, shift, todayISO } from '../domain/period.js';
import { icon } from './icon.js';
import { segmented } from './controls.js';

/** 范围预设里不含 custom：它由「自定义…」按钮进入，不占一个常驻档位。 */
const PRESETS = RANGES.filter((range) => range.id !== 'custom');

export function mountPeriodNav(container) {
  const prev = h('button', {
    class: 'icon-button', type: 'button',
    attrs: { 'aria-label': '上一个周期' },
    on: { click: () => step(-1) },
  }, icon('left'));
  const next = h('button', {
    class: 'icon-button', type: 'button',
    attrs: { 'aria-label': '下一个周期' },
    on: { click: () => step(1) },
  }, icon('right'));
  const label = h('div', { class: 'period-label', attrs: { 'aria-live': 'polite' } });
  const today = h('button', {
    class: 'button', type: 'button', text: '今天',
    on: { click: () => setState('period', { ...getState().period, date: todayISO() }) },
  });

  const ranges = segmented(
    PRESETS,
    getState().period.range,
    (id) => pickRange(id),
    { label: '时间范围' },
  );

  const startInput = h('input', { type: 'date', class: 'control', attrs: { 'aria-label': '起始日期' } });
  const endInput = h('input', { type: 'date', class: 'control', attrs: { 'aria-label': '结束日期' } });
  const custom = h(
    'div',
    { class: 'period-custom', hidden: true },
    startInput,
    h('span', { text: '–' }),
    endInput,
  );
  // 自定义收在一个按钮后面：它是少数场景，常驻两个日期框会把这一行挤满。
  const customToggle = h('button', {
    class: 'button', type: 'button', text: '自定义…',
    attrs: { 'aria-expanded': 'false' },
    on: { click: () => pickRange('custom') },
  });
  const applyCustom = () => {
    if (!startInput.value || !endInput.value) return;
    setState('period', { range: 'custom', date: null, start: startInput.value, end: endInput.value });
  };
  startInput.addEventListener('change', applyCustom);
  endInput.addEventListener('change', applyCustom);

  // 视图级筛选的插槽。切视图时整体替换内容（见 setFilters）。
  const filters = h('div', { class: 'periodbar__filters', hidden: true });
  // 数据新鲜度（16 文档 §A6）。**只在实时通道断掉时出现**：SSE 正常时数据一变就重取，
  // 常驻一行"更新于 刚刚"是噪声；而退到 30 秒轮询后，屏幕上原本没有任何地方说得出
  // 这屏数字算于何时（前身 TimeLens 的 `.updated` 是常驻的，它没有实时通道）。
  const freshness = h('span', { class: 'periodbar__freshness numeric', hidden: true });

  mount(
    container,
    ranges.root,
    h('div', { class: 'periodbar__nav' }, prev, label, next),
    today,
    customToggle,
    custom,
    h('span', { class: 'spacer' }),
    freshness,
    filters,
  );

  /** @type {Date | null} */
  let fetchedAt = null;
  const syncFreshness = () => {
    const { live } = getState();
    const stamp = live.mode === 'stream' ? null : fetchedAt;
    freshness.hidden = stamp === null;
    setText(freshness, stamp ? `更新于 ${formatClock(stamp.toISOString())}` : '');
  };
  subscribe('data', () => {
    fetchedAt = new Date();
    syncFreshness();
  });
  subscribe('live', syncFreshness);

  const render = () => {
    const { period, periodMeta } = getState();
    ranges.setActive(period.range);
    const pageable = isPageable(period.range);
    prev.disabled = !pageable;
    next.disabled = !pageable || !canGoForward(period.range, anchorOf(), todayISO());
    today.hidden = period.range === 'total' || Boolean(periodMeta?.is_current);
    const isCustom = period.range === 'custom';
    custom.hidden = !isCustom;
    customToggle.hidden = isCustom;
    customToggle.setAttribute('aria-expanded', String(isCustom));
    if (isCustom) {
      if (period.start) startInput.value = period.start;
      if (period.end) endInput.value = period.end;
    }
    // 标题一律用后端给的 label：前端不会算"9月2日 周三"里的星期，也不该算。
    setText(label, periodMeta?.label || '…');
  };

  subscribe('period', render);
  subscribe('periodMeta', render);
  render();

  return {
    render,
    step,
    pickRange,
    /**
     * 视图级筛选：切视图时整体替换。传空数组即清空（总览没有视图级筛选）。
     * @param {readonly import('../types/dom.js').Child[]} nodes
     */
    setFilters(nodes) {
      const items = (nodes || []).filter(Boolean);
      filters.hidden = items.length === 0;
      mount(filters, ...items);
    },
  };
}

/** 锚点优先用后端规整过的值，否则退回本地选择。 */
function anchorOf() {
  const { period, periodMeta } = getState();
  return periodMeta?.anchor || period.date || todayISO();
}

export function step(direction) {
  const { period } = getState();
  if (!isPageable(period.range)) return;
  if (direction > 0 && !canGoForward(period.range, anchorOf(), todayISO())) return;
  setState('period', { ...period, date: shift(period.range, anchorOf(), direction) });
}

export function pickRange(id) {
  const { period, periodMeta } = getState();
  if (id === 'custom') {
    const end = periodMeta?.truncated_end || todayISO();
    const start = periodMeta?.start || end;
    setState('period', { range: 'custom', date: null, start, end });
    return;
  }
  setState('period', { range: id, date: anchorOf(), start: null, end: null });
}

export function goToday() {
  setState('period', { ...getState().period, date: todayISO() });
}
