const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/overview-DF1rEaV8.js","assets/degraded-mkfLsXii.js","assets/Card-CxjL8c3d.js","assets/states-WQyaTbLh.js","assets/apps-YsxOuX3Q.js","assets/controls-CgVt8_vH.js","assets/shell-B5wD9e0n.js","assets/Quad-BFRR8NaA.js","assets/keyboard-QI8Zu-yU.js","assets/axis-B3WMBRfR.js","assets/insights-D1CZpRMb.js","assets/SettingsDrawer-DFjOpm1k.js","assets/SettingsPage-DzlEzCsT.js"])))=>i.map(i=>d[i]);
import { B as tokenParam, C as useSlice, D as subscribe, E as setState, F as get, H as on, I as invalidate, K as require_react, T as setEntry, U as Icon, V as emit, W as require_jsx_runtime, c as set, f as hide, h as formatCount, j as ApiError, k as fail, l as setHeat, m as formatClock, p as show, w as getState, y as formatMs, z as post } from "./degraded-mkfLsXii.js";
import { a as mountChrome, d as require_client, i as loadStatus, l as closeOverlay, n as PageLink, o as mountPoint, r as adopt, t as MissingToken, u as openOverlay } from "./shell-B5wD9e0n.js";
import { i as Segmented, o as ImportBanner, s as openImportWizard } from "./controls-CgVt8_vH.js";
import { t as AboutContent } from "./AboutContent-BCYgB_rG.js";
//#region frontend/src/components/Onboarding.tsx
var import_client = require_client();
var import_react = require_react();
var import_jsx_runtime = require_jsx_runtime();
/** 首屏调用：只在后端说 `required` 时弹出。取数失败一律安静跳过，不挡住仪表盘。 */
async function maybeShowOnboarding() {
	let payload = null;
	try {
		payload = await get("/onboarding");
	} catch {
		return;
	}
	if (!payload?.required) return;
	openOverlay(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Onboarding, { payload }));
}
function Onboarding({ payload }) {
	const dialog = (0, import_react.useRef)(null);
	const opener = (0, import_react.useRef)(typeof document === "undefined" ? null : document.activeElement);
	const close = () => {
		closeOverlay();
		const previous = opener.current;
		if (previous && typeof previous.focus === "function") previous.focus();
	};
	const closeRef = (0, import_react.useRef)(close);
	closeRef.current = close;
	(0, import_react.useEffect)(() => {
		const root = dialog.current;
		root?.querySelector("button")?.focus() ?? root?.focus();
		const onKeydown = (event) => {
			if (event.key !== "Tab") return;
			const host = dialog.current;
			if (!host) return;
			const items = [...host.querySelectorAll("button, a[href]")].filter((node) => node.offsetParent !== null);
			if (!items.length) return;
			const first = items[0];
			const last = items[items.length - 1];
			if (event.shiftKey && document.activeElement === first) {
				event.preventDefault();
				last.focus();
			} else if (!event.shiftKey && document.activeElement === last) {
				event.preventDefault();
				first.focus();
			} else if (!host.contains(document.activeElement)) {
				event.preventDefault();
				first.focus();
			}
		};
		document.addEventListener("keydown", onKeydown, true);
		return () => document.removeEventListener("keydown", onKeydown, true);
	}, []);
	const accept = async () => {
		try {
			await post("/onboarding/ack", {});
		} catch {
			fail("无法记录你的确认，下次启动可能再次显示这份说明");
		}
		close();
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "scrim" }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "onboarding",
		ref: dialog,
		role: "dialog",
		"aria-modal": "true",
		"aria-labelledby": "onboarding-title",
		tabIndex: -1,
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "onboarding__head",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
					id: "onboarding-title",
					children: "OmniSight 记录什么"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "muted",
					children: "本机运行，无账号、不联网、无遥测。"
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(AboutContent, { payload }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "onboarding__foot",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
					className: "button button--primary",
					type: "button",
					onClick: () => void accept(),
					children: "开始使用"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
					className: "button",
					type: "button",
					title: "这份说明会在下次启动时再次出现",
					onClick: close,
					children: "稍后再说"
				})]
			})
		]
	})] });
}
//#endregion
//#region frontend/src/domain/metrics.ts
/** 与 services/keyboard.py 的 METRICS 一一对应。顺序即 UI 顺序。 */
var METRICS = [
	{
		id: "press_count",
		name: "次数",
		short: "次",
		format: formatCount
	},
	{
		id: "duration_total_ms",
		name: "总时长",
		short: "总",
		format: formatMs
	},
	{
		id: "duration_avg_ms",
		name: "均时长",
		short: "均",
		format: formatMs
	},
	{
		id: "duration_max_ms",
		name: "最长",
		short: "最长",
		format: formatMs
	}
];
var BY_ID = new Map(METRICS.map((metric) => [metric.id, metric]));
function metricOf(id) {
	return BY_ID.get(id) || METRICS[0];
}
function formatMetric(id, value) {
	return metricOf(id).format(value);
}
/** 周期范围。API 的 range 取值（services/period.py 的 RANGES）。 */
var RANGES = [
	{
		id: "day",
		name: "日"
	},
	{
		id: "week",
		name: "周"
	},
	{
		id: "month",
		name: "月"
	},
	{
		id: "year",
		name: "年"
	},
	{
		id: "total",
		name: "全部"
	},
	{
		id: "custom",
		name: "自定义"
	}
];
/** config 的 ui.default_view 用 daily/weekly/... 命名，API 的 range 用 day/week/...。 */
var VIEW_TO_RANGE = {
	daily: "day",
	weekly: "week",
	monthly: "month",
	yearly: "year",
	total: "total"
};
function rangeFromDefaultView(view) {
	return VIEW_TO_RANGE[view] || "day";
}
/** 键盘时间分布的四个视图（services/keyboard.py 的 TIMELINE_VIEWS）。 */
var TIMELINE_VIEWS = [
	{
		id: "hours",
		name: "时"
	},
	{
		id: "days",
		name: "日"
	},
	{
		id: "months",
		name: "月"
	},
	{
		id: "years",
		name: "年"
	}
];
/**
* 热力比例。**p95 归一而不是最大值归一**（06 文档 §7 改进 1）：空格键通常是第二名的
* 3 倍，用最大值会把其余所有键压成一片浅色。超出 p95 的键饱和到 1 并单独标记。
*/
function heatRatio(value, scale) {
	const top = Number(scale?.p95) || Number(scale?.max) || 0;
	if (top <= 0) return 0;
	const ratio = (Number(value) || 0) / top;
	return ratio > 1 ? 1 : ratio;
}
function isSaturated(value, scale) {
	const top = Number(scale?.p95) || 0;
	const max = Number(scale?.max) || 0;
	return top > 0 && max > top && (Number(value) || 0) > top;
}
/**
* 离散档位。**这就是键面与格子实际渲染的那一档**（14 文档 §2.4）——不是"另外算一个
* 供图例用的近似"。现状是 `color-mix` 在 heat-0 与 heat-5 之间连续插值，图例摆 6 个
* 离散色块、键面画连续量，读者无法把一个键的颜色对回一个值区间。
*
* 0 是零态（没按过），不属于色阶的任何一档：它是承载面本身。
*/
function heatLevel(ratio) {
	if (ratio <= 0) return 0;
	if (ratio < .2) return 1;
	if (ratio < .4) return 2;
	if (ratio < .6) return 3;
	if (ratio < .8) return 4;
	return 5;
}
/** 每一档对应的比例区间上界，供图例标出"这一档到多少"。 */
var HEAT_BOUNDS = [
	0,
	.2,
	.4,
	.6,
	.8,
	1
];
//#endregion
//#region frontend/src/domain/period.ts
function todayISO(now = /* @__PURE__ */ new Date()) {
	return toISO(now);
}
function toISO(date) {
	return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
function fromISO(text) {
	const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(text || ""));
	if (!match) return null;
	const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
	return Number.isNaN(date.getTime()) ? null : date;
}
function addDays(day, count) {
	const date = fromISO(day);
	if (!date) return day;
	date.setDate(date.getDate() + count);
	return toISO(date);
}
function addMonths(day, count) {
	const date = fromISO(day);
	if (!date) return day;
	const target = new Date(date.getFullYear(), date.getMonth() + count, 1);
	const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
	target.setDate(Math.min(date.getDate(), lastDay));
	return toISO(target);
}
function addYears(day, count) {
	const date = fromISO(day);
	if (!date) return day;
	const target = new Date(date.getFullYear() + count, date.getMonth(), 1);
	const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
	target.setDate(Math.min(date.getDate(), lastDay));
	return toISO(target);
}
/**
* 周期翻页。`anchor` 用响应里的 `period.anchor`（后端已把它规整过），
* 没有响应时退回本地今天。
*/
function shift(range, anchor, direction) {
	const base = anchor || todayISO();
	switch (range) {
		case "day": return addDays(base, direction);
		case "week": return addDays(base, direction * 7);
		case "month": return addMonths(base, direction);
		case "year": return addYears(base, direction);
		default: return base;
	}
}
/** 能不能往后翻。后端会把未来截断，但按钮该先置灰，而不是点了没反应。 */
function canGoForward(range, anchor, today = todayISO()) {
	if (range === "total" || range === "custom") return false;
	return shift(range, anchor, 1) <= today;
}
function isPageable(range) {
	return range !== "total" && range !== "custom";
}
/**
* `coverage.gaps` -> Set of days，图表按桶查它决定画不画斜纹。
*
* 每条 gap 形如 `{from, to, missing, reason, message}`（services/coverage.py）。
* **必须按 `missing` 过滤**：时长图只关心 `foreground` 缺失，键盘图只关心 `keyboard`
* 缺失。而 `key_position` 根本不是"没有数据"——它是"左右修饰键合并统计了"，
* 口径变化，画成斜纹会告诉用户那几天没打字，那是错的。
*/
function gapSet(coverage, kinds = ["foreground"]) {
	const wanted = new Set(kinds);
	const days = /* @__PURE__ */ new Set();
	for (const gap of coverage?.gaps || []) {
		if (!wanted.has(gap?.missing)) continue;
		const start = gap.from;
		const end = gap.to || start;
		if (!start) continue;
		let cursor = start;
		for (let index = 0; index < 4e3 && cursor <= end; index += 1) {
			days.add(cursor);
			cursor = addDays(cursor, 1);
		}
	}
	return days;
}
/** 口径变化（不是缺数据）的说明，供图例注记用。 */
function caliberNotes(coverage) {
	return (coverage?.gaps || []).filter((gap) => gap?.missing === "key_position").map((gap) => ({
		from: gap.from,
		to: gap.to,
		message: gap.message,
		reason: gap.reason
	}));
}
/** 桶 id -> 是否命中缺口。日桶精确匹配，月/年桶只要包含一天缺口就算。 */
function bucketCoversGap(bucket, gaps) {
	if (!gaps || gaps.size === 0) return false;
	const text = String(bucket || "");
	if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return gaps.has(text);
	if (/^\d{4}-\d{2}$/.test(text) || /^\d{4}$/.test(text)) {
		for (const day of gaps) if (day.startsWith(text)) return true;
	}
	return false;
}
/**
* 周期状态 -> 查询参数（05 文档 §1.2）。custom 用 start/end，其余用 date。
* 视图取数一律经它，于是"周期怎么变成参数"只有一份实现。
*/
function periodParams(period) {
	if (period.range === "custom") return {
		range: "custom",
		start: period.start,
		end: period.end
	};
	return {
		range: period.range,
		date: period.date
	};
}
//#endregion
//#region frontend/src/components/PeriodNav.tsx
/** 指标带的 portal 目标（模板里的 `<div class="metricbar" id="metricbar">`）。 */
var METRIC_SLOT_ID = "metricbar";
/** 范围预设里不含 custom：它由日期控件右端那个小按钮进入，不占一个常驻档位。 */
var PRESETS = RANGES.filter((range) => range.id !== "custom");
/** 锚点优先用后端规整过的值，否则退回本地选择。 */
function anchorOf() {
	const { period, periodMeta } = getState();
	return periodMeta?.anchor || period.date || todayISO();
}
function step(direction) {
	const { period } = getState();
	if (!isPageable(period.range)) return;
	if (direction > 0 && !canGoForward(period.range, anchorOf(), todayISO())) return;
	setState("period", {
		...period,
		date: shift(period.range, anchorOf(), direction)
	});
}
function pickRange(id) {
	const { periodMeta } = getState();
	if (id === "custom") {
		const end = periodMeta?.truncated_end || todayISO();
		const start = periodMeta?.start || end;
		setState("period", {
			range: "custom",
			date: null,
			start,
			end
		});
		return;
	}
	setState("period", {
		range: id,
		date: anchorOf(),
		start: null,
		end: null
	});
}
function goToday() {
	setState("period", {
		...getState().period,
		date: todayISO()
	});
}
/** 日期条。四格网格：翻页 / 日期 / 翻页 / 今天，与前身逐格对应。 */
function DateBar() {
	const period = useSlice("period");
	const periodMeta = useSlice("periodMeta");
	const today = todayISO();
	const pageable = isPageable(period.range);
	const isCustom = period.range === "custom";
	const frozen = period.range === "total";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "round-btn",
			type: "button",
			"aria-label": "上一个周期",
			title: "上一个周期",
			disabled: !pageable,
			onClick: () => step(-1),
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "left" })
		}),
		isCustom ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CustomRange, {}) : /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
			className: frozen ? "date-control date-control--disabled" : "date-control",
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "date-control__label",
					children: "查看日期"
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
					type: "date",
					max: today,
					disabled: frozen,
					"aria-label": "查看日期",
					value: anchorValue(period.date, periodMeta?.anchor),
					onChange: (event) => {
						if (!event.target.value) return;
						setState("period", {
							...period,
							date: event.target.value,
							start: null,
							end: null
						});
					}
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RangeToggle, { active: false })
			]
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "round-btn",
			type: "button",
			"aria-label": "下一个周期",
			title: "下一个周期",
			disabled: !pageable || !canGoForward(period.range, anchorOf(), today),
			onClick: () => step(1),
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "right" })
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "button",
			type: "button",
			disabled: frozen || Boolean(periodMeta?.is_current),
			onClick: goToday,
			children: "今天"
		})
	] });
}
/** 日期框要一个 `YYYY-MM-DD`：后端规整过的锚点优先，否则用本地选择，最后退今天。 */
function anchorValue(date, anchor) {
	return date || anchor || todayISO();
}
/**
* 自定义区间的入口/出口（17 文档 §6.1）。
*
* 它是日期控件**里面**的一个小按钮，而不是控件带上的第五格：420px 的四格几何来自
* 前身，为一个少数场景常驻两个日期框会把它顶开。前身没有自定义区间这个功能，所以
* 这一处没有可照搬的形状——收进控件内部是"不破坏几何"与"不删功能"的交点。
*
* **用文字而不是图标**：`<input type="date">` 自带一个日历图标，再放一个日历图标在它
* 右边就是两个日历并排，读者无从知道哪个开哪个。两个字反而没有歧义。
*/
function RangeToggle({ active }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
		className: "date-control__toggle",
		type: "button",
		"aria-pressed": active,
		"aria-label": active ? "退出自定义区间" : "选择自定义区间",
		title: active ? "退出自定义区间，回到按天翻页" : "改成自定义起止日期",
		onClick: (event) => {
			event.preventDefault();
			event.stopPropagation();
			if (active) pickRange("day");
			else pickRange("custom");
		},
		children: "区间"
	});
}
function CustomRange() {
	const period = useSlice("period");
	const today = todayISO();
	const apply = (start, end) => {
		if (!start || !end) return;
		setState("period", {
			range: "custom",
			date: null,
			start,
			end
		});
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "date-control date-control--range",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
				type: "date",
				max: today,
				"aria-label": "起始日期",
				value: period.start || "",
				onChange: (event) => apply(event.target.value, period.end || "")
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "date-control__dash",
				"aria-hidden": "true",
				children: "–"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
				type: "date",
				max: today,
				"aria-label": "结束日期",
				value: period.end || "",
				onChange: (event) => apply(period.start || "", event.target.value)
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RangeToggle, { active: true })
		]
	});
}
/**
* 范围带 + 它下面那行口径注记。
*
* 注记存在的理由：日期控件里只有**一个**日期，而选「每周」时这一屏覆盖的是哪七天
* 得有个落脚处——后端算好的 `periodMeta.label` 就放在这里（前端不自己算星期）。
*/
function RangeBar() {
	const period = useSlice("period");
	const periodMeta = useSlice("periodMeta");
	const notes = caliberNotes(useSlice("coverage"));
	const label = period.range === "day" ? "" : periodMeta?.label || "";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Segmented, {
		items: PRESETS,
		active: period.range,
		onPick: pickRange,
		variant: "lg",
		label: "时间范围"
	}), label || notes.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
		className: "periodnote",
		"aria-live": "polite",
		children: [
			label,
			label && notes.length ? " · " : "",
			notes.length ? `${notes[0].from} 至 ${notes[0].to} 口径不同：${notes[0].message}` : ""
		]
	}) : null] });
}
/**
* 数据新鲜度（17 文档 §8 的 D9）。**常驻**：前身每一段标题右侧都有这行小字，而我们
* 原先只在实时通道降级时才显示它（16 文档 §A6 的结论），于是屏幕上没有任何地方说得出
* 这屏数字算于何时。SSE 正常时它每次重取都会更新，不是噪声。
*/
function Updated() {
	const data = useSlice("data");
	const live = useSlice("live");
	const [fetchedAt, setFetchedAt] = (0, import_react.useState)(() => /* @__PURE__ */ new Date());
	const first = (0, import_react.useRef)(true);
	(0, import_react.useEffect)(() => {
		if (first.current) {
			first.current = false;
			return;
		}
		setFetchedAt(/* @__PURE__ */ new Date());
	}, [data]);
	if (!fetchedAt) return null;
	const suffix = live.mode === "stream" ? "" : "（轮询）";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("p", {
		className: "updated",
		children: [
			"更新于 ",
			formatClock(fetchedAt.toISOString()),
			suffix
		]
	});
}
//#endregion
//#region frontend/src/core/loader.ts
var controller = new AbortController();
/** 周期/范围变了：上一批请求的结果已经没人要了。 */
function abortPending() {
	controller.abort();
	controller = new AbortController();
}
/**
* 取一段数据并写进 store。
* `key` 是组件订阅的名字（`overview`、`heatmap`…），与路径无关，便于同一路径不同参数并存。
*/
async function fetchInto(key, path, params = {}, options = {}) {
	const { maxAge = 0 } = options;
	setEntry("loading", key, true);
	const signal = controller.signal;
	try {
		const payload = await get(path, params, {
			signal,
			maxAge
		});
		if (signal.aborted) return null;
		setEntry("errors", key, null);
		setEntry("data", key, payload);
		if (payload && "period" in payload && payload.period) setState("periodMeta", payload.period);
		if (payload && "coverage" in payload && payload.coverage) setState("coverage", payload.coverage);
		return payload;
	} catch (error) {
		if (error?.name === "AbortError" || signal.aborted) return null;
		setEntry("errors", key, describe(error));
		setEntry("data", key, null);
		return null;
	} finally {
		if (!signal.aborted) setEntry("loading", key, false);
	}
}
function describe(error) {
	if (error instanceof ApiError) return {
		message: error.message,
		code: error.code,
		status: error.status,
		field: error.field
	};
	return {
		message: "无法连接到本机服务，采集进程可能已退出",
		code: "network_error",
		status: 0
	};
}
//#endregion
//#region frontend/src/core/router.ts
var ROUTES = [
	"overview",
	"apps",
	"keyboard",
	"insights"
];
var DEFAULT_ROUTE = "overview";
var applying = false;
function isRoute(value) {
	return ROUTES.includes(value);
}
/** `#/keyboard?range=week&date=2026-08-31&metric=duration_avg_ms` */
function parseHash(hash = window.location.hash) {
	const [path, query = ""] = String(hash || "").replace(/^#\/?/, "").split("?");
	return {
		route: isRoute(path) ? path : DEFAULT_ROUTE,
		params: new URLSearchParams(query)
	};
}
function currentQuery() {
	const { period, metric, scopeAppId, selectedAppId } = getState();
	const params = new URLSearchParams();
	params.set("range", period.range);
	if (period.range === "custom") {
		if (period.start) params.set("start", period.start);
		if (period.end) params.set("end", period.end);
	} else if (period.date) params.set("date", period.date);
	if (metric !== "press_count") params.set("metric", metric);
	if (scopeAppId) params.set("scope", String(scopeAppId));
	if (selectedAppId) params.set("app", String(selectedAppId));
	return params;
}
function hashFor(route) {
	const query = currentQuery().toString();
	return `#/${route}${query ? `?${query}` : ""}`;
}
/** URL -> store。用户手改地址、前进后退都走这里。 */
function applyFromHash() {
	const { route, params } = parseHash();
	applying = true;
	try {
		setState("period", {
			range: params.get("range") || "day",
			date: params.get("date") || null,
			start: params.get("start") || null,
			end: params.get("end") || null
		});
		setState("metric", params.get("metric") || "press_count");
		setState("scopeAppId", toId(params.get("scope")));
		setState("selectedAppId", toId(params.get("app")));
		setState("route", route);
	} finally {
		applying = false;
	}
}
function toId(value) {
	const id = Number.parseInt(value ?? "", 10);
	return Number.isInteger(id) && id > 0 ? id : null;
}
function go(route) {
	if (!isRoute(route) || getState().route === route) return;
	history.pushState(null, "", hashFor(route));
	setState("route", route);
}
/** store -> URL，静默。视图切换之外的一切状态变化都用它。 */
function syncHash() {
	if (applying) return;
	const next = hashFor(getState().route);
	if (next !== window.location.hash) history.replaceState(null, "", next);
}
function start() {
	window.addEventListener("hashchange", applyFromHash);
	window.addEventListener("popstate", applyFromHash);
	for (const slice of [
		"period",
		"metric",
		"scopeAppId",
		"selectedAppId"
	]) subscribe(slice, syncHash);
	subscribe("route", syncHash);
	applyFromHash();
}
//#endregion
//#region frontend/src/core/stream.ts
var POLL_INTERVAL_MS = 3e4;
var source = null;
var pollTimer = 0;
var disabled = false;
function connect() {
	if (source || disabled) return;
	const token = tokenParam();
	if (!token) return;
	source = new EventSource(`/api/v1/stream?token=${encodeURIComponent(token)}`);
	source.addEventListener("open", () => {
		stopPolling();
		setState("live", {
			connected: true,
			mode: "stream"
		});
	});
	source.addEventListener("status", (event) => {
		const payload = parse(event.data);
		if (!payload) return;
		setState("degraded", payload.degraded || []);
		emit("capture:status", payload.capture || null);
	});
	source.addEventListener("keypress", (event) => {
		const payload = parse(event.data);
		if (payload?.keys?.length) emit("key:press", payload.keys);
	});
	source.addEventListener("foreground", (event) => {
		const payload = parse(event.data);
		if (payload) setState("live", { currentApp: payload });
	});
	source.addEventListener("counters", (event) => {
		const payload = parse(event.data);
		if (payload) setState("live", { counters: payload });
	});
	source.addEventListener("invalidate", (event) => {
		const payload = parse(event.data);
		invalidate();
		emit("data:invalidated", payload || {});
	});
	source.addEventListener("settings", () => {
		invalidate();
		emit("settings:changed", {});
	});
	source.addEventListener("bye", () => {
		close();
		setState("live", {
			connected: false,
			mode: "offline"
		});
	});
	source.addEventListener("error", () => {
		setState("live", {
			connected: false,
			mode: "polling"
		});
		if (source && source.readyState === EventSource.CLOSED) {
			close();
			disabled = true;
			startPolling();
		}
	});
}
function parse(data) {
	try {
		return JSON.parse(data);
	} catch {
		return null;
	}
}
function close() {
	if (source) {
		source.close();
		source = null;
	}
}
/** 30 秒轮询兜底：只重新拉状态并让缓存失效，UI 只是少了实时动画。 */
function startPolling() {
	if (pollTimer) return;
	setState("live", {
		connected: false,
		mode: "polling"
	});
	pollTimer = window.setInterval(async () => {
		try {
			const status = await get("/status");
			setState("status", status);
			setState("degraded", status.degraded || []);
			invalidate();
			emit("data:invalidated", { data_version: status.data_version });
			emit("settings:changed", {});
		} catch {}
	}, POLL_INTERVAL_MS);
}
function stopPolling() {
	if (!pollTimer) return;
	window.clearInterval(pollTimer);
	pollTimer = 0;
}
//#endregion
//#region \0vite/preload-helper.js
var scriptRel = "modulepreload";
var assetsURL = function(dep) {
	return "/static/dist/" + dep;
};
var seen = {};
var __vitePreload = function preload(baseModule, deps, importerUrl) {
	let promise = Promise.resolve();
	if (deps && deps.length > 0) {
		const links = document.getElementsByTagName("link");
		const cspNonceMeta = document.querySelector("meta[property=csp-nonce]");
		const cspNonce = cspNonceMeta?.nonce || cspNonceMeta?.getAttribute("nonce");
		function allSettled(promises) {
			return Promise.all(promises.map((p) => Promise.resolve(p).then((value) => ({
				status: "fulfilled",
				value
			}), (reason) => ({
				status: "rejected",
				reason
			}))));
		}
		function importMetaResolve(specifier) {
			if (import.meta.resolve) return import.meta.resolve(specifier);
			return new URL(
				specifier,
				/** #__KEEP__ */
				import.meta.url
			).href;
		}
		promise = allSettled(deps.map((dep) => {
			dep = assetsURL(dep, importerUrl);
			dep = importMetaResolve(dep);
			if (dep in seen) return;
			seen[dep] = true;
			const isCss = dep.endsWith(".css");
			for (let i = links.length - 1; i >= 0; i--) {
				const link = links[i];
				if (link.href === dep && (!isCss || link.rel === "stylesheet")) return;
			}
			const link = document.createElement("link");
			link.rel = isCss ? "stylesheet" : scriptRel;
			if (!isCss) link.as = "script";
			link.crossOrigin = "";
			link.href = dep;
			if (cspNonce) link.setAttribute("nonce", cspNonce);
			document.head.appendChild(link);
			if (isCss) return new Promise((res, rej) => {
				link.addEventListener("load", res);
				link.addEventListener("error", () => rej(/* @__PURE__ */ new Error(`Unable to preload CSS for ${dep}`)));
			});
		}));
	}
	function handlePreloadError(err) {
		const e = new Event("vite:preloadError", { cancelable: true });
		e.payload = err;
		window.dispatchEvent(e);
		if (!e.defaultPrevented) throw err;
	}
	return promise.then((res) => {
		for (const item of res || []) {
			if (item.status !== "rejected") continue;
			handlePreloadError(item.reason);
		}
		return baseModule().catch(handlePreloadError);
	});
};
//#endregion
//#region frontend/src/main.tsx
var VIEW_MODULES = {
	overview: () => __vitePreload(() => import("./overview-DF1rEaV8.js"), __vite__mapDeps([0,1,2,3])),
	apps: () => __vitePreload(() => import("./apps-YsxOuX3Q.js"), __vite__mapDeps([4,1,5,6,2,7,3])),
	keyboard: () => __vitePreload(() => import("./keyboard-QI8Zu-yU.js"), __vite__mapDeps([8,1,5,6,2,7,3,9])),
	insights: () => __vitePreload(() => import("./insights-D1CZpRMb.js"), __vite__mapDeps([10,1,2,3,9]))
};
var viewRoot = null;
var activeRoute = null;
var activeModule = null;
/** 切换视图。React 负责卸载上一棵树（图表的 ResizeObserver 与总线订阅在 effect 里拆）。 */
async function mountRoute(route) {
	if (activeRoute === route) return;
	const load = VIEW_MODULES[route] || VIEW_MODULES.overview;
	let module;
	try {
		module = await load();
	} catch {
		fail("视图加载失败，请刷新页面");
		return;
	}
	activeRoute = route;
	activeModule = module;
	syncTabs(route);
	refresh();
	const { View } = module;
	viewRoot?.render(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_react.StrictMode, { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(View, {}) }));
	document.title = `${module.title} · OmniSight`;
	window.setTimeout(() => {
		document.querySelector("#view-title")?.focus();
	}, 0);
}
function syncTabs(route) {
	for (const id of ROUTES) document.getElementById(`tab-${id}`)?.setAttribute("aria-selected", String(id === route));
	document.getElementById("view-root")?.setAttribute("aria-labelledby", `tab-${route}`);
	document.body.dataset.route = route;
}
/** 按当前状态重新取数。周期变了要 abort 上一批，否则旧响应会覆盖新数据。 */
function refresh({ abort = true } = {}) {
	if (!activeModule) return;
	if (abort) abortPending();
	for (const request of activeModule.needs(getState())) fetchInto(request.key, request.path, request.params || {}, request.options || {});
}
/**
* data-action 分发表。声明式意图写在模板的标记上，处理集中在这里（07 文档 §7）。
*
* React 化之后它只服务**模板里那些标记**（视图标签栏）——React 组件里的按钮直接写
* onClick，不必绕这一圈。设置与关于原先也在这张表里（`settings:open` / `about:open`），
* 18 文档 批 1 之后它们各有一个地址，由工具条右段那个槽负责（PageLink / SettingsEntry）。
*/
var ACTIONS = {
	"route:go": (dataset) => go(dataset.route || "overview"),
	"import:open": () => openImportWizard(),
	"period:prev": () => step(-1),
	"period:next": () => step(1),
	"period:today": () => goToday()
};
function installDelegation() {
	document.addEventListener("click", (event) => {
		const target = event.target?.closest("[data-action]");
		if (!target) return;
		const handler = ACTIONS[target.dataset.action || ""];
		if (handler) handler(target.dataset);
	});
}
/** 快捷键（06 文档 §4.1）。输入框里一律不拦截，否则用户没法在搜索框里打 4。 */
function installShortcuts() {
	document.addEventListener("keydown", (event) => {
		if (event.metaKey || event.ctrlKey || event.altKey) return;
		const tag = (event.target?.tagName || "").toLowerCase();
		if (tag === "input" || tag === "select" || tag === "textarea") return;
		const index = [
			"1",
			"2",
			"3",
			"4"
		].indexOf(event.key);
		if (index >= 0) {
			go(ROUTES[index]);
			return;
		}
		if (event.key === "ArrowLeft") step(-1);
		else if (event.key === "ArrowRight") step(1);
		else if (event.key === "t" || event.key === "T") goToday();
		else if (event.key === "/") {
			const search = document.querySelector(".search input");
			if (search) {
				event.preventDefault();
				search.focus();
			}
		} else if (event.key === "?") showShortcutHelp();
	});
}
function showShortcutHelp() {
	show({
		title: "键盘快捷键",
		rows: [
			["1 - 4", "切换视图"],
			["左 / 右", "上一个 / 下一个周期"],
			["T", "回到今天"],
			["/", "聚焦搜索"],
			["方向键", "在键盘热力图上移动"]
		],
		x: window.innerWidth / 2 - 120,
		y: window.innerHeight / 2 - 80
	});
	window.setTimeout(hide, 4e3);
}
/** 读一条设置的当前值。 */
function valueOf(settings, key, fallback) {
	const spec = settings[key];
	return spec && spec.value !== null && spec.value !== void 0 ? spec.value : fallback;
}
/**
* 最近一次读到的设置全文。**判据是"这一份与上一份一样吗"，不是"有人喊了一声"**：轮询
* 那一路每 30 秒都会喊一次（它分不清变没变，见 core/stream.ts 的说明），而每喊一次就要
* 重取当前视图那四五个请求，只为了发现什么都没改。
*/
var settingsFingerprint = "";
/**
* 读一次设置：周起始日、默认周期、键盘布局、设置的打开方式都是**后端配置**，前端不猜。
*
* @returns 与上一次读到的相比变了吗（第一次总是变）
*/
async function loadPrefs() {
	try {
		const payload = await get("/settings");
		const settings = payload.settings || {};
		const fingerprint = JSON.stringify(settings);
		const changed = fingerprint !== settingsFingerprint;
		settingsFingerprint = fingerprint;
		setState("settings", payload);
		setState("prefs", {
			weekStartsOn: Number(valueOf(settings, "ui.week_starts_on", 0)),
			defaultRange: rangeFromDefaultView(String(valueOf(settings, "ui.default_view", "daily"))),
			keyboardLayout: String(valueOf(settings, "ui.keyboard_layout", "auto")),
			titlesRecorded: Boolean(valueOf(settings, "privacy.record_window_titles", false)),
			settingsSurface: String(valueOf(settings, "ui.settings_surface", "drawer"))
		});
		const theme = String(valueOf(settings, "ui.theme", "system"));
		if (theme !== getState().theme) set(theme);
		const heat = String(valueOf(settings, "ui.heat", "blue"));
		if (heat !== getState().heat) setHeat(heat);
		return changed;
	} catch {
		return false;
	}
}
/**
* 取数订阅。**渲染不在这里**：React 组件各自订阅自己关心的切片（core/useStore.ts），
* 数据到位就自己重画。这里只管"什么变化要重新发请求"。
*
* 这是 React 化省掉的一整块：原先有八个切片订阅同一个 `rerender()`，因为渲染是
* 手写的、必须有人来喊一声。
*/
function installSubscriptions() {
	subscribe("period", () => refresh());
	subscribe("metric", () => refresh());
	subscribe("scopeAppId", () => refresh());
	subscribe("selectedKeyId", () => refresh());
	on("data:invalidated", () => {
		const meta = getState().periodMeta;
		if (!meta || meta.is_current) refresh({ abort: false });
	});
	on("settings:changed", () => {
		loadPrefs().then((changed) => {
			if (changed) refresh({ abort: false });
		});
	});
}
/**
* 挂进模板给的那几个洞。它们互不嵌套，状态经 core/store.ts 共享。
*
* 工具条与三个浮层由 pages/shell.tsx 统一挂（三页共用）；这里只剩仪表盘独有的两条控件带
* 与视图根。工具条右段那个槽在这一页是 ⚙，它去哪儿由配置决定（见 SettingsEntry）。
*/
function mountShell() {
	mountChrome({
		nav: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ImportButton, {}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SettingsEntry, {})] }),
		banners: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ImportBanner, {})
	});
	(0, import_client.createRoot)(mountPoint("periodbar")).render(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_react.StrictMode, { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(DateBar, {}) }));
	(0, import_client.createRoot)(mountPoint("rangebar")).render(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_react.StrictMode, { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RangeBar, {}) }));
	viewRoot = (0, import_client.createRoot)(mountPoint("view-root"));
}
/**
* 导入向导的入口（17 文档 §4.1 的第四个功能钮）。
*
* 它有三个入口，各自的场合不同：这个钮（随时想导入）、`ImportBanner`（首次发现旧数据时
* 主动提示一次）、以及设置页「数据」段里那个按钮（在"数据"这件事的语境里）。三者调的是
* 同一个 `openImportWizard()`。
*/
function ImportButton() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
		className: "icon-button",
		type: "button",
		title: "从旧版导入",
		"aria-label": "从旧版导入数据",
		onClick: () => openImportWizard(),
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "download" })
	});
}
/**
* ⚙。**它去哪儿由配置决定**（`ui.settings_surface`，18 文档 §2.1）：抽屉开在仪表盘右侧，
* 或者跳到 `/settings` 那一页。原先它一律 `target="_blank"`，而"每点一次设置就多攒一个
* 标签页"没有任何设置关得掉——这是这次改动的起点。
*
* 两档下它都是**一个真链接**（`href` 始终指向 `/settings`），抽屉只接管不带修饰键的左键
* 点击，因此 Ctrl+点击、中键、右键「在新标签页打开」仍然有效（pages/shell.tsx:PageLink）。
*
* 读 store 里的 prefs 而不是渲染时算好的常量：这一项在抽屉里就能改，改完**下一次点击**
* 必须已经按新的走（`settings:changed` -> loadPrefs -> 这里重渲染）。
*/
function SettingsEntry() {
	const drawer = useSlice("prefs").settingsSurface === "drawer";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PageLink, {
		href: "/settings",
		icon: "gear",
		label: "设置",
		onActivate: drawer ? openSettings : null
	});
}
/** 抽屉那一份按需加载：首屏不为一个可能不点的面板付表单代码的钱（与四个视图同一个手法）。 */
function openSettings() {
	__vitePreload(() => import("./SettingsDrawer-DFjOpm1k.js").then((module) => module.openSettingsDrawer()), __vite__mapDeps([11,1,6,12,5,2])).catch(() => fail("设置面板加载失败，请刷新页面"));
}
async function main() {
	const token = adopt();
	mountShell();
	installDelegation();
	installShortcuts();
	installSubscriptions();
	if (!token) {
		viewRoot?.render(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(MissingToken, {}));
		return;
	}
	await Promise.all([loadStatus(), loadPrefs()]);
	start();
	if (!window.location.hash.includes("range=")) setState("period", {
		...getState().period,
		range: getState().prefs.defaultRange
	});
	subscribe("route", (route) => {
		mountRoute(route);
	});
	await mountRoute(getState().route);
	const settings = getState().settings;
	if (settings && !valueOf(settings.settings || {}, "privacy.realtime_stream", true)) startPolling();
	else connect();
	maybeShowOnboarding();
}
main();
//#endregion
export { fromISO as a, HEAT_BOUNDS as c, formatMetric as d, heatLevel as f, metricOf as h, bucketCoversGap as i, METRICS as l, isSaturated as m, METRIC_SLOT_ID as n, gapSet as o, heatRatio as p, Updated as r, periodParams as s, fetchInto as t, TIMELINE_VIEWS as u };
