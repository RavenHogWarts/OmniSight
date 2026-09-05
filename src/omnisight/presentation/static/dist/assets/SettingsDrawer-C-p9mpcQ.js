import { W as require_jsx_runtime, k as fail, w as getState } from "./degraded-qMnijys5.js";
import { c as Drawer, s as pageUrl, u as openOverlay } from "./shell-8ge_e5M8.js";
import { n as loadSettings, t as SettingsPage } from "./SettingsPage-C_ET1OP0.js";
//#region frontend/src/pages/SettingsDrawer.tsx
var import_jsx_runtime = require_jsx_runtime();
async function openSettingsDrawer() {
	if (getState().settings) loadSettings().catch(() => fail("重读设置失败"));
	else try {
		await loadSettings();
	} catch {
		fail("读不到设置，请刷新页面重试");
		return;
	}
	openOverlay(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Drawer, {
		title: "设置",
		wide: true,
		footer: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
			className: "button",
			href: pageUrl("/settings"),
			children: "在独立页面中打开 →"
		}),
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "page",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SettingsPage, { surface: "drawer" })
		})
	}));
}
//#endregion
export { openSettingsDrawer };
