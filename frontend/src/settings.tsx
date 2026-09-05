// 设置页的入口（18 文档 批 1、批 2）。
//
// 三个入口（main.tsx / settings.tsx / about.tsx）共用 pages/shell.tsx 那一套开场：接令牌、
// 恢复主题、挂工具条与三个浮层。这个文件因此只剩下"这一页要什么数据、画什么"。
//
// **这一页始终存在**，与 `ui.settings_surface` 那一档无关（18 文档 §2.1）：托盘的「打开
// 设置」去的是它，文档与 issue 里的 `/settings#privacy` 也是。配置只决定仪表盘上那个 ⚙
// 点下去是开抽屉还是走到这里。正文两档共用（pages/SettingsPage.tsx）。
//
// **样式表也进构建图**（15 文档 §11.4）：`cssCodeSplit: false` 让三个入口共用产物里的同一份
// CSS，而每个入口都显式 import 它——"这一页需要那份样式"是一条应当写出来的事实。
import '../styles/app.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { fail } from './components/toast.tsx';
import { SettingsPage, loadSettings } from './pages/SettingsPage.tsx';
import { MissingToken, PageLink, adopt, loadStatus, mountChrome, mountPoint } from './pages/shell.tsx';

async function main(): Promise<void> {
  const token = adopt();
  // 工具条右段那个槽在这一页是「返回仪表盘」，同一标签页跳转——来回几次不该攒出一堆标签。
  mountChrome({ nav: <PageLink href="/" icon="overview" label="返回仪表盘" /> });
  const root = createRoot(mountPoint('settings-root'));

  if (!token) {
    root.render(<MissingToken />);
    return;
  }

  // **先取回设置再画**：半张空表单比等半秒更糟（原设置抽屉的口径，06 文档 §9）。
  // 取不到也照画：状态那一路会给出降级横幅，各张卡显示 `-` 比一片空白说得清。
  await Promise.all([
    loadStatus(),
    loadSettings().catch(() => fail('读不到设置，请从托盘菜单重新打开')),
  ]);

  root.render(
    <StrictMode>
      <SettingsPage />
    </StrictMode>,
  );
}

void main();
