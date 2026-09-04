import { A as formatPercent, B as capabilityOf, F as del, G as setState, H as useResource, I as messageOf, J as require_react_dom, L as patch, M as fail, N as ok, R as post, T as formatCount, U as useSlice, V as noticeFor, W as getState, Y as require_react, a as FILTERS_SLOT_ID, c as SearchBox, h as periodParams, l as Segmented, n as fetchInto, o as Checkbox, q as require_jsx_runtime, s as Chip, u as Switch } from "./main-DA_wrxiB.js";
import { t as AppRow } from "./AppRow-BMX9Ac2T.js";
import { n as EmptyState, o as SkeletonRows, r as ErrorState, s as Card, t as CapabilityNotice } from "./states-DZ-0dhHV.js";
//#region frontend/src/views/apps.tsx
var import_react = require_react();
var import_react_dom = require_react_dom();
var import_jsx_runtime = require_jsx_runtime();
var title = "应用";
var PAGE_SIZE = 25;
var SORTS = [
	{
		id: "seconds",
		name: "时长"
	},
	{
		id: "presses",
		name: "按键"
	},
	{
		id: "sessions",
		name: "次数"
	},
	{
		id: "name",
		name: "名称"
	},
	{
		id: "last_seen",
		name: "最近"
	}
];
/** 搜索词变化到重取之间的间隔。本机请求毫秒级，防的是连打时的请求风暴。 */
var SEARCH_DEBOUNCE_MS = 300;
/**
* 影响**请求参数**的两个视图内状态。
*
* 它们放在模块作用域而不是组件里，因为 `needs(state)` 要读到它们——而 `needs` 是
* 模块级导出（main.tsx 在组件之外调用它来编排取数）。类版本里这两个变量在
* `create()` 的闭包里，`needs` 是实例方法，因此看得见；这里只是把同一个闭包抬到了
* 模块上。**刻意不进 store**：它们是这一个视图的筛选态，不是全局状态（07 文档 §4.3）。
*/
var viewParams = {
	query: "",
	includeExcluded: false
};
function needs(state) {
	const period = periodParams(state.period);
	const requests = [{
		key: "appsPeriod",
		path: "/usage/period",
		params: {
			...period,
			limit: 500,
			q: viewParams.query
		}
	}, {
		key: "appsMeta",
		path: "/apps",
		params: {
			limit: 500,
			include_excluded: viewParams.includeExcluded
		}
	}];
	if (state.selectedAppId) {
		requests.push({
			key: "appDetail",
			path: `/apps/${state.selectedAppId}`
		});
		requests.push({
			key: "appSessions",
			path: "/usage/sessions",
			params: {
				...period,
				app_id: state.selectedAppId,
				limit: 20
			}
		});
	}
	return requests;
}
function num(value) {
	return Number(value) || 0;
}
function nameOf(row) {
	return row.user_alias || row.display_name || row.process_name || "";
}
/** 把周期列表与管理元数据合并成一份。派生结果不入 store（07 文档 §4.3）。 */
function joinApps(periodPayload, appsPayload, options) {
	const meta = /* @__PURE__ */ new Map();
	for (const app of appsPayload?.apps || []) meta.set(app.app_id, app);
	const rows = [];
	for (const app of periodPayload?.apps || []) rows.push({
		...meta.get(app.app_id) || {},
		...app
	});
	if (options.includeExcluded) {
		const seen = new Set(rows.map((row) => row.app_id));
		for (const app of meta.values()) if (app.excluded && !seen.has(app.app_id)) rows.push({
			...app,
			seconds: 0,
			presses: 0,
			percent: 0
		});
	}
	return rows;
}
function applyFilters(rows, options) {
	const needle = options.query.toLowerCase();
	let items = [...rows];
	if (needle) items = items.filter((row) => {
		const name = (row.user_alias || row.display_name || "").toLowerCase();
		const process = (row.process_name || "").toLowerCase();
		return name.includes(needle) || process.includes(needle);
	});
	if (options.category) items = items.filter((row) => (row.category || "uncategorized") === options.category);
	items.sort((left, right) => {
		switch (options.sort) {
			case "presses": return num(right.presses) - num(left.presses);
			case "sessions": return num(right.session_count) - num(left.session_count);
			case "name": return nameOf(left).localeCompare(nameOf(right), "zh-CN");
			case "last_seen": return String(right.last_seen_at || "").localeCompare(String(left.last_seen_at || ""));
			default: return num(right.seconds) - num(left.seconds);
		}
	});
	return items;
}
/** 重取整屏。写操作之后必调：写操作会让缓存整体失效并递增 data_version。 */
function reload() {
	const state = getState();
	const period = periodParams(state.period);
	fetchInto("appsPeriod", "/usage/period", {
		...period,
		limit: 500,
		q: viewParams.query
	});
	fetchInto("appsMeta", "/apps", {
		limit: 500,
		include_excluded: viewParams.includeExcluded
	});
	if (state.selectedAppId) loadDetail(state.selectedAppId);
}
function loadDetail(appId) {
	fetchInto("appDetail", `/apps/${appId}`);
	fetchInto("appSessions", "/usage/sessions", {
		...periodParams(getState().period),
		app_id: appId,
		limit: 20
	});
}
function View() {
	const capabilities = useSlice("capabilities");
	const degraded = useSlice("degraded");
	const selectedAppId = useSlice("selectedAppId");
	const period = useResource("appsPeriod");
	const meta = useResource("appsMeta");
	const [query, setQuery] = (0, import_react.useState)(viewParams.query);
	const [includeExcluded, setIncludeExcluded] = (0, import_react.useState)(viewParams.includeExcluded);
	const [category, setCategory] = (0, import_react.useState)("");
	const [sort, setSort] = (0, import_react.useState)("seconds");
	const [page, setPage] = (0, import_react.useState)(0);
	const searchTimer = (0, import_react.useRef)(0);
	(0, import_react.useEffect)(() => {
		if (selectedAppId) loadDetail(selectedAppId);
	}, [selectedAppId]);
	(0, import_react.useEffect)(() => {
		viewParams.query = query;
		window.clearTimeout(searchTimer.current);
		searchTimer.current = window.setTimeout(() => {
			fetchInto("appsPeriod", "/usage/period", {
				...periodParams(getState().period),
				limit: 500,
				q: query
			});
		}, SEARCH_DEBOUNCE_MS);
		return () => window.clearTimeout(searchTimer.current);
	}, [query]);
	(0, import_react.useEffect)(() => {
		viewParams.includeExcluded = includeExcluded;
		fetchInto("appsMeta", "/apps", {
			limit: 500,
			include_excluded: includeExcluded
		});
	}, [includeExcluded]);
	const slot = document.getElementById(FILTERS_SLOT_ID);
	const error = period.error || meta.error;
	const catalog = meta.data?.categories || [];
	const rows = applyFilters(joinApps(period.data, meta.data, { includeExcluded }), {
		query,
		category,
		sort
	});
	const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
	const current = Math.min(page, pages - 1);
	const slice = rows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);
	const maxSeconds = Math.max(0, ...rows.map((row) => num(row.seconds)));
	const maxKpm = Math.max(0, ...rows.map((row) => num(row.kpm)));
	const foregroundOk = capabilityOf(capabilities, "foreground");
	const notice = noticeFor(degraded, "foreground");
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
			className: "view__title sr-only",
			tabIndex: -1,
			id: "view-title",
			children: "应用"
		}),
		slot ? (0, import_react_dom.createPortal)(/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(SearchBox, {
				placeholder: "搜索应用",
				value: query,
				onInput: setQuery
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Segmented, {
				items: SORTS,
				active: sort,
				onPick: (id) => {
					setSort(id);
					setPage(0);
				},
				small: true,
				label: "排序"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Checkbox, {
				label: "显示已排除",
				checked: includeExcluded,
				onChange: (value) => {
					setIncludeExcluded(value);
					setPage(0);
				}
			})
		] }), slot) : null,
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
			title: "应用",
			footer: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "row row--wrap",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "row row--wrap",
						children: [{
							id: "",
							name: "全部"
						}, ...catalog].map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Chip, {
							item,
							active: category === item.id,
							onPick: (id) => {
								setCategory(id);
								setPage(0);
							}
						}, item.id || "all"))
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { className: "spacer" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "apps__count",
						children: foregroundOk && period.data ? `${rows.length} 个应用，合计 ${period.data.total_seconds_formatted || ""}` : ""
					})
				]
			}),
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "app-list",
					children: !foregroundOk ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CapabilityNotice, {
						title: notice?.title || "当前环境不支持识别前台应用",
						detail: notice?.detail || "键盘统计不受影响。这个面板依赖前台窗口信息，因此无法显示。",
						hint: notice?.hint || ""
					}) : error ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ErrorState, {
						message: error.message,
						onRetry: reload
					}) : !period.data ? period.loading ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 6 }) : null : !slice.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(EmptyState, {
						title: query ? "没有匹配的应用" : "这段时间没有使用记录",
						detail: query ? "换一个关键词试试" : "把范围切到全部即可查看历史数据"
					}) : slice.map((row) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AppRow, {
						app: row,
						maxSeconds,
						maxKpm,
						expanded: selectedAppId === row.app_id,
						onToggle: (appId) => setState("selectedAppId", getState().selectedAppId === appId ? null : appId)
					}, row.app_id))
				}),
				foregroundOk && selectedAppId && slice.some((row) => row.app_id === selectedAppId) ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(AppDetail, {
					appId: selectedAppId,
					catalog,
					rows
				}) : null,
				pages > 1 ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "pager",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
							className: "button",
							type: "button",
							disabled: current === 0,
							onClick: () => setPage(current - 1),
							children: "上一页"
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
							current + 1,
							" / ",
							pages
						] }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
							className: "button",
							type: "button",
							disabled: current >= pages - 1,
							onClick: () => setPage(current + 1),
							children: "下一页"
						})
					]
				}) : null
			] })
		})
	] });
}
function AppDetail({ appId, catalog, rows }) {
	const detail = useResource("appDetail");
	const sessions = useResource("appSessions");
	if (!detail.data || detail.data.app.app_id !== appId) return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "app-detail",
		children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SkeletonRows, { count: 3 })
	});
	const app = detail.data.app;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "app-detail",
		children: [
			app.exe_path ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "app-detail__path",
				children: app.exe_path
			}) : null,
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Totals, { totals: detail.data.totals }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(KeyboardSummary, { keyboard: detail.data.keyboard }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Sessions, { payload: sessions.data }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Editor, {
				app,
				catalog,
				rows
			})
		]
	});
}
function Totals({ totals }) {
	const labels = [
		["day", "今天"],
		["week", "本周"],
		["month", "本月"],
		["total", "总计"]
	];
	const read = (key) => totals?.[key];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("dl", {
		className: "app-detail__totals",
		children: labels.map(([key, label]) => {
			const part = read(key);
			return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "app-detail__total",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: label }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: part?.seconds_formatted || "0秒" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "text-xs dim numeric",
						children: [formatCount(part?.presses || 0), " 次按键"]
					})
				]
			}, key);
		})
	});
}
function KeyboardSummary({ keyboard }) {
	if (!keyboard) return null;
	const keys = keyboard.top_keys || [];
	const modifiers = keyboard.modifier_breakdown || [];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "text-sm muted",
			children: [
				"键盘概况：",
				(keyboard.kpm || 0).toFixed(1),
				" KPM（",
				keyboard.profile_name || "",
				"）"
			]
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "app-detail__keys",
			children: keys.map((key) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
				className: "key-chip",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("b", { children: key.label }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: formatCount(key.press_count) })]
			}, key.id || key.label))
		}),
		modifiers.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "card__hint",
			children: [
				"修饰键偏好：",
				modifiers.slice(0, 4).map((item) => `${item.label} ${formatPercent(item.percent)}`).join(" · "),
				"（口径：修饰键自身被按下的次数）"
			]
		}) : null,
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "button",
			type: "button",
			onClick: () => {
				setState("scopeAppId", getState().selectedAppId);
				setState("route", "keyboard");
			},
			children: "查看完整键盘热力图"
		})
	] });
}
function Sessions({ payload }) {
	const sessions = payload?.sessions || [];
	if (!sessions.length) return null;
	const clock = (value) => String(value || "").slice(11, 16);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "text-sm muted",
			children: [
				"最近 ",
				sessions.length,
				" 次访问"
			]
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "session-list",
			children: sessions.map((session, index) => {
				const start = clock(session.start);
				const end = clock(session.end);
				return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "session-row",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: start && end ? `${start}-${end}` : start || end }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "truncate",
							children: session.window_title || ""
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "numeric",
							children: session.seconds_formatted
						})
					]
				}, `${session.start}-${index}`);
			})
		}),
		payload?.titles_included ? null : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "card__hint",
			children: "窗口标题未记录（隐私设置默认关闭）"
		})
	] });
}
/**
* 管理操作。写操作会让缓存整体失效并递增 data_version，因此改完立刻能看到新名字。
*
* "合并到…"（M3 已知限制 4 的补齐）：候选来自当前周期的列表——被排除的应用不在
* 列表里，但它们本来也不该作为合并目标。
*/
function Editor({ app, catalog, rows }) {
	const [alias, setAlias] = (0, import_react.useState)(app.user_alias || "");
	const [category, setCategory] = (0, import_react.useState)(app.category || "");
	const [target, setTarget] = (0, import_react.useState)("");
	(0, import_react.useEffect)(() => {
		setAlias(app.user_alias || "");
		setCategory(app.category || "");
		setTarget("");
	}, [
		app.app_id,
		app.user_alias,
		app.category
	]);
	const write = async (body, message) => {
		try {
			await patch(`/apps/${app.app_id}`, body);
			ok(message);
			reload();
		} catch (error) {
			fail(messageOf(error));
		}
	};
	const mergeInto = async () => {
		const into = Number.parseInt(target, 10);
		if (!Number.isFinite(into) || into <= 0) {
			fail("先选择要合并到的应用");
			return;
		}
		try {
			await post(`/apps/${app.app_id}/merge`, { into_app_id: into });
			ok("已合并，两边的统计从此算作一个应用");
			reload();
		} catch (error) {
			fail(messageOf(error));
		}
	};
	const unmerge = async () => {
		try {
			await del(`/apps/${app.app_id}/merge`);
			ok("已取消合并");
			reload();
		} catch (error) {
			fail(messageOf(error));
		}
	};
	const members = /* @__PURE__ */ new Set([app.app_id, ...app.merged_members || []]);
	const candidates = rows.filter((row) => !members.has(row.app_id) && !row.merged_into);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "app-actions",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
				className: "row",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "text-sm muted",
					children: "别名"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
					className: "control",
					type: "text",
					value: alias,
					placeholder: app.display_name || "",
					"aria-label": "自定义名称",
					maxLength: 120,
					onChange: (event) => setAlias(event.target.value)
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "button button--primary",
				type: "button",
				onClick: () => write({ user_alias: alias.trim() || null }, "已更新名称"),
				children: "保存别名"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
				className: "row",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "text-sm muted",
					children: "分类"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("select", {
					className: "control",
					"aria-label": "分类",
					value: category,
					onChange: (event) => setCategory(event.target.value),
					children: catalog.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
						value: item.id,
						children: item.name
					}, item.id))
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "button",
				type: "button",
				onClick: () => write({ category }, "已更新分类"),
				children: "保存分类"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
				className: "row",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "text-sm muted",
					children: "排除"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Switch, {
					checked: Boolean(app.excluded),
					label: "排除此应用",
					onChange: (value) => write({ excluded: value }, value ? "已排除" : "已取消排除")
				})]
			}),
			app.merged_into ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "button",
				type: "button",
				onClick: unmerge,
				children: "取消合并"
			}) : null,
			app.merged_members?.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
				className: "text-xs dim",
				children: [
					"已合并 ",
					app.merged_members.length,
					" 个来源"
				]
			}) : null,
			!app.merged_into ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "app-actions__merge",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "text-sm muted",
						children: "合并到…"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
						className: "control",
						"aria-label": "合并到哪个应用",
						value: target,
						onChange: (event) => setTarget(event.target.value),
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
							value: "",
							children: "选择目标应用…"
						}), candidates.map((row) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
							value: String(row.app_id),
							children: nameOf(row)
						}, row.app_id))]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						className: "button",
						type: "button",
						onClick: mergeInto,
						children: "合并"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "text-xs dim",
						children: "两个进程的统计从此算作一个应用（如 Code.exe 与 Code - Insiders.exe）"
					})
				]
			}) : null
		]
	});
}
//#endregion
export { View, applyFilters, joinApps, needs, title };
