// 键盘布局的**遍历契约**：后端下发的布局数据能被前端正确读出来。
//
// 布局 JSON 直接从后端的 layouts.py 导出（见 tests/unit/test_frontend_js.py 如何生成），
// 因此这些断言验证的是"前端能正确吃下真实布局"，不是"能吃下我编的假数据"。
//
// **原先这条用例还断言渲染出的 DOM 结构**（`buildKeyboard()` 建出多少个 .key-cap、
// 每个键的 --w/--h、未知 shape 退化为矩形）。15 文档方案 A 之后那部分搬进了
// `components/KeyboardView.tsx`，而 React 组件在纯 Node 下测不了：
// `node --experimental-strip-types` 只剥类型、不转 JSX（15 文档 §3.6 那条"零依赖也能
// 测"的路对**纯函数**仍然通，对组件不通）。
//
// 那一半的验证换成了**真实浏览器**：`tools/page.py --view keyboard` 用 playwright-core
// 驱动已装的 Edge，读 computed style 与 getBoundingClientRect，比 dom-shim 能断言的
// 更多（14 文档 §8.3）。这里只留下不需要 DOM 的那一半——而它恰好是与后端的契约。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { keyOrder, keyRows } from '../../frontend/src/domain/keyboard-layout.ts';
import type { LayoutResponse } from '../../frontend/src/types/api.d.ts';

type Fixture = LayoutResponse & { unit_hint: { max_units: number; rows: number } };

const LAYOUTS: Record<string, Fixture> = JSON.parse(
  readFileSync(new URL('./layouts.json', import.meta.url), 'utf8'),
);

for (const family of Object.keys(LAYOUTS)) {
  const layout = LAYOUTS[family];

  test(`${family}: 每一行的宽度总和都是同一个单位数（键与空隙用同一个公式）`, () => {
    for (const [index, row] of layout.rows.entries()) {
      const units = row.reduce((sum, slot) => sum + Number(slot.w), 0);
      assert.equal(units, layout.unit_hint.max_units, `第 ${index + 1} 行`);
    }
  });

  test(`${family}: keyRows 的行数与布局一致，且不含占位槽`, () => {
    const rows = keyRows(layout);
    assert.equal(rows.length, layout.unit_hint.rows);
    for (const row of rows) {
      assert.ok(!row.includes('gap'), '占位槽不该出现在导航序列里');
    }
  });

  test(`${family}: keyOrder 覆盖布局里每一个真实键，顺序即视觉顺序`, () => {
    const expected = layout.rows
      .flat()
      .filter((slot) => slot.id !== 'gap')
      .map((slot) => slot.id);
    assert.deepEqual(keyOrder(layout), expected);
  });

  test(`${family}: 键 id 不重复——热力数据按 id 匹配，重复会让两个键抢同一个值`, () => {
    const ids = keyOrder(layout);
    assert.equal(new Set(ids).size, ids.length);
  });
}

test('布局缺失时两个函数都给空结果，不抛', () => {
  assert.deepEqual(keyOrder(null), []);
  assert.deepEqual(keyRows(undefined), []);
});
