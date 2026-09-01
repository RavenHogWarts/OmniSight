// 通用格子热力图：时 / 月 / 年 桶。与日历同一套着色（--heat + data-level），
// 只是排布是流式的而不是按周分列。
import { h, renderKeyed } from '../core/dom.js';
import { heatLevel, heatRatio } from '../domain/metrics.js';
import { formatMetric } from '../domain/metrics.js';

export function gridHeatmap(container, { metric = 'press_count', onSelect = null, label = '时间分布' } = {}) {
  const grid = h('div', {
    class: 'heatgrid heatgrid--flow',
    attrs: { role: 'group', 'aria-label': label },
  });
  const legend = h('div', { class: 'chart__axis' });
  container.replaceChildren(grid, legend);

  if (onSelect) {
    grid.addEventListener('click', (event) => {
      const cell = event.target.closest('.heat-cell');
      if (cell?.dataset.bucket) onSelect(cell.dataset.bucket);
    });
  }

  return {
    update(buckets, scale, gaps, activeMetric = metric) {
      const items = buckets || [];
      renderKeyed(
        grid,
        items,
        (item) => item.bucket,
        () => h('div', { class: 'heat-cell' }),
        (node, item) => {
          node.dataset.bucket = item.bucket;
          const isGap = Boolean(gaps?.has(item.bucket));
          if (isGap) node.dataset.gap = 'true';
          else delete node.dataset.gap;
          const value = Number(item[activeMetric]) || 0;
          const ratio = isGap ? 0 : heatRatio(value, scale);
          node.style.setProperty('--heat', ratio.toFixed(4));
          node.dataset.level = String(heatLevel(ratio));
          node.setAttribute(
            'aria-label',
            isGap
              ? `${item.label || item.bucket}：无记录`
              : `${item.label || item.bucket}：${formatMetric(activeMetric, value)}`,
          );
        },
      );
      legend.replaceChildren(
        h('span', { text: items.length ? String(items[0].label ?? items[0].bucket) : '' }),
        h('span', { text: items.length ? String(items[items.length - 1].label ?? items[items.length - 1].bucket) : '' }),
      );
    },
    destroy() {
      container.replaceChildren();
    },
  };
}
