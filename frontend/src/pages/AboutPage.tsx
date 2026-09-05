// 关于与隐私说明页（18 文档 批 4）。原先是一个模态（托盘那一项与 `#about` 都打开它），
// 现在是一张有地址的页面：`/about`。
//
// **首次运行仍然是模态**（components/Onboarding.tsx）。08 文档 §6.1 要求那一步必须点
// 「开始使用」才算确认，做成页面等于允许用户关掉标签页跳过——两者共用同一份正文
// （components/AboutContent.tsx），因此"说明"只有一处真源。
import { AboutContent } from '../components/AboutContent.tsx';
import { Card } from '../components/Card.tsx';
import type { OnboardingResponse, StatusResponse } from '../types/api.d.ts';
import { pageUrl } from './shell.tsx';

export function AboutPage({
  payload,
  status,
}: {
  payload: OnboardingResponse | null;
  status: StatusResponse | null;
}) {
  const platform = status?.platform;
  return (
    <>
      <div className="section-heading section-heading--lead">
        <div>
          <h1 className="section-title" id="page-title">
            关于与隐私说明
          </h1>
          <p className="section-sub">本机运行，无账号、不联网、无遥测。</p>
        </div>
      </div>
      <div className="card about-card">
        {payload ? (
          <AboutContent payload={payload} />
        ) : (
          <p className="muted">
            读不到隐私说明（采集进程可能已退出，或访问令牌已失效）。请从托盘菜单重新打开。
          </p>
        )}
      </div>
      <Card title="版本与环境">
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
        <div className="actions">
          <a className="button" href={pageUrl('/settings')}>
            设置 →
          </a>
          <a className="button" href={pageUrl('/')}>
            仪表盘 →
          </a>
        </div>
        <div className="field__note">
          第三方组件与许可写在程序目录的 THIRD_PARTY_NOTICES.md 里。
        </div>
      </Card>
    </>
  );
}
