// 设置的正文。**它有两个落脚处**（18 文档 §2.1），由 `ui.settings_surface` 决定：
//
//   `page`   —— `/settings` 那一页（托盘那一项、深链、以及"一次看完所有设置"走的是它）。
//   `drawer` —— 仪表盘右侧的抽屉（06 文档 §9 的原方案），改完立刻看见图表跟着变。
//
// 两档共用这一个组件，因此没有"抽屉版设置"这种东西——那是一份迟早与另一份不一样的副本。
// 差别只有三处，全部收在 `surface` 上：页面那一档多一个大标题、段落写进 hash（深链）、并
// 监听 hash 变化。**抽屉里一个字都不许写进 hash**：仪表盘的路由与周期就在那里
// （`#/apps?range=week&date=…`），写一个 `#privacy` 进去等于顺手把视图和周期一起重置了。
//
// **段导航用 `.viewbar`，不用侧栏**：这一页所有导航都是"居中定宽控件带"，而侧栏在这套设计
// 里没有先例；分段切换器还顺带让每一段都是短的一屏，不必滚三千像素。
//
// **表单仍然由 `GET /api/v1/settings` 的元数据生成**（一行一项的实现在 settings-fields.tsx）。
import { useEffect, useState } from 'react';
import { Icon } from '../components/Icon.tsx';
import { Card } from '../components/Card.tsx';
import { fail, ok } from '../components/toast.tsx';
import { get as apiGet, messageOf, patch } from '../core/api.ts';
import { emit, on as busOn } from '../core/bus.ts';
import { setState } from '../core/store.ts';
import { useSlice } from '../core/useStore.ts';
import { setHeat, set as setTheme } from '../core/theme.ts';
import { ActionToggle, Field, PathField, PauseField, TagsField, labelOf } from './settings-fields.tsx';
import type { ApplyFn } from './settings-fields.tsx';
import { AboutCard, CapabilityCard, DataCard, revealDirectory } from './settings-sections.tsx';
import type { SettingsResponse, StatusResponse } from '../types/api.d.ts';

interface Group {
  id: string;
  title: string;
  /** 归到这一段的设置键前缀。`server.` 与 `system.` 合并成"系统"。 */
  prefixes: readonly string[];
}

const GROUPS: readonly Group[] = [
  { id: 'appearance', title: '外观', prefixes: ['ui.'] },
  { id: 'capture', title: '采集', prefixes: ['capture.'] },
  { id: 'privacy', title: '隐私', prefixes: ['privacy.'] },
  { id: 'data', title: '数据', prefixes: ['storage.'] },
  { id: 'system', title: '系统', prefixes: ['server.', 'system.'] },
];

/** 页顶那句话。两档共用同一份措辞：说两遍就会有一天只改了一遍。 */
const LEAD = '改动即时保存；需重启的项会标出来，从托盘菜单重启后生效。';

function groupFromHash(): string {
  const id = window.location.hash.replace(/^#\/?/, '');
  return GROUPS.some((group) => group.id === id) ? id : GROUPS[0].id;
}

/** 取一次设置与状态。入口首屏与每次改动之后都走它。 */
export async function loadSettings(): Promise<void> {
  const [settings, status] = await Promise.all([apiGet('/settings'), apiGet('/status')]);
  setState('settings', settings as SettingsResponse);
  setState('status', status as StatusResponse);
}

/** 重读表单。改完、被别处改了、以及一次失败的写入之后都走它。 */
function reload(): void {
  void loadSettings().catch(() => fail('重读设置失败'));
}

export type Surface = 'page' | 'drawer';

export function SettingsPage({ surface = 'page' }: { surface?: Surface }) {
  const payload = useSlice('settings');
  const status = useSlice('status');
  const settings = payload?.settings || {};
  const onPage = surface === 'page';
  const [group, setGroup] = useState(() => (onPage ? groupFromHash() : GROUPS[0].id));
  // 本次打开这一页之后改过、且要重启才生效的项。**只在这一页的这一次会话里成立**——
  // 服务端没有"待重启"这个状态，刷新页面它就没了，措辞因此说"本次改动"。
  const [pending, setPending] = useState<readonly string[]>([]);

  useEffect(() => {
    if (!onPage) return;
    const onHash = () => setGroup(groupFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, [onPage]);

  // 配置落盘了就重读表单。**同一条总线同时管两件事**：这一页自己刚改完（`apply` 里
  // emit），以及别处改完了（另一个标签页的 SSE `settings` 帧、或托盘里的暂停）。两者
  // 要做的事一模一样，因此不给"我自己改的"留一条捷径——那条捷径迟早与这一条分叉。
  useEffect(() => busOn('settings:changed', reload), []);

  const pick = (id: string) => {
    // replaceState 而不是 push：在设置页里换段不该在返回键上攒出五条记录。
    if (onPage) history.replaceState(null, '', `#${id}`);
    setGroup(id);
  };

  const apply: ApplyFn = (key, value) => {
    void (async () => {
      try {
        const result = (await patch('/settings', { settings: { [key]: value } })) as {
          rejected?: { key: string; message: string }[];
          requires_restart?: string[];
        };
        const rejected = (result.rejected || []).find((item) => item.key === key);
        if (rejected) {
          fail(`${labelOf(key)}：${rejected.message}`);
          // 控件上已经是新值而服务端没收下——重读把它拨回去，否则页面在说谎。
          reload();
          return;
        }
        // 谎称已生效是这里最糟的失败模式——用户会以为自己关掉了某项采集。
        const restart = (result.requires_restart || []).includes(key);
        ok(restart ? `${labelOf(key)} 已保存，重启后生效` : `${labelOf(key)} 已生效`);
        if (restart) setPending((keys) => (keys.includes(key) ? keys : [...keys, key]));
        // 主题与热力色要立刻看得见：这一页本身就在深浅色里。
        if (key === 'ui.theme') setTheme(String(value));
        if (key === 'ui.heat') setHeat(String(value));
        // 广播"变了"，剩下的交给订阅者：这一页重读表单（上面那个 effect），而**开着的
        // 仪表盘重读偏好并重取当前视图**（main.tsx）。抽屉那一档里它就在旁边——"改了
        // 周起始日而图表还按旧的切周"会当场被看见，而那是一种不报错的错。
        emit('settings:changed', { key });
      } catch (error) {
        fail(messageOf(error));
        reload();
      }
    })();
  };

  const current = GROUPS.find((item) => item.id === group) || GROUPS[0];
  const keys = Object.keys(settings)
    .filter((key) => current.prefixes.some((prefix) => key.startsWith(prefix)))
    .sort();

  return (
    <>
      {pending.length ? <RestartNotice keys={pending} /> : null}
      {/* 抽屉自己的表头就写着「设置」（components/Drawer.tsx），再来一个 h1 是把同一个词
          说两遍；那句"改动即时保存"两档都要，它回答的是"我要不要找一个保存按钮"。 */}
      {onPage ? (
        <div className="section-heading section-heading--lead">
          <div>
            <h1 className="section-title" id="page-title">
              设置
            </h1>
            <p className="section-sub">{LEAD}</p>
          </div>
        </div>
      ) : (
        <p className="section-sub">{LEAD}</p>
      )}
      <nav className="viewbar settings-nav" role="tablist" aria-label="设置分组">
        {GROUPS.map((item) => (
          <button
            key={item.id}
            className="viewbar__tab"
            role="tab"
            type="button"
            aria-selected={item.id === current.id}
            onClick={() => pick(item.id)}
          >
            {item.title}
          </button>
        ))}
      </nav>
      <Card title={current.title}>
        {keys.length ? (
          keys.map((key) => {
            const spec = settings[key];
            if (key === 'capture.paused') return <PauseField key={key} spec={spec} />;
            // 名单与路径各有一个专用控件（18 文档 批 7）：一个逗号分隔的长输入框改不动，
            // 一个空着的路径框说不出数据现在落在哪儿。
            if (key === 'privacy.excluded_processes') {
              return <TagsField key={key} settingKey={key} spec={spec} onChange={apply} />;
            }
            if (key === 'storage.data_dir') {
              return (
                <PathField
                  key={key}
                  settingKey={key}
                  spec={spec}
                  onChange={apply}
                  onReveal={() => void revealDirectory('data')}
                />
              );
            }
            if (key === 'system.autostart' || key === 'system.autostart_elevated') {
              return (
                <ActionToggle
                  key={key}
                  settingKey={key}
                  spec={spec}
                  path={
                    key === 'system.autostart'
                      ? '/settings/autostart'
                      : '/settings/autostart-elevated'
                  }
                  onReload={reload}
                />
              );
            }
            return <Field key={key} settingKey={key} spec={spec} onChange={apply} />;
          })
        ) : (
          <p className="muted">读不到这一段的设置项。</p>
        )}
      </Card>
      {current.id === 'data' ? <DataCard status={status} /> : null}
      {current.id === 'system' ? (
        <>
          <CapabilityCard />
          <AboutCard status={status} configPath={payload?.config_path || ''} />
        </>
      ) : null}
    </>
  );
}

/**
 * 「有 N 项改动要重启后生效」。
 *
 * **这里不给重启按钮**（18 文档 批 7）：重启与退出只从托盘走。重启会中断采集几秒，而它的
 * 失败模式是"新实例起不来而旧实例已经退了"——那时页面上的按钮只会变成一个消失的标签页，
 * 而托盘图标还在。
 */
function RestartNotice({ keys }: { keys: readonly string[] }) {
  return (
    <div className="banner" data-severity="warning" role="status">
      <span className="banner__mark" aria-hidden="true">
        <Icon name="warning" />
      </span>
      <div className="banner__body">
        <div className="banner__title">本次改动有 {keys.length} 项要重启后生效</div>
        <div className="banner__detail">
          {keys.map(labelOf).join('、')}——从托盘菜单的「重新启动」生效
        </div>
      </div>
    </div>
  );
}
