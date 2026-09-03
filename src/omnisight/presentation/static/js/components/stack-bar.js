// 单条 100% 构成条（14 文档 §2.10）。
//
// 它替换的是环形图。三条理由，任何一条都够：扇区顺序由数据决定（因此是 all-pairs
// 场景，而 all-pairs 能安全承载的身份色上限约 3–4 个，这里有 6 个）；命中区是扇区
// 中点的 24×24 方块，既不覆盖整个扇区也不精确；旁边的类别列表已经把名称、占比、
// 时长全列了一遍，环形图只多贡献了一次颜色匹配。
//
// **槽位顺序固定**（后端 CATEGORIES 的顺序），不按大小排：相邻关系因此确定、可以
// 事先校验，而且同一个类别在每个周期都在同一个位置，跨周期对比更容易。
//
// 用 DOM 而不是 canvas：单条构成条用 flex 就是几行 CSS，而且天然可悬停、可读屏、
// 可选中文字——canvas 要为这些各写一遍。
import { closestFrom, h } from '../core/dom.js';
import { formatPercent } from '../domain/format.js';

/**
 * @param {Element} container
 * @param {{ label?: string, onSelect?: ((id: string) => void) | null }} [options]
 */
export function stackBar(container, { label = '构成', onSelect = null } = {}) {
  const track = h('div', {
    class: 'stackbar',
    attrs: { role: 'img', 'aria-label': label },
  });
  const table = h('div', { class: 'sr-only' });
  container.replaceChildren(track, table);

  if (onSelect) {
    track.addEventListener('click', (event) => {
      const segment = closestFrom(event, '.stackbar__seg');
      if (segment?.dataset.id) onSelect(segment.dataset.id);
    });
    track.classList.add('stackbar--clickable');
  }

  return {
    /**
     * segments: [{ id, name, value, percent, formatted }]，顺序即槽位顺序。
     * @param {readonly any[]} segments
     */
    update(segments) {
      const items = (segments || []).filter((item) => (Number(item.percent) || 0) > 0);
      track.replaceChildren(
        ...items.map((item) => {
          const percent = Number(item.percent) || 0;
          const node = h('span', {
            class: 'stackbar__seg',
            dataset: { category: item.id, id: item.id },
            // dash-case：style 走 setProperty，flexGrow 会被静默丢弃（core/dom.js）。
            style: { 'flex-grow': String(percent) },
            attrs: { title: `${item.name}：${item.formatted ?? ''}（${formatPercent(percent)}）` },
          });
          // 内联标签只在装得下时出现（约 9%）；装不下时交给列表与悬停，
          // 绝不缩字或裁字（14 文档 §4.3）。
          if (percent >= 9) node.append(h('span', { class: 'stackbar__label', text: item.name }));
          return node;
        }),
      );
      track.setAttribute(
        'aria-label',
        items.length
          ? `${label}：${items.map((item) => `${item.name} ${formatPercent(item.percent)}`).join('，')}`
          : `${label}：暂无数据`,
      );
      table.replaceChildren(
        h(
          'table',
          null,
          h('caption', { text: label }),
          h('thead', null, h('tr', null, h('th', { text: '类别' }), h('th', { text: '占比' }), h('th', { text: '数值' }))),
          h(
            'tbody',
            null,
            ...items.map((item) =>
              h(
                'tr',
                null,
                h('td', { text: String(item.name ?? '') }),
                h('td', { text: formatPercent(item.percent) }),
                h('td', { text: String(item.formatted ?? '') }),
              ),
            ),
          ),
        ),
      );
    },
    destroy() {
      container.replaceChildren();
    },
  };
}
