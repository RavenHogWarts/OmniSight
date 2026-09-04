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
import { Drawer, openOverlay } from '../components/Drawer.tsx';
import { Switch } from '../components/controls.tsx';
import { fail, ok } from '../components/toast.tsx';
import { get as apiGet, messageOf, patch, post, tokenParam } from '../core/api.ts';
import { getState, setState } from '../core/store.ts';
import { useSlice } from '../core/useStore.ts';
import { setHeat, set as setTheme } from '../core/theme.ts';
import type { SettingField, SettingValue, SettingsResponse, StatusResponse } from '../types/api.d.ts';

const GROUPS = [
  { prefixes: ['ui.'], title: '外观与显示' },
  { prefixes: ['capture.'], title: '采集' },
  { prefixes: ['privacy.'], title: '隐私' },
  { prefixes: ['storage.'], title: '数据' },
  // server. 与 system. 都归"系统"，合并成一节。
  { prefixes: ['server.', 'system.'], title: '系统' },
];

const LABELS: Record<string, string> = {
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
  'system.autostart_elevated': '登录时以管理员身份启动',
};

const OPTION_LABELS: Record<string, string> = {
  system: '跟随系统',
  light: '浅色',
  dark: '深色',
  daily: '日',
  weekly: '周',
  monthly: '月',
  yearly: '年',
  total: '全部',
  auto: '自动',
  none: '关闭',
  raw_input: 'Raw Input',
  pynput: 'pynput',
  ansi104: 'ANSI 104',
  iso105: 'ISO 105',
  browser: '浏览器',
};

const HINTS: Record<string, string> = {
  'capture.store_raw_key_events': '关闭后无法按应用查看键盘热力图，也无法重算历史聚合',
  'privacy.record_window_titles': '标题是最敏感的一档数据，默认关闭。接口默认也不下发',
  'privacy.realtime_stream': '关闭后键盘视图没有实时按压动画，改为 30 秒轮询',
};

function labelOf(key: string): string {
  return LABELS[key] || key;
}

function optionLabel(value: SettingValue): string {
  return OPTION_LABELS[String(value)] || String(value);
}

/** 能力名的中文。`capabilities` 只读布尔值，这里只是给它们起个名字。 */
const CAPABILITY_NAMES: Record<string, string> = {
  keyboard: '键盘采集',
  foreground: '应用归因',
  window_titles: '窗口标题',
  idle: '空闲检测',
  icons: '应用图标',
  autostart: '开机自启',
  tray: '托盘图标',
  keyboard_durations: '按压时长',
  key_position_stable: '左右键位可分',
};

/**
 * 打开设置抽屉。先把 settings 与 status 取回来再开——半张空表单比等半秒更糟。
 *
 * `onReload` 由 main.tsx 给：改完设置要重读状态并重取当前视图的数据。
 */
export async function openSettingsDrawer(onReload: () => void): Promise<void> {
  try {
    const [settings, status] = await Promise.all([apiGet('/settings'), apiGet('/status')]);
    setState('settings', settings as SettingsResponse);
    setState('status', status as StatusResponse);
    openOverlay(
      <Drawer
        title="设置"
        footer={
          <span>配置文件：{(settings as SettingsResponse)?.config_path || '-'}</span>
        }
      >
        <Settings onReload={onReload} />
      </Drawer>,
    );
  } catch (error) {
    fail(messageOf(error, '打开设置失败'));
  }
}

function Settings({ onReload }: { onReload: () => void }) {
  const payload = useSlice('settings');
  const status = useSlice('status');
  const settings = payload?.settings || {};

  const apply = async (key: string, value: SettingValue) => {
    try {
      const result = (await patch('/settings', { settings: { [key]: value } })) as {
        rejected?: { key: string; message: string }[];
        requires_restart?: string[];
      };
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
      onReload();
    } catch (error) {
      fail(messageOf(error));
    }
  };

  return (
    <div>
      {GROUPS.map((group) => {
        const keys = Object.keys(settings)
          .filter((key) => group.prefixes.some((prefix) => key.startsWith(prefix)))
          .sort();
        if (!keys.length) return null;
        return (
          <section className="settings-group" key={group.title}>
            <h3 className="settings-group__title">{group.title}</h3>
            {keys.map((key) => {
              const spec = settings[key];
              if (key === 'capture.paused') return <PauseField key={key} spec={spec} />;
              if (key === 'system.autostart') {
                return <ActionToggle key={key} settingKey={key} spec={spec} path="/settings/autostart" onReload={onReload} />;
              }
              if (key === 'system.autostart_elevated') {
                return <ActionToggle key={key} settingKey={key} spec={spec} path="/settings/autostart-elevated" onReload={onReload} />;
              }
              return <Field key={key} settingKey={key} spec={spec} onChange={apply} />;
            })}
            {group.prefixes[0] === 'ui.' ? <HeatField /> : null}
          </section>
        );
      })}
      <DataSection status={status} />
      <CapabilitySection />
      <AboutSection status={status} />
    </div>
  );
}

/** 一行设置。控件类型完全由 spec.kind 决定。 */
function Field({
  settingKey,
  spec,
  onChange,
}: {
  settingKey: string;
  spec: SettingField;
  onChange: (key: string, value: SettingValue) => void;
}) {
  const note = spec.unavailable_reason || spec.note || HINTS[settingKey] || '';
  return (
    <div className="field" data-available={String(spec.available !== false)}>
      <div className="field__label">
        <span>{labelOf(settingKey)}</span>
        {spec.applies === 'restart' ? <span className="field__tag">需重启</span> : null}
      </div>
      <Control settingKey={settingKey} spec={spec} onChange={onChange} />
      {note ? <div className="field__note">{note}</div> : null}
    </div>
  );
}

function Control({
  settingKey,
  spec,
  onChange,
}: {
  settingKey: string;
  spec: SettingField;
  onChange: (key: string, value: SettingValue) => void;
}) {
  const disabled = spec.available === false;
  const label = labelOf(settingKey);

  if (spec.kind === 'bool') {
    return (
      <Switch
        checked={Boolean(spec.value)}
        disabled={disabled}
        label={label}
        onChange={(value) => onChange(settingKey, value)}
      />
    );
  }
  if (spec.kind === 'enum') {
    return (
      <select
        className="control"
        disabled={disabled}
        aria-label={label}
        value={String(spec.value ?? '')}
        onChange={(event) => onChange(settingKey, event.target.value)}
      >
        {(spec.options || []).map((option) => (
          <option value={String(option)} key={String(option)}>
            {optionLabel(option)}
          </option>
        ))}
      </select>
    );
  }
  if (spec.kind === 'int' || spec.kind === 'number') {
    return (
      <input
        className="control"
        type="number"
        defaultValue={spec.value === null || spec.value === undefined ? '' : String(spec.value)}
        disabled={disabled}
        aria-label={label}
        min={spec.min === undefined ? undefined : String(spec.min)}
        max={spec.max === undefined ? undefined : String(spec.max)}
        step={spec.kind === 'int' ? '1' : 'any'}
        onChange={(event) => {
          const raw = event.target.value;
          const value = spec.kind === 'int' ? Number.parseInt(raw, 10) : Number.parseFloat(raw);
          if (Number.isNaN(value)) return;
          onChange(settingKey, value);
        }}
      />
    );
  }
  if (spec.kind === 'list') {
    return (
      <input
        className="control"
        type="text"
        defaultValue={Array.isArray(spec.value) ? spec.value.join(', ') : ''}
        disabled={disabled}
        aria-label={label}
        placeholder="用逗号分隔"
        onBlur={(event) =>
          onChange(
            settingKey,
            event.target.value
              .split(',')
              .map((item) => item.trim())
              .filter(Boolean),
          )
        }
      />
    );
  }
  // string / path / 未知类型都按文本处理。未知 kind 不该让整个抽屉画不出来。
  return (
    <input
      className="control"
      type="text"
      defaultValue={spec.value === null || spec.value === undefined ? '' : String(spec.value)}
      disabled={disabled}
      aria-label={label}
      onBlur={(event) => onChange(settingKey, event.target.value.trim() || null)}
    />
  );
}

/** 暂停走专用端点：它除了写配置还要真的停掉采集线程（05 文档 §7）。 */
function PauseField({ spec }: { spec: SettingField }) {
  return (
    <div className="field">
      <div className="field__label">
        <span>暂停采集</span>
      </div>
      <Switch
        checked={Boolean(spec.value)}
        label="暂停采集"
        onChange={async (value) => {
          try {
            const result = (await post('/capture/pause', { paused: value })) as { paused?: boolean };
            ok(result.paused ? '采集已暂停' : '采集已恢复');
          } catch (error) {
            fail(messageOf(error));
          }
        }}
      />
      <div className="field__note">
        暂停期间不记录任何按键与前台时长。本次运行不会自动恢复。
      </div>
    </div>
  );
}

/**
 * 走专用端点的开关：开机自启要写注册表、「登录时以管理员身份启动」要建计划任务
 * （10 文档 §5.3），能力缺失时后端返回 422（不是"设置失败"）。
 *
 * 不可用的原因**一定要显示**：提权那个开关多数时候是灰的（要装到 Program Files、
 * 要先提权），而三种原因对应三种完全不同的下一步动作。原因与说明两行都留着——
 * 只显示原因的话，用户不知道这个开关本来是干什么的。
 */
function ActionToggle({
  settingKey,
  spec,
  path,
  onReload,
}: {
  settingKey: string;
  spec: SettingField;
  path: string;
  onReload: () => void;
}) {
  const label = labelOf(settingKey);
  return (
    <div className="field" data-available={String(spec.available !== false)}>
      <div className="field__label">
        <span>{label}</span>
      </div>
      <Switch
        checked={Boolean(spec.value)}
        disabled={spec.available === false}
        label={label}
        onChange={async (value) => {
          try {
            const result = (await post(path, { enabled: value })) as {
              enabled?: boolean;
              note?: string;
            };
            ok(
              [result.enabled ? `已开启${label}` : `已关闭${label}`, result.note]
                .filter(Boolean)
                .join('；'),
            );
          } catch (error) {
            fail(messageOf(error));
          }
          // 成功与失败都重读：失败时开关已经被点着了而真实状态没变（例如"要先关掉
          // 登录任务"那个 422），留着一个反的开关就是谎报。
          onReload();
        }}
      />
      {spec.unavailable_reason ? (
        <div className="field__note">{spec.unavailable_reason}</div>
      ) : null}
      {spec.note ? <div className="field__note">{spec.note}</div> : null}
    </div>
  );
}

/** 热力色是纯前端偏好：没有配置键，也不需要有（06 文档 §3.1 的橙色备选）。 */
function HeatField() {
  const heat = useSlice('heat');
  return (
    <div className="field">
      <div className="field__label">
        <span>热力色</span>
      </div>
      <select
        className="control"
        aria-label="热力色"
        value={heat === 'warm' ? 'warm' : 'blue'}
        onChange={(event) => setHeat(event.target.value)}
      >
        <option value="blue">蓝色</option>
        <option value="warm">暖色</option>
      </select>
      <div className="field__note">仅影响本机浏览器，不写入配置</div>
    </div>
  );
}

/**
 * 导出用普通链接而不是 fetch：响应是流式的附件，交给浏览器下载最省事。
 * 令牌走查询串（下载请求带不了自定义头，与图标同一个理由）。
 */
function ExportLink({ scope, format, label }: { scope: string; format: string; label: string }) {
  const period = getState().period;
  const params = new URLSearchParams({ scope, format, range: period.range });
  if (period.range === 'custom') {
    if (period.start) params.set('start', period.start);
    if (period.end) params.set('end', period.end);
  } else if (period.date) {
    params.set('date', period.date);
  }
  return (
    <a
      className="button"
      href={`/api/v1/export?${params.toString()}&token=${encodeURIComponent(tokenParam())}`}
      download=""
    >
      {label}
    </a>
  );
}

/** 数据段：导出可用，备份/重算/删除排在后续版本——**显示但禁用并说明**，不假装能用。 */
function DataSection({ status }: { status: StatusResponse | null }) {
  const database = status?.database;
  const range = status?.data_range;
  const size = database?.size_bytes ? `${(database.size_bytes / 1048576).toFixed(1)} MB` : '-';
  return (
    <section className="settings-group">
      <h3 className="settings-group__title">数据与导出</h3>
      <dl className="kv-list">
        <dt>数据库</dt>
        <dd>{size}</dd>
        <dt>数据范围</dt>
        <dd>{range?.min_date ? `${range.min_date} 至 ${range.max_date}` : '暂无数据'}</dd>
        <dt>schema</dt>
        <dd>{String(database?.schema_version || '-')}</dd>
      </dl>
      <div className="app-actions">
        <ExportLink scope="usage" format="csv" label="导出使用记录 CSV" />
        <ExportLink scope="keyboard" format="csv" label="导出键盘统计 CSV" />
        <ExportLink scope="all" format="json" label="导出全部 JSON" />
      </div>
      <div className="app-actions">
        <button className="button" type="button" data-action="import:open">
          从旧版导入数据…
        </button>
        {/* 首启说明不该是"只在第一次能看到"的东西：数据位置与隐私边界是用户随时
            会想再确认一次的事实（08 文档 §6.1）。托盘里那一项与这里是同一个入口。 */}
        <button className="button" type="button" data-action="about:open">
          关于与隐私说明…
        </button>
      </div>
      <div className="field__note">备份、重算聚合与删除数据排在后续版本。</div>
    </section>
  );
}

/** 能力说明：所有 degraded 都在这里列全，横幅只上 error 一级。 */
function CapabilitySection() {
  const capabilities = useSlice('capabilities');
  const degraded = useSlice('degraded');
  const read = capabilities as unknown as Record<string, unknown> | null;
  return (
    <section className="settings-group">
      <h3 className="settings-group__title">运行环境能力</h3>
      <dl className="kv-list">
        {Object.entries(CAPABILITY_NAMES).map(([key, name]) => {
          if (!read || read[key] === undefined) return null;
          return (
            <div key={key} style={{ display: 'contents' }}>
              <dt>{name}</dt>
              <dd>{read[key] ? '可用' : '不可用'}</dd>
            </div>
          );
        })}
      </dl>
      {(degraded || []).map((notice) => (
        <div className="notice" data-severity={notice.severity} key={notice.code || notice.title}>
          <span className="notice__mark" aria-hidden="true">
            i
          </span>
          <div>
            <div className="notice__title">{notice.title}</div>
            <div className="notice__detail">{notice.detail}</div>
            {notice.hint ? <div className="notice__hint">{notice.hint}</div> : null}
          </div>
        </div>
      ))}
    </section>
  );
}

function AboutSection({ status }: { status: StatusResponse | null }) {
  const platform = status?.platform;
  return (
    <section className="settings-group">
      <h3 className="settings-group__title">关于</h3>
      <dl className="kv-list">
        <dt>版本</dt>
        <dd>{status?.version || '-'}</dd>
        {/* platform 是纯展示信息，不参与任何逻辑分支（06 文档 §9 最后一段）。 */}
        <dt>运行环境</dt>
        <dd>{`${platform?.id || '-'} ${platform?.os_version || ''}`}</dd>
        <dt>支持级别</dt>
        <dd>{platform?.tier ? `${platform.tier} 级` : '-'}</dd>
        <dt>端口</dt>
        <dd>{String(status?.port || '-')}</dd>
      </dl>
      <div className="field__note">
        所有数据只保存在本机，不上传任何服务器。本程序不记录按键内容，只记录按了哪个键、多少次。
      </div>
    </section>
  );
}
