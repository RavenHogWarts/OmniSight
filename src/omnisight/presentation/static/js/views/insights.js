// 洞察视图（06 文档 §8）。**合并才可能实现的分析**——这是"为什么要升级"的答案。
//
// 四块内容都需要两边的数据同时在一个库里：
//   输入强度排行  前台时长（TimeLens 侧）除以按键数（KeyTrace 侧）
//   时间去向      按 KPM 把前台时长分成主动输入 / 交互 / 被动 / 开着未用
//   专注与作息    会话跨度 + 按键节奏
//   键位 x 应用   某个键的按下主要来自哪些应用（反向视图）
import { h, mount } from '../core/dom.js';
import { getState, setState } from '../core/store.js';
import { fetchInto } from '../core/loader.js';
import { formatCount, formatClock, formatPercent } from '../domain/format.js';
import { capabilityNotice, emptyState, errorState, skeletonRows } from '../components/states.js';
import { capabilityOf, noticeFor } from '../components/degraded.js';
import { card } from '../components/card.js';
import { periodParams } from '../domain/period.js';

export const title = '洞察';

const KEY_CHOICES = [
  { id: 'space', label: 'Space' },
  { id: 'key_e', label: 'E' },
  { id: 'backspace', label: 'Backspace' },
  { id: 'enter', label: 'Enter' },
  { id: 'control_left', label: 'Ctrl' },
  { id: 'tab', label: 'Tab' },
];

function bar(ratio, profile) {
  const node = h('div', { class: 'bar', dataset: profile ? { profile } : {} }, h('i'));
  node.style.setProperty('--fill', String(Math.max(0, Math.min(1, ratio || 0))));
  return node;
}

export function create(root) {
  const rankHost = h('div', { class: 'data-table__scroll' });
  const rankNote = h('div', { class: 'card__hint' });
  const distributionHost = h('div', { class: 'distribution' });
  const focusHost = h('div', { class: 'stack' });
  const rhythmHost = h('div', { class: 'stack' });
  const keySplitHost = h('div', { class: 'key-app-split' });
  const keySelect = h(
    'select',
    { class: 'control', attrs: { 'aria-label': '选择键位' } },
    ...KEY_CHOICES.map((key) => h('option', { value: key.id, text: key.label })),
  );
  keySelect.addEventListener('change', () => {
    setState('selectedKeyId', keySelect.value);
    fetchInto('insightKey', `/keyboard/keys/${keySelect.value}`, periodParams(getState().period));
  });

  mount(
    root,
    h('h1', { class: 'view__title sr-only', text: '洞察', attrs: { tabindex: '-1', id: 'view-title' } }),
    card('输入强度排行', rankHost, [], rankNote),
    card('时间去向', distributionHost),
    h(
      'div',
      { class: 'grid grid--2' },
      card('专注度', focusHost),
      card('作息', rhythmHost),
    ),
    card('键位与应用', keySplitHost, [keySelect]),
  );

  function render() {
    const state = getState();
    const keyboard = state.data.insightKeyboard;
    const rhythm = state.data.insightRhythm;
    const error = state.errors.insightKeyboard || state.errors.insightRhythm;

    // 洞察整体依赖应用归因：没有归因就只剩"某个键被按了多少次"，那不是洞察。
    if (!capabilityOf(state.capabilities, 'foreground')) {
      const notice = noticeFor(state.degraded, 'foreground');
      mount(rankHost, capabilityNotice({
        title: (notice && notice.title) || '当前环境不支持识别前台应用',
        detail: (notice && notice.detail) || '交叉分析需要把按键归到应用上，键盘总量统计不受影响。',
        hint: (notice && notice.hint) || '',
      }));
      mount(distributionHost);
      mount(focusHost);
      mount(rhythmHost);
      return;
    }
    if (error) {
      mount(rankHost, errorState({ message: error.message, onRetry: reload }));
      return;
    }
    if (!keyboard) {
      if (state.loading.insightKeyboard) mount(rankHost, skeletonRows(5));
      return;
    }

    renderRanking(keyboard);
    renderDistribution(keyboard);
    renderFocus(rhythm, state);
    renderRhythm(rhythm, state);
    renderKeySplit(state);
  }

  function renderRanking(payload) {
    const apps = payload.apps || [];
    if (!apps.length) {
      mount(rankHost, emptyState({ title: '这段时间没有可分析的应用' }));
      return;
    }
    const maxKpm = Math.max(1, ...apps.map((app) => Number(app.kpm) || 0));
    // 真实 table 而不是 div 堆叠：屏幕阅读器需要行列关系（06 文档 §13）。
    mount(
      rankHost,
      h(
        'table',
        { class: 'data-table' },
        h('caption', { class: 'sr-only', text: '各应用的输入强度' }),
        h(
          'thead',
          null,
          h(
            'tr',
            null,
            h('th', { text: '应用' }),
            h('th', { class: 'numeric', text: '前台时长' }),
            h('th', { class: 'numeric', text: '按键' }),
            h('th', { class: 'numeric', text: 'KPM' }),
            h('th', { class: 'numeric', text: '修饰键' }),
            h('th', { text: '画像' }),
          ),
        ),
        h(
          'tbody',
          null,
          ...apps.map((app) =>
            h(
              'tr',
              null,
              h('td', { class: 'wide truncate', text: app.display_name }),
              h('td', { class: 'numeric', text: app.seconds_formatted }),
              h('td', { class: 'numeric', text: formatCount(app.presses) }),
              h('td', { class: 'numeric', text: (Number(app.kpm) || 0).toFixed(1) }),
              h('td', { class: 'numeric', text: formatPercent(app.modifier_percent) }),
              h(
                'td',
                null,
                h(
                  'span',
                  { class: 'profile-tag', dataset: { profile: app.profile } },
                  h('span', { class: 'profile-tag__bar' }, bar((Number(app.kpm) || 0) / maxKpm, app.profile)),
                  h('span', { text: app.profile_name }),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    const parts = [payload.kpm_basis ? `KPM 口径：${payload.kpm_basis}` : ''];
    if (payload.unattributed_presses) {
      parts.push(`另有 ${formatCount(payload.unattributed_presses)} 次按键没有应用归因`);
    }
    mount(rankNote, h('span', { text: parts.filter(Boolean).join('。') }));
  }

  function renderDistribution(payload) {
    const distribution = payload.distribution || {};
    const buckets = distribution.buckets || [];
    const total = Number(distribution.total_seconds) || 0;
    if (!total) {
      mount(distributionHost, emptyState({ title: '这段时间没有前台记录', mark: '·' }));
      return;
    }
    mount(
      distributionHost,
      ...buckets.map((bucket) =>
        h(
          'div',
          { class: 'distribution__row', dataset: { profile: bucket.id } },
          h('span', { class: 'distribution__name', text: bucket.name }),
          bar((bucket.seconds || 0) / total, bucket.id),
          h('span', { class: 'distribution__value', text: bucket.seconds_formatted }),
          h('span', { class: 'distribution__percent', text: formatPercent(bucket.percent) }),
        ),
      ),
    );
  }

  function renderFocus(rhythm, state) {
    if (!rhythm) {
      if (state.loading.insightRhythm) mount(focusHost, skeletonRows(2));
      return;
    }
    const blocks = rhythm.focus_blocks || [];
    mount(
      focusHost,
      h(
        'dl',
        { class: 'kv-list' },
        h('dt', { text: '应用切换' }), h('dd', { text: `${formatCount(rhythm.switch_count)} 次` }),
        h('dt', { text: '每小时切换' }), h('dd', { text: (Number(rhythm.switches_per_hour) || 0).toFixed(1) }),
        h('dt', { text: '最长专注' }), h('dd', { text: `${(Number(rhythm.longest_focus_minutes) || 0).toFixed(0)} 分钟` }),
      ),
      // 切换次数的口径要写明：心跳切段不是切换，只有 end_reason = switch 才算
      // （否则这个数字会大两个数量级，见 03 文档的访问与会话段之分）。
      rhythm.switches_basis
        ? h('div', { class: 'card__hint', text: `口径：${rhythm.switches_basis}` })
        : null,
      blocks.length
        ? h(
            'div',
            { class: 'focus-blocks' },
            h('div', { class: 'text-sm muted', text: '最长的几段专注' }),
            ...blocks.slice(0, 6).map((block) =>
              h(
                'div',
                { class: 'focus-block' },
                h('span', { text: `${formatClock(block.start)}-${formatClock(block.end)}` }),
                h('span', { class: 'truncate', text: block.display_name }),
                h('span', { class: 'numeric', text: `${(Number(block.minutes) || 0).toFixed(0)} 分钟` }),
              ),
            ),
          )
        : h('div', { class: 'card__hint', text: '这段时间没有足够长的连续使用' }),
    );
  }

  function renderRhythm(rhythm, state) {
    if (!rhythm) {
      if (state.loading.insightRhythm) mount(rhythmHost, skeletonRows(2));
      return;
    }
    const active = rhythm.active_hours || {};
    const peak = rhythm.peak_kpm || {};
    mount(
      rhythmHost,
      h(
        'dl',
        { class: 'kv-list' },
        h('dt', { text: '首次活动' }), h('dd', { text: active.first || '-' }),
        h('dt', { text: '末次活动' }), h('dd', { text: active.last || '-' }),
        h('dt', { text: '活跃跨度' }), h('dd', { text: `${(Number(active.span_hours) || 0).toFixed(1)} 小时` }),
        h('dt', { text: '峰值 KPM' }), h('dd', { text: formatCount(peak.value || 0) }),
        h('dt', { text: '峰值时刻' }), h('dd', { text: peak.at ? formatClock(peak.at) : '-' }),
      ),
    );
  }

  function renderKeySplit(state) {
    const payload = state.data.insightKey;
    if (!payload) {
      if (state.loading.insightKey) mount(keySplitHost, skeletonRows(2));
      return;
    }
    const byApp = payload.by_app || [];
    const totals = payload.totals || {};
    if (!byApp.length) {
      mount(keySplitHost, emptyState({
        title: `${payload.key.label} 没有按应用拆分的数据`,
        detail: '这个键在本周期内没有被按下，或原始事件未保留',
        mark: '·',
      }));
      return;
    }
    const top = Math.max(1, ...byApp.map((item) => Number(item.press_count) || 0));
    mount(
      keySplitHost,
      h('div', {
        class: 'text-sm muted',
        text: `${payload.key.label} 的 ${formatCount(totals.press_count || 0)} 次按下来自：`,
      }),
      ...byApp.slice(0, 10).map((item) =>
        h(
          'div',
          { class: 'top-key' },
          h('span', { class: 'rank' }),
          h('span', { class: 'truncate', text: item.display_name }),
          bar((Number(item.press_count) || 0) / top),
          h('span', { class: 'top-key__count', text: formatCount(item.press_count) }),
          h('span', { class: 'top-key__percent', text: formatPercent(item.percent) }),
        ),
      ),
    );
  }

  function reload() {
    const state = getState();
    for (const request of requestsFor(state)) {
      fetchInto(request.key, request.path, request.params);
    }
  }

  function requestsFor(state) {
    const period = periodParams(state.period);
    const keyId = state.selectedKeyId || keySelect.value || 'space';
    keySelect.value = keyId;
    return [
      { key: 'insightKeyboard', path: '/insights/app-keyboard', params: { ...period, limit: 20 } },
      { key: 'insightRhythm', path: '/insights/rhythm', params: period },
      { key: 'insightKey', path: `/keyboard/keys/${keyId}`, params: period },
    ];
  }

  return {
    needs: requestsFor,
    render,
    destroy() {
      root.replaceChildren();
    },
  };
}
