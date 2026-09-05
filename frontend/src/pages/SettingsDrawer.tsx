// 设置抽屉（18 文档 §2.1）。仪表盘工具条的 ⚙ 在 `ui.settings_surface = drawer` 那一档
// 走这里；另一档是 `/settings` 那一页。**正文是同一个组件**（SettingsPage），这个文件只
// 负责"把它装进抽屉"这三件事：等数据、开覆盖层、给一条去独立页面的出口。
//
// **按需加载。** main.tsx 用 `import()` 拉它（那是仪表盘唯一一处提到设置代码的地方），
// 因此首屏不为一个可能不点的面板付表单、导出、进程动作那几个模块的钱——与四个视图同一个
// 手法（main.tsx:VIEW_MODULES）。
import { Drawer, openOverlay } from '../components/Drawer.tsx';
import { fail } from '../components/toast.tsx';
import { getState } from '../core/store.ts';
import { SettingsPage, loadSettings } from './SettingsPage.tsx';
import { pageUrl } from './shell.tsx';

export async function openSettingsDrawer(): Promise<void> {
  // 仪表盘首屏已经取过一次 `/settings`（main.tsx:loadPrefs 读的就是这一份），因此常态下
  // 抽屉是立刻开的，只在背后顺手刷新一遍。**取不到那一份时才等**：半张空表单比等半秒
  // 更糟（原设置抽屉的口径，06 文档 §9）。
  if (getState().settings) {
    void loadSettings().catch(() => fail('重读设置失败'));
  } else {
    try {
      await loadSettings();
    } catch {
      fail('读不到设置，请刷新页面重试');
      return;
    }
  }
  openOverlay(
    <Drawer
      title="设置"
      wide
      footer={
        // 抽屉里没有的东西只有一样：地址。给一条出口，于是"我想把这一页发给别人/开着
        // 慢慢看"不必先去改 `ui.settings_surface`。
        <a className="button" href={pageUrl('/settings')}>
          在独立页面中打开 →
        </a>
      }
    >
      {/* `.page` 在这里只取它的"一列、块间 16px"（layout.css）——760px 的上限在 520px 的
          抽屉里本来就不起作用。少了它，几张卡会贴在一起。 */}
      <div className="page">
        <SettingsPage surface="drawer" />
      </div>
    </Drawer>,
  );
}
