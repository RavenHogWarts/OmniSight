// 结论列表：总览与洞察共用（M4 判据 4）。
//
// 每条结论都是原生 <details>，点开就是这条结论的计算口径（后端下发的 basis）。
// 用 details/summary 而不是按钮 + 显隐：键盘可达与展开语义浏览器免费给。
// 放在 components/ 而不是某个 view 里：views 不互相 import（07 文档 §3 分层规则，
// M3 偏离 65 为此把 card() 挪下来过一次）。
import { h, mount } from '../core/dom.js';

export function renderHighlights(host, highlights) {
  const items = highlights || [];
  if (!items.length) {
    mount(host, h('div', { class: 'dim text-sm', text: '数据还不够多，暂时得不出结论' }));
    return;
  }
  mount(
    host,
    ...items.map((item) =>
      h(
        'details',
        { class: 'highlight' },
        h(
          'summary',
          null,
          h('span', { class: 'highlight__mark', attrs: { 'aria-hidden': 'true' }, text: '◈' }),
          h('span', { text: item.text }),
          item.basis
            ? h('span', { class: 'highlight__toggle', attrs: { 'aria-hidden': 'true' }, text: '口径' })
            : null,
        ),
        item.basis
          ? h('div', { class: 'highlight__basis', text: `口径：${item.basis}` })
          : null,
      ),
    ),
  );
}
