// 设置抽屉（06 文档 §9）。
//
// **表单由 GET /api/v1/settings 的元数据生成，不由前端写死。** 每项自带 kind / 取值范围 /
// options / available / unavailable_reason / applies，因此这里没有一行"哪个开关在哪个平台上
// 要隐藏"的知识——那正是 07 文档 §10 第 4 行要禁止的东西。
//
// 不可用的项**显示但禁用**，旁边给出原因。隐藏会让用户以为功能不存在并去别处找；
// 禁用加解释才能传达"这台机器上办不到"。
//
// 前端唯一自带的两样东西：
//   1. 字段的中文标签（UI 文案，后端不提供）。未知键仍会渲染，只是显示原始键名——
//      于是后端新增一项设置时前端不必同步改，只是名字不好看。
//   2. 热力色（--heat 备选主题）是纯前端偏好，没有对应的配置键，存 localStorage。
import { patch, post, tokenParam } from '../core/api.js';
import { h, mount } from '../core/dom.js';
import { getState, setState } from '../core/store.js';
import { drawer } from '../components/drawer.js';
import { switchControl } from '../components/controls.js';
import { fail, ok } from '../components/toast.js';
import { setHeat, set as setTheme } from '../core/theme.js';

const GROUPS = [
  { prefixes: ['ui.'], title: '外观与显示' },
  { prefixes: ['capture.'], title: '采集' },
  { prefixes: ['privacy.'], title: '隐私' },
  { prefixes: ['storage.'], title: '数据' },
  { prefixes: ['server.', 'system.'], title: '系统' },
];

const LABELS = {
  'ui.theme': '主题',
  'ui.default_view': '默认周期',
  'ui.keyboard_layout': '键盘布局',
  'ui.week_starts_on': '周起始日',
  'ui.timezone': '时区',
  'ui.locale': '语言',
  'ui.shell': '外壳',
  'capture.paused': '暂停采集',
  'capture.idle_threshold_seconds': '空闲阈值（秒）',
  'capture.foreground_poll_seconds': '前台轮询间隔（秒）',
  'capture.session_flush_seconds': '会话落盘间隔（秒）',
  'capture.keyboard_backend': '键盘后端',
  'capture.store_raw_key_events': '保存原始按键事件',
  'privacy.record_window_titles': '记录窗口标题',
  'privacy.realtime_stream': '实时按键流',
  'privacy.excluded_processes': '排除的进程',
  'storage.data_dir': '数据目录',
  'storage.raw_event_retention_days': '原始事件保留天数',
  'storage.checkpoint_interval_seconds': 'WAL 检查点间隔（秒）',
  'server.port': '端口',
  'system.autostart': '开机自启',
};

const OPTION_LABELS = {
  system: '跟随系统', light: '浅色', dark: '深色',
  daily: '日', weekly: '周', monthly: '月', yearly: '年', total: '全部',
  auto: '自动', none: '关闭', raw_input: 'Raw Input', pynput: 'pynput',
  ansi104: 'ANSI 104', iso105: 'ISO 105', browser: '浏览器',
};

const HINTS = {
  'capture.store_raw_key_events': '关闭后无法按应用查看键盘热力图，也无法重算历史聚合',
  'privacy.record_window_titles': '标题是最敏感的一档数据，默认关闭。接口默认也不下发',
  'privacy.realtime_stream': '关闭后键盘视图没有实时按压动画，改为 30 秒轮询',
};

function labelOf(key) {
  return LABELS[key] || key;
}

function optionLabel(value) {
  return OPTION_LABELS[String(value)] || String(value);
}

/** 一行设置。控件类型完全由 spec.kind 决定。 */
function field(key, spec, onChange) {
  const row = h('div', { class: 'field', dataset: { available: String(spec.available !== false) } });
  const label = h(
    'div',
    { class: 'field__label' },
    h('span', { text: labelOf(key) }),
    spec.applies === 'restart' ? h('span', { class: 'field__tag', text: '需重启' }) : null,
  );
  row.append(label, control(key, spec, onChange));
  const note = spec.unavailable_reason || spec.note || HINTS[key] || '';
  if (note) row.append(h('div', { class: 'field__note', text: note }));
  return row;
}

function control(key, spec, onChange) {
  const disabled = spec.available === false;
  if (spec.kind === 'bool') {
    return switchControl({
      checked: Boolean(spec.value),
      disabled,
      label: labelOf(key),
      onChange: (value) => onChange(key, value),
    }).root;
  }
  if (spec.kind === 'enum') {
    const select = h(
      'select',
      { class: 'control', disabled, attrs: { 'aria-label': labelOf(key) } },
      ...(spec.options || []).map((option) =>
        h('option', { value: String(option), text: optionLabel(option), selected: option === spec.value }),
      ),
    );
    select.addEventListener('change', () => onChange(key, select.value));
    return select;
  }
  if (spec.kind === 'int' || spec.kind === 'number') {
    const input = h('input', {
      class: 'control',
      type: 'number',
      value: spec.value === null || spec.value === undefined ? '' : String(spec.value),
      disabled,
      attrs: {
        'aria-label': labelOf(key),
        min: spec.min === undefined ? null : String(spec.min),
        max: spec.max === undefined ? null : String(spec.max),
        step: spec.kind === 'int' ? '1' : 'any',
      },
    });
    input.addEventListener('change', () => {
      const value = spec.kind === 'int' ? Number.parseInt(input.value, 10) : Number.parseFloat(input.value);
      if (Number.isNaN(value)) return;
      onChange(key, value);
    });
    return input;
  }
  if (spec.kind === 'list') {
    const value = Array.isArray(spec.value) ? spec.value.join(', ') : '';
    const input = h('input', {
      class: 'control',
      type: 'text',
      value,
      disabled,
      attrs: { 'aria-label': labelOf(key), placeholder: '用逗号分隔' },
    });
    input.addEventListener('change', () => {
      onChange(key, input.value.split(',').map((item) => item.trim()).filter(Boolean));
    });
    return input;
  }
  // string / path / 未知类型都按文本处理。未知 kind 不该让整个抽屉画不出来。
  const input = h('input', {
    class: 'control',
    type: 'text',
    value: spec.value === null || spec.value === undefined ? '' : String(spec.value),
    disabled,
    attrs: { 'aria-label': labelOf(key) },
  });
  input.addEventListener('change', () => onChange(key, input.value.trim() || null));
  return input;
}

/** 打开抽屉。payload 是 /api/v1/settings 的响应，status 是 /api/v1/status 的。 */
export function openSettings(payload, status, onReload) {
  const settings = (payload && payload.settings) || {};
  const body = h('div');

  const apply = async (key, value) => {
    try {
      const result = await patch('/settings', { settings: { [key]: value } });
      const rejected = (result.rejected || []).find((item) => item.key === key);
      if (rejected) {
        fail(`${labelOf(key)}：${rejected.message}`);
        return;
      }
      // 谎称已生效是这里最糟的失败模式——用户会以为自己关掉了某项采集。
      const restart = (result.requires_restart || []).includes(key);
      ok(restart ? `${labelOf(key)} 已保存，重启后生效` : `${labelOf(key)} 已生效`);
      if (key === 'ui.theme') setTheme(String(value));
      if (key === 'ui.week_starts_on') setState('prefs', { weekStartsOn: Number(value) || 0 });
      if (key === 'ui.keyboard_layout') setState('prefs', { keyboardLayout: String(value) });
      if (onReload) onReload();
    } catch (error) {
      fail(error.field ? `${error.field}：${error.message}` : error.message);
    }
  };

  for (const group of GROUPS) {
    const keys = Object.keys(settings)
      .filter((key) => group.prefixes.some((prefix) => key.startsWith(prefix)))
      .sort();
    if (!keys.length) continue;
    const section = h('section', { class: 'settings-group' }, h('h3', { class: 'settings-group__title', text: group.title }));
    for (const key of keys) {
      if (key === 'capture.paused') {
        section.append(pauseField(settings[key]));
        continue;
      }
      if (key === 'system.autostart') {
        section.append(autostartField(settings[key], onReload));
        continue;
      }
      section.append(field(key, settings[key], apply));
    }
    if (group.prefixes[0] === 'ui.') section.append(heatField());
    body.append(section);
  }

  body.append(dataSection(status));
  body.append(capabilitySection());
  body.append(aboutSection(status));

  return drawer({
    title: '设置',
    body,
    footer: h('span', { text: `配置文件：${(payload && payload.config_path) || '-'}` }),
  });
}

/** server. 与 system. 都归"系统"，合并成一节。 */

/** 暂停走专用端点：它除了写配置还要真的停掉采集线程（05 文档 §7）。 */
function pauseField(spec) {
  const row = h('div', { class: 'field' });
  const toggle = switchControl({
    checked: Boolean(spec.value),
    label: '暂停采集',
    onChange: async (value) => {
      try {
        const result = await post('/capture/pause', { paused: value });
        ok(result.paused ? '采集已暂停' : '采集已恢复');
      } catch (error) {
        fail(error.message);
      }
    },
  });
  row.append(h('div', { class: 'field__label' }, h('span', { text: '暂停采集' })), toggle.root);
  row.append(h('div', {
    class: 'field__note',
    text: '暂停期间不记录任何按键与前台时长。本次运行不会自动恢复。',
  }));
  return row;
}

/** 开机自启也走专用端点：它要写注册表，能力缺失时返回 422（不是"设置失败"）。 */
function autostartField(spec, onReload) {
  const row = h('div', { class: 'field', dataset: { available: String(spec.available !== false) } });
  const toggle = switchControl({
    checked: Boolean(spec.value),
    disabled: spec.available === false,
    label: '开机自启',
    onChange: async (value) => {
      try {
        const result = await post('/settings/autostart', { enabled: value });
        ok(result.enabled ? '已设置开机自启' : '已取消开机自启');
        if (onReload) onReload();
      } catch (error) {
        fail(error.message);
      }
    },
  });
  row.append(h('div', { class: 'field__label' }, h('span', { text: '开机自启' })), toggle.root);
  if (spec.unavailable_reason) row.append(h('div', { class: 'field__note', text: spec.unavailable_reason }));
  return row;
}

/** 热力色是纯前端偏好：没有配置键，也不需要有（06 文档 §3.1 的橙色备选）。 */
function heatField() {
  const row = h('div', { class: 'field' });
  const select = h(
    'select',
    { class: 'control', attrs: { 'aria-label': '热力色' } },
    h('option', { value: 'blue', text: '蓝色', selected: getState().heat !== 'warm' }),
    h('option', { value: 'warm', text: '暖色', selected: getState().heat === 'warm' }),
  );
  select.addEventListener('change', () => setHeat(select.value));
  row.append(h('div', { class: 'field__label' }, h('span', { text: '热力色' })), select);
  row.append(h('div', { class: 'field__note', text: '仅影响本机浏览器，不写入配置' }));
  return row;
}

/** 数据段：导出可用，备份/重算/删除排在后续版本——**显示但禁用并说明**，不假装能用。 */
function dataSection(status) {
  const database = (status && status.database) || {};
  const range = (status && status.data_range) || {};
  const size = database.size_bytes ? `${(database.size_bytes / 1048576).toFixed(1)} MB` : '-';
  return h(
    'section',
    { class: 'settings-group' },
    h('h3', { class: 'settings-group__title', text: '数据与导出' }),
    h(
      'dl',
      { class: 'kv-list' },
      h('dt', { text: '数据库' }), h('dd', { text: size }),
      h('dt', { text: '数据范围' }), h('dd', { text: range.min_date ? `${range.min_date} 至 ${range.max_date}` : '暂无数据' }),
      h('dt', { text: 'schema' }), h('dd', { text: String(database.schema_version || '-') }),
    ),
    h(
      'div',
      { class: 'app-actions' },
      exportButton('usage', 'csv', '导出使用记录 CSV'),
      exportButton('keyboard', 'csv', '导出键盘统计 CSV'),
      exportButton('all', 'json', '导出全部 JSON'),
    ),
    h(
      'div',
      { class: 'app-actions' },
      h('button', {
        class: 'button', type: 'button', text: '从旧版导入数据…',
        attrs: { 'data-action': 'import:open' },
      }),
    ),
    h('div', { class: 'field__note', text: '备份、重算聚合与删除数据排在后续版本。' }),
  );
}

/**
 * 导出用普通链接而不是 fetch：响应是流式的附件，交给浏览器下载最省事。
 * 令牌走查询串（下载请求带不了自定义头，与图标同一个理由）。
 */
function exportButton(scope, format, label) {
  const period = getState().period;
  const params = new URLSearchParams({ scope, format, range: period.range });
  if (period.range === 'custom') {
    if (period.start) params.set('start', period.start);
    if (period.end) params.set('end', period.end);
  } else if (period.date) {
    params.set('date', period.date);
  }
  return h('a', {
    class: 'button',
    text: label,
    href: `/api/v1/export?${params.toString()}&token=${encodeURIComponent(tokenParam())}`,
    attrs: { download: '' },
  });
}

/** 能力说明：所有 degraded 都在这里列全，横幅只上 error 一级。 */
function capabilitySection() {
  const { capabilities, degraded } = getState();
  const rows = [];
  const names = {
    keyboard: '键盘采集', foreground: '应用归因', window_titles: '窗口标题',
    idle: '空闲检测', icons: '应用图标', autostart: '开机自启', tray: '托盘图标',
    keyboard_durations: '按压时长', key_position_stable: '左右键位可分',
  };
  for (const [key, name] of Object.entries(names)) {
    if (!capabilities || capabilities[key] === undefined) continue;
    rows.push(h('dt', { text: name }));
    rows.push(h('dd', { text: capabilities[key] ? '可用' : '不可用' }));
  }
  return h(
    'section',
    { class: 'settings-group' },
    h('h3', { class: 'settings-group__title', text: '运行环境能力' }),
    h('dl', { class: 'kv-list' }, ...rows),
    ...(degraded || []).map((notice) =>
      h(
        'div',
        { class: 'notice', dataset: { severity: notice.severity } },
        h('span', { class: 'notice__mark', attrs: { 'aria-hidden': 'true' }, text: 'i' }),
        h(
          'div',
          null,
          h('div', { class: 'notice__title', text: notice.title }),
          h('div', { class: 'notice__detail', text: notice.detail }),
          notice.hint ? h('div', { class: 'notice__hint', text: notice.hint }) : null,
        ),
      ),
    ),
  );
}

function aboutSection(status) {
  const platform = (status && status.platform) || {};
  return h(
    'section',
    { class: 'settings-group' },
    h('h3', { class: 'settings-group__title', text: '关于' }),
    h(
      'dl',
      { class: 'kv-list' },
      h('dt', { text: '版本' }), h('dd', { text: (status && status.version) || '-' }),
      // platform 是纯展示信息，不参与任何逻辑分支（06 文档 §9 最后一段）。
      h('dt', { text: '运行环境' }), h('dd', { text: `${platform.id || '-'} ${platform.os_version || ''}` }),
      h('dt', { text: '支持级别' }), h('dd', { text: platform.tier ? `${platform.tier} 级` : '-' }),
      h('dt', { text: '端口' }), h('dd', { text: String((status && status.port) || '-') }),
    ),
    h('div', {
      class: 'field__note',
      text: '所有数据只保存在本机，不上传任何服务器。本程序不记录按键内容，只记录按了哪个键、多少次。',
    }),
  );
}
