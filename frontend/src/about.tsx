// 关于与隐私说明页的入口（18 文档 批 1、批 4）。
//
// 它是三个入口里最小的一个：一次 `GET /onboarding`（内容全部由后端算，08 文档 §6.1）加一次
// `GET /status`（版本与运行环境），然后交给 pages/AboutPage.tsx 排版。
import '../styles/app.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { AboutPage } from './pages/AboutPage.tsx';
import { MissingToken, PageLink, adopt, loadStatus, mountChrome, mountPoint } from './pages/shell.tsx';
import { get as apiGet } from './core/api.ts';
import { getState } from './core/store.ts';
import type { OnboardingResponse } from './types/api.d.ts';

async function main(): Promise<void> {
  const token = adopt();
  mountChrome({ nav: <PageLink href="/" icon="overview" label="返回仪表盘" /> });
  const root = createRoot(mountPoint('about-root'));

  if (!token) {
    root.render(<MissingToken />);
    return;
  }

  const [payload] = await Promise.all([
    // 读不到就画一句说明，不把整页变成错误：这一页存在的意义是"随时能确认这程序记录什么"，
    // 而一片空白连这一点都做不到。
    apiGet('/onboarding').catch(() => null) as Promise<OnboardingResponse | null>,
    loadStatus(),
  ]);

  root.render(
    <StrictMode>
      <AboutPage payload={payload} status={getState().status} />
    </StrictMode>,
  );
}

void main();
