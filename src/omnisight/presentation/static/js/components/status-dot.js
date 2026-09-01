// 采集状态指示器 + 详情浮层（06 文档 §4.1）。**现状完全缺失的能力**：
// 旧版两个项目都无法告诉用户"采集到底在跑吗"，图表全是 0 时用户无从判断是没用还是坏了。
import { on as busOn } from '../core/bus.js';
import { h, mount, setText } from '../core/dom.js';
import { getState, subscribe } from '../core/store.js';
import { formatCount, formatDuration } from '../domain/format.js';

export function mountStatus(container) {
  const dot = h('span', { class: 'status__dot', attrs: { 'aria-hidden': 'true' } });
  const text = h('span', { text: '连接中' });
  const panel = h('div', { class: 'status-panel', hidden: true });
  const button = h(
    'button',
    {
      class: 'status',
      type: 'button',
      dataset: { state: 'unknown', live: 'false' },
      attrs: { 'aria-expanded': 'false', 'aria-label': '采集状态' },
    },
    dot,
    text,
  );
  const wrap = h('div', { class: 'status-wrap' }, button, panel);
  container.replaceChildren(wrap);

  button.addEventListener('click', () => {
    const open = panel.hidden;
    panel.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
    if (open) renderPanel(panel);
  });
  document.addEventListener('click', (event) => {
    if (!wrap.contains(event.target) && !panel.hidden) {
      panel.hidden = true;
      button.setAttribute('aria-expanded', 'false');
    }
  });

  const render = () => {
    const { status, live, degraded } = getState();
    const capture = status?.capture;
    const paused = Boolean(capture?.paused);
    const broken = Boolean(status) && !paused && capture?.keyboard?.running === false
      && capture?.foreground?.running === false;
    const hasError = (degraded || []).some((notice) => notice.severity === 'error');
    const state = !status ? 'unknown' : paused ? 'paused' : (broken || hasError) ? 'error' : 'ok';
    button.dataset.state = state;
    button.dataset.live = String(live.mode === 'stream');
    setText(text, LABELS[state] + (live.mode === 'polling' ? '（轮询中）' : ''));
    if (!panel.hidden) renderPanel(panel);
  };

  subscribe('status', render);
  subscribe('live', render);
  subscribe('degraded', render);
  busOn('capture:status', render);
  render();
  return render;
}

const LABELS = {
  unknown: '连接中',
  ok: '采集中',
  paused: '已暂停',
  error: '采集异常',
};

function renderPanel(panel) {
  const { status, live } = getState();
  const capture = status?.capture || {};
  const counters = live.counters;
  mount(
    panel,
    h(
      'dl',
      null,
      row('键盘采集', describeBackend(capture.keyboard)),
      row('前台归因', describeBackend(capture.foreground)),
      row('写入线程', capture.writer?.running ? '运行中' : '未运行'),
      row('队列深度', String(capture.queue_depth ?? 0)),
      row('丢弃事件', String(capture.dropped_events ?? 0)),
      row('实时通道', live.mode === 'stream' ? 'SSE 已连接' : live.mode === 'polling' ? '30 秒轮询' : '未连接'),
      counters ? row('今日按键', formatCount(counters.presses)) : null,
      counters ? row('今日时长', formatDuration(counters.seconds)) : null,
      live.currentApp ? row('当前前台', live.currentApp.display_name || '未知') : null,
      row('版本', status?.version || '-'),
    ),
  );
}

function row(label, value) {
  return [h('dt', { text: label }), h('dd', { text: value })];
}

function describeBackend(part) {
  if (!part) return '未知';
  const backend = part.backend && part.backend !== 'none' ? part.backend : null;
  if (!part.running) return backend ? `未运行（${backend}）` : '未运行';
  return backend ? `运行中（${backend}）` : '运行中';
}
