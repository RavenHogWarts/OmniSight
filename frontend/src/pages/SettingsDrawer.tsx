// 设置抽屉（18 文档 §2.1）。仪表盘工具条的 ⚙ 在 `ui.settings_surface = drawer` 那一档
// 走这里；另一档是 `/settings` 那一页。**正文是同一个组件**（SettingsPage），这个文件只
// 负责"把它装进抽屉"这三件事：等数据、开覆盖层、给一条去独立页面的出口。
//
// **按需加载。** main.tsx 用 `import()` 拉它（那是仪表盘唯一一处提到设置代码的地方），
// 因此首屏不为一个可能不点的面板付表单与导出那几个模块的钱——与四个视图同一个
// 手法（main.tsx:VIEW_MODULES）。
import { Drawer, openOverlay } from '../components/Drawer.tsx';
import { Icon } from '../components/Icon.tsx';
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
      headExtra={
        // 抽屉里没有的东西只有一样：地址。给一条出口，于是"我想把这一页发给别人 / 开着慢慢
        // 看"不必先去改 `ui.settings_surface`。
        //
        // **在表头而不是底部**（18 文档 批 7）：抽屉底部是滚动之外的一条常驻带，为一个链接
        // 占掉整整一行；而这个动作与"关闭"是同一类——都是对这个抽屉本身的操作，因此并排。
        <a
          className="icon-button"
          href={pageUrl('/settings')}
          aria-label="在独立页面中打开设置"
        >
          <Icon name="external" />
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
