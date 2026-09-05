import { W as require_jsx_runtime } from "./degraded-qMnijys5.js";
//#region frontend/src/components/Card.tsx
var import_jsx_runtime = require_jsx_runtime();
function Card({ title, controls, subtitle, footer, children, refreshing, id, className }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: className ? `card ${className}` : "card",
		id,
		"data-refreshing": refreshing ? "true" : void 0,
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "card__head",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
						className: "card__title",
						children: title
					}), subtitle ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "card__subtitle",
						children: subtitle
					}) : null] }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "spacer" }),
					controls
				]
			}),
			children,
			footer
		]
	});
}
function Section({ title, right, sub, lead = false, children }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: "section",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: lead ? "section-heading section-heading--lead" : "section-heading",
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
				className: "section-title",
				children: title
			}), sub ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "section-sub",
				children: sub
			}) : null] }), right]
		}), children]
	});
}
//#endregion
export { Section as n, Card as t };
