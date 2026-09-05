// 设置页里那几块**不是一行一项**的内容（18 文档 批 2）：数据与导出、运行环境能力、关于。
// 原先散在设置抽屉的末尾，现在各自是一张卡。
//
// **动作也是一行一项**（18 文档 批 7）：导出、打开目录、导入都走 `ActionField`——左边是名字，
// 控件位上一个图标钮，与上下那些开关、下拉对齐。原先是三个挤在卡底的文字按钮排，读起来像
// 另一类东西，而"导出使用记录 CSV"这种长度的按钮怎么排都排不齐。
//
// 进程动作（重新启动、退出）已经从这一页撤掉，只从托盘走（18 文档 批 7）。
import { Card } from '../components/Card.tsx';
import { Icon } from '../components/Icon.tsx';
import { openImportWizard } from '../components/ImportWizard.tsx';
import { fail } from '../components/toast.tsx';
import { messageOf, post, tokenParam } from '../core/api.ts';
import { useSlice } from '../core/useStore.ts';
import type { StatusResponse } from '../types/api.d.ts';
import { ActionField } from './settings-fields.tsx';
import { pageUrl } from './shell.tsx';

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
 * 导出用普通链接而不是 fetch：响应是流式的附件，交给浏览器下载最省事。
 * 令牌走查询串（下载请求带不了自定义头，与图标同一个理由）。
 *
 * **范围固定 `total`**：设置页没有周期栏，而"从设置页导出"的合理默认是全部数据。原先它
 * 长在抽屉里，能读到仪表盘当前那个周期；独立成页之后那个上下文不存在了，继续读 store 里
 * 的默认值等于悄悄只导出了今天。
 */
function exportHref(scope: string, format: string): string {
  const params = new URLSearchParams({ scope, format, range: 'total' });
  return `/api/v1/export?${params.toString()}&token=${encodeURIComponent(tokenParam())}`;
}

/**
 * 打开数据目录 / 日志目录。**只有后端做得到**：浏览器里的页面开不了文件管理器，而"管理员
 * 模式下要降权打开"这件事本来就在后端（`lifecycle._open_external`）。托盘里那两项、以及
 * 「数据目录」那一行旁边的按钮，走的都是这一条。
 */
export async function revealDirectory(target: 'data' | 'logs'): Promise<void> {
  try {
    await post('/system/reveal', { target });
  } catch (error) {
    fail(messageOf(error, '打开目录失败'));
  }
}

/** 数据与导出。备份、重算聚合与删除数据排在后续版本——**说明而不是画一个禁用按钮**。 */
export function DataCard({ status }: { status: StatusResponse | null }) {
  const database = status?.database;
  const range = status?.data_range;
  const size = database?.size_bytes ? `${(database.size_bytes / 1048576).toFixed(1)} MB` : '-';
  return (
    <Card title="数据与导出">
      <dl className="kv-list">
        <dt>数据库</dt>
        <dd>{size}</dd>
        <dt>数据范围</dt>
        <dd>{range?.min_date ? `${range.min_date} 至 ${range.max_date}` : '暂无数据'}</dd>
        <dt>schema</dt>
        <dd>{String(database?.schema_version || '-')}</dd>
        <dt>数据库文件</dt>
        <dd className="mono">{database?.path || '-'}</dd>
      </dl>
      <ActionField
        label="导出使用记录 CSV"
        icon="download"
        href={exportHref('usage', 'csv')}
        download
      />
      <ActionField
        label="导出键盘统计 CSV"
        icon="download"
        href={exportHref('keyboard', 'csv')}
        download
      />
      <ActionField label="导出全部 JSON" icon="download" href={exportHref('all', 'json')} download />
      <ActionField label="打开数据目录" icon="folder" onClick={() => void revealDirectory('data')} />
      <ActionField label="打开日志目录" icon="logs" onClick={() => void revealDirectory('logs')} />
      <ActionField
        label="从旧版导入数据"
        icon="import"
        note="从 KeyTrace 或 TimeLens 的旧数据库导入历史记录"
        onClick={() => openImportWizard()}
      />
      <div className="field__note">备份、重算聚合与删除数据排在后续版本。</div>
    </Card>
  );
}

/** 能力说明：所有 degraded 都在这里列全，横幅只上 error 一级。 */
export function CapabilityCard() {
  const capabilities = useSlice('capabilities');
  const degraded = useSlice('degraded');
  const read = capabilities as unknown as Record<string, unknown> | null;
  return (
    <Card title="运行环境能力">
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
    </Card>
  );
}

/** 关于。详细的隐私说明在 `/about`——标题旁那个图标是去那一页的入口（18 文档 批 7）。 */
export function AboutCard({
  status,
  configPath,
}: {
  status: StatusResponse | null;
  configPath: string;
}) {
  const platform = status?.platform;
  return (
    <Card
      title="关于"
      titleAside={
        <a className="icon-button" href={pageUrl('/about')} aria-label="关于与隐私说明">
          <Icon name="external" />
        </a>
      }
    >
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
        <dt>配置文件</dt>
        <dd className="mono">{configPath || '-'}</dd>
      </dl>
      <div className="field__note">
        所有数据只保存在本机，不上传任何服务器。本程序不记录按键内容，只记录按了哪个键、多少次。
      </div>
    </Card>
  );
}
