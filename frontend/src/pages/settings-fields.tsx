// 设置页的一行一项（18 文档 批 2）。原先长在设置抽屉里（`views/settings.tsx`），除了
// 落脚处换成独立页面，控件本身一行没改——**表单仍然由 `GET /api/v1/settings` 的元数据
// 生成**，每项自带 kind / 取值范围 / options / available / unavailable_reason / applies，
// 因此这里没有一行"哪个开关在哪个平台上要隐藏"的知识（07 文档 §10 第 4 行）。
//
// 不可用的项**显示但禁用**，旁边给出原因。隐藏会让用户以为功能不存在并去别处找；
// 禁用加解释才能传达"这台机器上办不到"。
//
// 前端唯一自带的是字段的中文标签（UI 文案，后端不提供）。未知键仍会渲染，只是显示原始
// 键名——于是后端新增一项设置时前端不必同步改，只是名字不好看。
import { useState } from 'react';
import { Icon } from '../components/Icon.tsx';
import type { IconName } from '../components/Icon.tsx';
import { Switch } from '../components/controls.tsx';
import { fail, ok } from '../components/toast.tsx';
import { messageOf, post } from '../core/api.ts';
import type { SettingField, SettingValue } from '../types/api.d.ts';

/** 一项设置改完之后由页面负责落盘与提示。 */
export type ApplyFn = (key: string, value: SettingValue) => void;

const LABELS: Record<string, string> = {
  'ui.theme': '主题',
  // 18 批 3 起它是一条真的配置（`ui.heat`），不再是只存 localStorage 的前端偏好。
  'ui.heat': '热力色',
  'ui.default_view': '默认周期',
  'ui.keyboard_layout': '键盘布局',
  'ui.week_starts_on': '周起始日',
  'ui.timezone': '时区',
  'ui.locale': '语言',
  'ui.shell': '外壳',
  'ui.settings_surface': '设置打开方式',
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
  blue: '蓝色',
  warm: '暖色',
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
  drawer: '侧边抽屉',
  page: '独立页面',
  'zh-CN': '中文（简体）',
};

const HINTS: Record<string, string> = {
  'capture.store_raw_key_events': '关闭后无法按应用查看键盘热力图，也无法重算历史聚合',
  'privacy.record_window_titles': '标题是最敏感的一档数据，默认关闭。接口默认也不下发',
  'privacy.realtime_stream': '关闭后键盘视图没有实时按压动画，改为 30 秒轮询',
  'ui.heat': '键盘热力图与日历格子的色阶。写入配置，因此换浏览器也一致',
};

export function labelOf(key: string): string {
  return LABELS[key] || key;
}

function optionLabel(value: SettingValue, effective?: string): string {
  const text = String(value ?? '');
  // 空串是"没有配置"那一档（时区留空 = 跟随系统）。**把此刻实际在用的那一个写进标签**：
  // 光是"跟随系统"四个字回答不了"那到底是哪个时区"，而那正是来看这一项的人要问的。
  if (text === '') return effective ? `跟随系统（${effective}）` : '跟随系统';
  return OPTION_LABELS[text] || text;
}

/**
 * 把 `Asia/Shanghai` 这类选项按第一段分组。不带 `/` 的留在最前面（`""`、`UTC`）。
 *
 * 600 条时区平铺在一个下拉里找不动；分了组之后与系统设置里那个时区选择器读起来一样。
 * 普通枚举（主题、周起始日）没有 `/`，因此全部落在 `plain` 里——它们的渲染一行没变。
 */
function groupOptions(options: readonly SettingValue[]): {
  plain: string[];
  groups: [string, string[]][];
} {
  const plain: string[] = [];
  const groups = new Map<string, string[]>();
  for (const option of options) {
    const text = String(option ?? '');
    const slash = text.indexOf('/');
    if (slash <= 0) {
      plain.push(text);
      continue;
    }
    const region = text.slice(0, slash);
    const bucket = groups.get(region);
    if (bucket) bucket.push(text);
    else groups.set(region, [text]);
  }
  return { plain, groups: [...groups] };
}

/** 一行设置。控件类型完全由 spec.kind 决定。 */
export function Field({
  settingKey,
  spec,
  onChange,
}: {
  settingKey: string;
  spec: SettingField;
  onChange: ApplyFn;
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
  onChange: ApplyFn;
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
  // **判据是"有没有 options"，不是 kind === 'enum'**：时区是一个 string 项（任何 IANA 名都
  // 合法，校验在 config.validate 里），但后端把本机 tzdata 的全部时区当 options 一起下发了
  // ——那 600 条只能是一个下拉，不该是一个要用户默写 "Asia/Shanghai" 的输入框（18 批 7）。
  if (spec.options) {
    const { plain, groups } = groupOptions(spec.options);
    return (
      <select
        className="control"
        disabled={disabled}
        aria-label={label}
        value={String(spec.value ?? '')}
        onChange={(event) => onChange(settingKey, event.target.value)}
      >
        {plain.map((option) => (
          <option value={option} key={option || '__auto__'}>
            {optionLabel(option, spec.effective)}
          </option>
        ))}
        {groups.map(([region, items]) => (
          <optgroup label={region} key={region}>
            {items.map((option) => (
              <option value={option} key={option}>
                {option}
              </option>
            ))}
          </optgroup>
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
  // string / path / 未知类型都按文本处理。未知 kind 不该让整页画不出来。
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
export function PauseField({ spec }: { spec: SettingField }) {
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
            const result = (await post('/capture/pause', { paused: value })) as {
              paused?: boolean;
            };
            ok(result.paused ? '采集已暂停' : '采集已恢复');
          } catch (error) {
            fail(messageOf(error));
          }
        }}
      />
      <div className="field__note">
        暂停期间不记录任何按键与前台时长。本次运行不会自动恢复。托盘菜单里那一项是同一条路径。
      </div>
    </div>
  );
}

/**
 * 走专用端点的开关：开机自启要写注册表、「登录时以管理员身份启动」要建计划任务
 * （10 文档 §5.3），能力缺失时后端返回 422（不是"设置失败"）。
 *
 * **这两项的真源是操作系统，不是 config.json**（注册表项 / 登录计划任务）。写进配置文件
 * 就会立刻有两份真相——"配置说开着、注册表里没有"，而 10 文档 §4 有一条不可退让的要求：
 * 任何一条机制开着时，界面都不许显示"开机自启：关"。因此它们留在这里而不是进配置。
 * 18 批 4 起托盘里那个勾选框撤掉了，这里是它唯一的落脚处。
 *
 * 不可用的原因**一定要显示**：提权那个开关多数时候是灰的（要装到 Program Files、
 * 要先提权），而三种原因对应三种完全不同的下一步动作。
 */
export function ActionToggle({
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
/**
 * 一行"动作"：左边是名字，控件位上是一个图标钮（18 文档 批 7）。
 *
 * 这些动作原先是一排文字按钮挤在卡片底部。一排按钮读起来是"这张卡的操作"，而它们其实与上面
 * 那些一行一项是同一类东西——一个名字、一个控件。名字回到标签列之后还顺带解决了按钮宽度：
 * 「导出使用记录 CSV」这种长度的按钮怎么排都排不齐，而标签列天然对齐。
 *
 * 图标钮一律带 `aria-label`：控件位上没有文字，屏幕阅读器读不到左边那一列。
 */
export function ActionField({
  label,
  icon,
  note,
  href,
  download = false,
  onClick,
}: {
  label: string;
  icon: IconName;
  note?: string;
  /** 给链接式动作（导出、去另一个页面）。与 `onClick` 二选一。 */
  href?: string;
  download?: boolean;
  onClick?: () => void;
}) {
  return (
    <div className="field">
      <div className="field__label">
        <span>{label}</span>
      </div>
      {href ? (
        <a
          className="icon-button"
          href={href}
          aria-label={label}
          download={download ? '' : undefined}
        >
          <Icon name={icon} />
        </a>
      ) : (
        <button className="icon-button" type="button" aria-label={label} onClick={onClick}>
          <Icon name={icon} />
        </button>
      )}
      {note ? <div className="field__note">{note}</div> : null}
    </div>
  );
}

/**
 * 名单类设置（当前只有「排除的进程」）：**标签 + 一个输入框**，不是一行逗号分隔的长文本。
 *
 * 逗号分隔那种写法的三个毛病都只在真的去用的时候才发现：改一项要先把整行读懂、删一项要连着
 * 一个逗号一起删干净、而"要不要写 .exe"没有任何提示。标签形态里每一项自带一个删除位，新增
 * 敲回车，占位符里就写着一个例子（18 文档 批 7）。
 *
 * 粘贴一串也认：空白、半角与全角逗号都当分隔符——用户手里那份名单多半就是这种形状。
 */
export function TagsField({
  settingKey,
  spec,
  onChange,
}: {
  settingKey: string;
  spec: SettingField;
  onChange: ApplyFn;
}) {
  const values = Array.isArray(spec.value) ? spec.value.map(String) : [];
  const [draft, setDraft] = useState('');
  const disabled = spec.available === false;
  const label = labelOf(settingKey);

  const commit = (text: string) => {
    const additions = text
      .split(/[,，;；\s]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    setDraft('');
    if (!additions.length) return;
    const merged = [...values];
    for (const item of additions) {
      // 进程名在 Windows 上不分大小写，两条只差大小写的规则只会让人以为没生效。
      if (!merged.some((existing) => existing.toLowerCase() === item.toLowerCase())) {
        merged.push(item);
      }
    }
    if (merged.length !== values.length) onChange(settingKey, merged);
  };

  return (
    <div className="field field--stack" data-available={String(!disabled)}>
      <div className="field__label">
        <span>{label}</span>
        {spec.applies === 'restart' ? <span className="field__tag">需重启</span> : null}
      </div>
      <div className="tag-input" data-empty={values.length ? undefined : 'true'}>
        {values.map((value) => (
          <span className="tag" key={value}>
            {value}
            <button
              className="tag__remove"
              type="button"
              aria-label={`不再排除 ${value}`}
              disabled={disabled}
              onClick={() => onChange(settingKey, values.filter((item) => item !== value))}
            >
              <Icon name="close" />
            </button>
          </span>
        ))}
        <input
          className="tag-input__field"
          type="text"
          value={draft}
          disabled={disabled}
          aria-label={`添加${label}`}
          placeholder={values.length ? '再加一个…' : '输入进程名后回车，例如 KeePass.exe'}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ',' || event.key === '，') {
              event.preventDefault();
              commit(draft);
              return;
            }
            // 空输入框上按退格删掉最后一个标签：与所有标签输入框一致的手感。
            if (event.key === 'Backspace' && !draft && values.length) {
              event.preventDefault();
              onChange(settingKey, values.slice(0, -1));
            }
          }}
          // 失焦也提交：敲完不按回车就走开是最常见的一种"以为已经加上了"。
          onBlur={() => commit(draft)}
        />
      </div>
      {spec.note ? <div className="field__note">{spec.note}</div> : null}
      <div className="field__note">
        名单里的进程完全不被采集：既不记按键，也不记前台时长。改动立即生效。
      </div>
    </div>
  );
}

/**
 * 路径项（当前只有「数据目录」）。与普通输入框有两处不同，都来自同一个事实：**这一项留空
 * 表示"按平台惯例解析"**（18 文档 批 7）。
 *
 * 1. 留空时输入框原先是空的——而来看这一项的人要问的恰恰是"数据现在落在哪儿"。后端给了
 *    `effective`，这里把它放进 placeholder，并在说明行里再写一遍：placeholder 在 200px 的
 *    控件里一定会被截断，而路径的关键部分在末尾。
 * 2. 旁边直接给一个打开那个目录的按钮——否则用户得先把路径读出来，再自己去文件管理器里找。
 */
export function PathField({
  settingKey,
  spec,
  onChange,
  onReveal,
}: {
  settingKey: string;
  spec: SettingField;
  onChange: ApplyFn;
  onReveal?: () => void;
}) {
  const label = labelOf(settingKey);
  const disabled = spec.available === false;
  const configured = spec.value === null || spec.value === undefined ? '' : String(spec.value);
  return (
    <div className="field" data-available={String(!disabled)}>
      <div className="field__label">
        <span>{label}</span>
        {spec.applies === 'restart' ? <span className="field__tag">需重启</span> : null}
      </div>
      <div className="control-row">
        <input
          className="control"
          type="text"
          defaultValue={configured}
          disabled={disabled}
          aria-label={label}
          placeholder={spec.effective || ''}
          onBlur={(event) => {
            const next = event.target.value.trim();
            if (next !== configured) onChange(settingKey, next || null);
          }}
        />
        {onReveal ? (
          <button
            className="icon-button"
            type="button"
            aria-label={`打开${label}`}
            onClick={onReveal}
          >
            <Icon name="folder" />
          </button>
        ) : null}
      </div>
      {spec.note ? <div className="field__note">{spec.note}</div> : null}
      <div className="field__note">
        {configured ? '当前使用：' : '留空表示按平台惯例解析。当前使用：'}
        <span className="mono">{spec.effective || '-'}</span>
      </div>
    </div>
  );
}
