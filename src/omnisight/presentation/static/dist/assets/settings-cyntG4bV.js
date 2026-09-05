import { K as require_react, W as require_jsx_runtime, k as fail } from "./degraded-mkfLsXii.js";
import { a as mountChrome, d as require_client, i as loadStatus, n as PageLink, o as mountPoint, r as adopt, t as MissingToken } from "./shell-B5wD9e0n.js";
import { n as loadSettings, t as SettingsPage } from "./SettingsPage-DzlEzCsT.js";
//#region frontend/src/settings.tsx
var import_react = require_react();
var import_client = require_client();
var import_jsx_runtime = require_jsx_runtime();
async function main() {
	const token = adopt();
	mountChrome({ nav: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageLink, {
		href: "/",
		icon: "overview",
		label: "返回仪表盘"
	}) });
	const root = (0, import_client.createRoot)(mountPoint("settings-root"));
	if (!token) {
		root.render(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(MissingToken, {}));
		return;
	}
	await Promise.all([loadStatus(), loadSettings().catch(() => fail("读不到设置，请从托盘菜单重新打开"))]);
	root.render(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_react.StrictMode, { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SettingsPage, {}) }));
}
main();
//#endregion
