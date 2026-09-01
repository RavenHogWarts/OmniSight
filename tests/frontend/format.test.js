// 前端格式化必须与 services/formatting.py 逐个边界一致。
//
// 这张表**与 tests/unit/test_formatting.py 的表格同源**（都抄自 05 文档 §1.6）。
// 两边同时改才可能改，这正是它存在的理由：接口给的 `seconds_formatted` 与前端在
// tooltip 里自己算的时长，如果边界处理不同，同一个数字在同一屏上会有两种写法。
import assert from 'node:assert/strict';
import test from 'node:test';
import { formatCount, formatDelta, formatDuration, formatDurationShort, initialOf } from '../../src/omnisight/presentation/static/js/domain/format.js';

const DURATIONS = [
  [0, '0秒'],
  [0.4, '0秒'],
  [1, '1秒'],
  [59, '59秒'],
  [59.6, '59秒'],
  [60, '1分钟'],
  [61, '1分钟'],
  [3599, '59分钟'],
  [3600, '1小时'],
  [3660, '1小时1分钟'],
  [27183.5, '7小时33分钟'],
  [86400, '24小时'],
];

test('formatDuration 与 Python 版的边界一致', () => {
  for (const [seconds, text] of DURATIONS) {
    assert.equal(formatDuration(seconds), text, `${seconds} 秒`);
  }
});

test('formatDuration 不输出 0小时5分钟 这种读起来像坏了的写法', () => {
  assert.equal(formatDuration(300), '5分钟');
  assert.equal(formatDuration(7200), '2小时');
});

test('负数与非数字都按 0 处理', () => {
  assert.equal(formatDuration(-5), '0秒');
  assert.equal(formatDuration(null), '0秒');
  assert.equal(formatDuration(undefined), '0秒');
  assert.equal(formatDuration('abc'), '0秒');
});

test('formatCount 分组', () => {
  assert.equal(formatCount(0), '0');
  assert.equal(formatCount(999), '999');
  assert.equal(formatCount(18422), '18,422');
});

test('formatDelta 只表达方向，不做价值判断', () => {
  assert.equal(formatDelta(null), '');
  assert.match(formatDelta({ percent: 12.9 }), /12\.9%/);
  assert.match(formatDelta({ percent: -4.3 }), /4\.3%/);
  assert.equal(formatDelta({ percent: 0 }), '持平');
  // 上升与下降只有箭头不同，没有任何颜色或褒贬词。
  assert.notEqual(formatDelta({ percent: 5 }).slice(0, 1), formatDelta({ percent: -5 }).slice(0, 1));
});

test('formatDurationShort 给图表轴用，紧凑但不丢量级', () => {
  assert.equal(formatDurationShort(0), '0');
  assert.equal(formatDurationShort(45), '45s');
  assert.equal(formatDurationShort(600), '10m');
  assert.equal(formatDurationShort(3600), '1h');
  assert.equal(formatDurationShort(5400), '1h30m');
});

test('initialOf 取首字符，中文与空值都有结果', () => {
  assert.equal(initialOf('Visual Studio Code'), 'V');
  assert.equal(initialOf('微信'), '微');
  assert.equal(initialOf(''), '?');
  assert.equal(initialOf(null), '?');
});
