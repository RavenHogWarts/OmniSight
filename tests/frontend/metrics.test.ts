// 热力归一与指标定义。p95 归一是 06 文档 §7 改进 1 的实质内容，值得单独固定：
// 用最大值归一时空格键会把其余所有键压成一片浅色，热力图读不出差异。
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  METRICS, PROFILES, TIMELINE_VIEWS, formatMetric, heatLevel, heatRatio,
  isSaturated, metricOf, rangeFromDefaultView,
} from '../../frontend/src/domain/metrics.ts';

test('METRICS 与后端 services/keyboard.py 的 METRICS 一一对应', () => {
  assert.deepEqual(
    METRICS.map((metric) => metric.id),
    ['press_count', 'duration_total_ms', 'duration_avg_ms', 'duration_max_ms'],
  );
  assert.deepEqual(TIMELINE_VIEWS.map((view) => view.id), ['hours', 'days', 'months', 'years']);
  assert.deepEqual(PROFILES, ['input_heavy', 'interactive', 'passive', 'idle_open']);
});

test('未知指标退化为第一个，而不是抛异常', () => {
  assert.equal(metricOf('nonsense').id, 'press_count');
  assert.equal(metricOf(undefined).id, 'press_count');
});

test('heatRatio 按 p95 归一，超出的钳到 1', () => {
  const scale = { min: 0, p95: 800, max: 2400 };
  assert.equal(heatRatio(0, scale), 0);
  assert.equal(heatRatio(400, scale), 0.5);
  assert.equal(heatRatio(800, scale), 1);
  // 空格键这类离群值不会让其余键被压扁：它自己饱和到 1。
  assert.equal(heatRatio(2400, scale), 1);
});

test('p95 缺失时退回最大值，两者都没有则一律 0', () => {
  assert.equal(heatRatio(50, { max: 100 }), 0.5);
  assert.equal(heatRatio(50, {}), 0);
  assert.equal(heatRatio(50, null), 0);
});

test('isSaturated 只在真的存在离群值时为真', () => {
  assert.equal(isSaturated(2400, { p95: 800, max: 2400 }), true);
  assert.equal(isSaturated(800, { p95: 800, max: 2400 }), false);
  // 最大值等于 p95 时没有离群值，任何键都不该被标记。
  assert.equal(isSaturated(800, { p95: 800, max: 800 }), false);
});

test('heatLevel 给出离散档位，供图例与 aria-label 使用', () => {
  assert.equal(heatLevel(0), 0);
  assert.equal(heatLevel(0.1), 1);
  assert.equal(heatLevel(0.5), 3);
  assert.equal(heatLevel(1), 5);
});

test('配置的 ui.default_view 映射到 API 的 range', () => {
  assert.equal(rangeFromDefaultView('daily'), 'day');
  assert.equal(rangeFromDefaultView('weekly'), 'week');
  assert.equal(rangeFromDefaultView('monthly'), 'month');
  assert.equal(rangeFromDefaultView('yearly'), 'year');
  assert.equal(rangeFromDefaultView('total'), 'total');
  assert.equal(rangeFromDefaultView('nonsense'), 'day');
});

test('formatMetric 按指标选单位：次数不带 ms，时长带', () => {
  assert.equal(formatMetric('press_count', 18422), '18,422');
  assert.match(formatMetric('duration_avg_ms', 85.8), /ms$/);
});
