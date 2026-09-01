// 结论卡组件（M4 判据 4：每个洞察结论都能点开看到它的计算口径）。
//
// 结构性验证：details/summary 的展开语义由浏览器保证，这里断言的是
// "结论文本与口径文本都在、且口径不在 summary 里（不会把口径当结论读）"。
import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './dom-shim.js';

const restore = installDom();
const { h } = await import('../../src/omnisight/presentation/static/js/core/dom.js');
const { renderHighlights } = await import(
  '../../src/omnisight/presentation/static/js/components/highlights.js'
);

test.after(() => restore());

const HIGHLIGHTS = [
  { code: 'peak_hour', text: '22:00 是今天最活跃的时段', basis: '对比 24 个小时的前台时长，取最大者。' },
  { code: 'kpm_peak', text: '峰值输入速度 412 键/分钟', basis: '周期内单分钟最大按键数。' },
];

test('每条结论是一个可展开的 details，口径在展开区里', () => {
  const host = h('div');
  renderHighlights(host, HIGHLIGHTS);
  // dom-shim 只支持单选择器：按类取，再断言标签名。
  const items = host.querySelectorAll('.highlight');
  assert.equal(items.length, 2);
  for (const [index, node] of items.entries()) {
    assert.equal(node.tagName, 'DETAILS', '必须是 details 才有免费的原生展开语义');
    const summary = node.querySelector('summary');
    assert.ok(summary, '必须有 summary（键盘可达的展开入口）');
    assert.ok(summary.textContent.includes(HIGHLIGHTS[index].text));
    // 口径在展开区，不在摘要行里——摘要读的是结论，不是算法。
    const basis = node.querySelector('.highlight__basis');
    assert.ok(basis, '必须有口径说明');
    assert.ok(basis.textContent.includes(HIGHLIGHTS[index].basis));
    assert.ok(!summary.textContent.includes('口径：'));
  }
});

test('没有结论时给出引导文案而不是空白', () => {
  const host = h('div');
  renderHighlights(host, []);
  assert.match(host.textContent, /暂时得不出结论/);
});
