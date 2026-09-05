import { F as get, K as require_react, W as require_jsx_runtime, w as getState } from "./degraded-mkfLsXii.js";
import { a as mountChrome, d as require_client, i as loadStatus, n as PageLink, o as mountPoint, r as adopt, s as pageUrl, t as MissingToken } from "./shell-B5wD9e0n.js";
import { t as AboutContent } from "./AboutContent-BCYgB_rG.js";
import { t as Card } from "./Card-CxjL8c3d.js";
//#region frontend/src/pages/AboutPage.tsx
var import_react = require_react();
var import_client = require_client();
var import_jsx_runtime = require_jsx_runtime();
function AboutPage({ payload, status }) {
	const platform = status?.platform;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "section-heading section-heading--lead",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
				className: "section-title",
				id: "page-title",
				children: "关于与隐私说明"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "section-sub",
				children: "本机运行，无账号、不联网、无遥测。"
			})] })
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "card about-card",
			children: payload ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AboutContent, { payload }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "muted",
				children: "读不到隐私说明（采集进程可能已退出，或访问令牌已失效）。请从托盘菜单重新打开。"
			})
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Card, {
			title: "版本与环境",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dl", {
					className: "kv-list",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "版本" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: status?.version || "-" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "运行环境" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: `${platform?.id || "-"} ${platform?.os_version || ""}` }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "支持级别" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: platform?.tier ? `${platform.tier} 级` : "-" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "端口" }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: String(status?.port || "-") })
					]
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "actions",
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
						className: "button",
						href: pageUrl("/settings"),
						children: "设置 →"
					}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
						className: "button",
						href: pageUrl("/"),
						children: "仪表盘 →"
					})]
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "field__note",
					children: "第三方组件与许可写在程序目录的 THIRD_PARTY_NOTICES.md 里。"
				})
			]
		})
	] });
}
//#endregion
//#region frontend/src/about.tsx
async function main() {
	const token = adopt();
	mountChrome({ nav: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageLink, {
		href: "/",
		icon: "overview",
		label: "返回仪表盘"
	}) });
	const root = (0, import_client.createRoot)(mountPoint("about-root"));
	if (!token) {
		root.render(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(MissingToken, {}));
		return;
	}
	const [payload] = await Promise.all([get("/onboarding").catch(() => null), loadStatus()]);
	root.render(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_react.StrictMode, { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AboutPage, {
		payload,
		status: getState().status
	}) }));
}
main();
//#endregion
