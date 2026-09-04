// 采集状态指示器 + 详情浮层（06 文档 §4.1）。**现状完全缺失的能力**：
// 旧版两个项目都无法告诉用户"采集到底在跑吗"，图表全是 0 时用户无从判断是没用还是坏了。
import { useEffect, useRef, useState } from 'react';
import { useSlice } from '../core/useStore.ts';
import { formatCount, formatDuration } from '../domain/format.ts';
import type { BackendState } from '../types/api.d.ts';

const LABELS: Record<string, string> = {
  unknown: '连接中',
  ok: '采集中',
  paused: '已暂停',
  error: '采集异常',
};

export function StatusDot() {
  const status = useSlice('status');
  const live = useSlice('live');
  const degraded = useSlice('degraded');
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement | null>(null);

  // 点浮层外面关掉它。装在 document 上而不是加一层遮罩：遮罩会吃掉一次点击，
  // 而用户点"外面"通常是想点到那个东西。
  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, [open]);

  const capture = status?.capture;
  const paused = Boolean(capture?.paused);
  const broken =
    Boolean(status) &&
    !paused &&
    capture?.keyboard?.running === false &&
    capture?.foreground?.running === false;
  const hasError = (degraded || []).some((notice) => notice.severity === 'error');
  const state = !status ? 'unknown' : paused ? 'paused' : broken || hasError ? 'error' : 'ok';

  return (
    <div className="status-wrap" ref={wrap}>
      <button
        className="status"
        type="button"
        data-state={state}
        data-live={String(live.mode === 'stream')}
        aria-expanded={open}
        aria-label="采集状态"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="status__dot" aria-hidden="true" />
        <span>{LABELS[state] + (live.mode === 'polling' ? '（轮询中）' : '')}</span>
      </button>
      <div className="status-panel" hidden={!open}>
        {open ? <StatusPanel /> : null}
      </div>
    </div>
  );
}

function StatusPanel() {
  const status = useSlice('status');
  const live = useSlice('live');
  const capture = status?.capture;
  const counters = live.counters;
  const rows: (readonly [string, string] | null)[] = [
    ['键盘采集', describeBackend(capture?.keyboard)],
    ['前台归因', describeBackend(capture?.foreground)],
    ['写入线程', capture?.writer?.running ? '运行中' : '未运行'],
    ['队列深度', String(capture?.queue_depth ?? 0)],
    ['丢弃事件', String(capture?.dropped_events ?? 0)],
    [
      '实时通道',
      live.mode === 'stream' ? 'SSE 已连接' : live.mode === 'polling' ? '30 秒轮询' : '未连接',
    ],
    counters ? ['今日按键', formatCount(counters.presses)] : null,
    counters ? ['今日时长', formatDuration(counters.seconds)] : null,
    live.currentApp ? ['当前前台', live.currentApp.display_name || '未知'] : null,
    ['版本', status?.version || '-'],
  ];
  return (
    <dl>
      {rows.filter(Boolean).map((row) => {
        const [label, value] = row as readonly [string, string];
        return (
          <div key={label} style={{ display: 'contents' }}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        );
      })}
    </dl>
  );
}

function describeBackend(part: BackendState | null | undefined): string {
  if (!part) return '未知';
  const backend = part.backend && part.backend !== 'none' ? part.backend : null;
  if (!part.running) return backend ? `未运行（${backend}）` : '未运行';
  return backend ? `运行中（${backend}）` : '运行中';
}
