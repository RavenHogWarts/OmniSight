// 时间轴标签的抽稀规则（charts/axis.ts）。
//
// 为什么这一层值得有测试：轴标签是"错了也不报错"的那类代码——叠字、末桶没刻度、首标签
// 探进 y 轴刻度区，三者都只在某个宽度加某个粒度的组合下出现，而人眼过一遍截图恰好最容易
// 漏掉它们（14 文档 §8.3 把可量化的判据尽量移出人工清单）。
//
// `timeAxisTicks` 收一个 `measure` 函数，所以这里用一把"每字符 7px"的假尺子就能跑，
// 不需要 canvas，也不受运行机器上装了哪些字体的影响。
import assert from 'node:assert/strict';
import test from 'node:test';
import { timeAxisTicks } from '../../frontend/src/charts/axis.ts';

/** 假尺子。等宽 7px/字符——真实的 Segoe 不等宽，但抽稀规则与字宽的具体值无关。 */
const ruler = (text: string) => text.length * 7;

const hours = Array.from({ length: 24 }, (_unused, hour) => `${hour}:00`);
const days = Array.from({ length: 31 }, (_unused, index) => `9/${index + 1}`);

/** 标签占据的横向区间。`align` 决定 x 是左端、中点还是右端。 */
function extent(tick: { text: string; x: number; align: string }): [number, number] {
  const width = ruler(tick.text);
  if (tick.align === 'left') return [tick.x, tick.x + width];
  if (tick.align === 'right') return [tick.x - width, tick.x];
  return [tick.x - width / 2, tick.x + width / 2];
}

test('没有标签、或宽度为 0 时不画', () => {
  assert.deepEqual(timeAxisTicks([], { x: 0, w: 600 }, ruler), []);
  assert.deepEqual(timeAxisTicks(hours, { x: 0, w: 0 }, ruler), []);
  assert.deepEqual(timeAxisTicks(hours, { x: 0, w: -10 }, ruler), []);
});

test('都放得下时一个不抽', () => {
  const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
  const ticks = timeAxisTicks(weekdays, { x: 44, w: 700 }, ruler);
  assert.deepEqual(ticks.map((tick) => tick.text), weekdays);
});

test('末桶一定有标签——右端要说得出自己在哪结束', () => {
  // 31 天 / 400px：stride=4 时原先最后一个标签落在第 28 天，右边三天没有任何刻度。
  const ticks = timeAxisTicks(days, { x: 48, w: 400 }, ruler);
  assert.equal(ticks[ticks.length - 1].index, 30);
  assert.equal(ticks[ticks.length - 1].text, '9/31');
  // 末桶挤掉的是它前面那个中间刻度，不是又多画一个叠在一起的。
  assert.ok(!ticks.some((tick) => tick.index === 28));
  assert.equal(ticks[0].index, 0);
});

test('24 小时轴：首末都在，且没有两个标签叠在一起', () => {
  const ticks = timeAxisTicks(hours, { x: 52, w: 600 }, ruler);
  assert.equal(ticks[0].index, 0);
  assert.equal(ticks[ticks.length - 1].index, 23);
  for (let i = 1; i < ticks.length; i += 1) {
    assert.ok(ticks[i].x > ticks[i - 1].x, `第 ${i} 个标签的 x 没有递增`);
    const [, previousRight] = extent(ticks[i - 1]);
    const [left] = extent(ticks[i]);
    assert.ok(left >= previousRight, `${ticks[i - 1].text} 与 ${ticks[i].text} 叠在一起`);
  }
});

test('首末标签贴边，不探出绘图区', () => {
  const plot = { x: 52, w: 600 };
  const ticks = timeAxisTicks(hours, plot, ruler);
  const first = ticks[0];
  const last = ticks[ticks.length - 1];
  assert.equal(first.align, 'left');
  assert.equal(first.x, plot.x);
  assert.equal(last.align, 'right');
  assert.equal(last.x, plot.x + plot.w);
  // 贴边之后两端都严格落在绘图区内——居中时首标签会探进 y 轴刻度文字那一片。
  for (const tick of ticks) {
    const [left, right] = extent(tick);
    assert.ok(left >= plot.x - 0.01, `${tick.text} 探出左缘`);
    assert.ok(right <= plot.x + plot.w + 0.01, `${tick.text} 探出右缘`);
  }
});

test('宽度再窄也留首末两个', () => {
  const ticks = timeAxisTicks(hours, { x: 52, w: 50 }, ruler);
  assert.equal(ticks.length, 2);
  assert.deepEqual(ticks.map((tick) => tick.index), [0, 23]);
});

test('只有一个桶时就画那一个', () => {
  const ticks = timeAxisTicks(['9/4'], { x: 48, w: 400 }, ruler);
  assert.equal(ticks.length, 1);
  assert.equal(ticks[0].index, 0);
});

test('宽标签比窄标签抽得狠——按实测宽度而不是一个常数', () => {
  const plot = { x: 48, w: 600 };
  const narrow = timeAxisTicks(days, plot, ruler);
  // 「2026年12月」这类标签是 `9/1` 的三倍宽，同样 31 个桶必须少画很多个。
  const wide = timeAxisTicks(
    days.map((_unused, index) => `2026年${(index % 12) + 1}月`),
    plot,
    ruler,
  );
  assert.ok(
    wide.length < narrow.length,
    `宽标签给了 ${wide.length} 个、窄标签 ${narrow.length} 个——没有按实测宽度抽稀`,
  );
});
