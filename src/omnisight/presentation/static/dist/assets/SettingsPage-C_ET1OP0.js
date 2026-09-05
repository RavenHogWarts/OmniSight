import { A as ok, B as tokenParam, C as useSlice, E as setState, F as get, H as on, K as require_react, L as messageOf, R as patch, U as Icon, V as emit, W as require_jsx_runtime, c as set, j as ApiError, k as fail, l as setHeat, w as getState, z as post } from "./degraded-qMnijys5.js";
import { l as closeOverlay, s as pageUrl, u as openOverlay } from "./shell-8ge_e5M8.js";
import { a as Switch, s as openImportWizard } from "./controls-CacwHgpC.js";
import { t as Card } from "./Card-CwX6lTXj.js";
//#region frontend/src/pages/settings-fields.tsx
var import_react = require_react();
var import_jsx_runtime = require_jsx_runtime();
var LABELS = {
	"ui.theme": "主题",
	"ui.heat": "热力色",
	"ui.default_view": "默认周期",
	"ui.keyboard_layout": "键盘布局",
	"ui.week_starts_on": "周起始日",
	"ui.timezone": "时区",
	"ui.locale": "语言",
	"ui.shell": "外壳",
	"ui.settings_surface": "设置打开方式",
	"capture.paused": "暂停采集",
	"capture.idle_threshold_seconds": "空闲阈值（秒）",
	"capture.foreground_poll_seconds": "前台轮询间隔（秒）",
	"capture.session_flush_seconds": "会话落盘间隔（秒）",
	"capture.keyboard_backend": "键盘后端",
	"capture.store_raw_key_events": "保存原始按键事件",
	"privacy.record_window_titles": "记录窗口标题",
	"privacy.realtime_stream": "实时按键流",
	"privacy.excluded_processes": "排除的进程",
	"storage.data_dir": "数据目录",
	"storage.raw_event_retention_days": "原始事件保留天数",
	"storage.checkpoint_interval_seconds": "WAL 检查点间隔（秒）",
	"server.port": "端口",
	"system.autostart": "开机自启",
	"system.autostart_elevated": "登录时以管理员身份启动"
};
var OPTION_LABELS = {
	system: "跟随系统",
	light: "浅色",
	dark: "深色",
	blue: "蓝色",
	warm: "暖色",
	daily: "日",
	weekly: "周",
	monthly: "月",
	yearly: "年",
	total: "全部",
	auto: "自动",
	none: "关闭",
	raw_input: "Raw Input",
	pynput: "pynput",
	ansi104: "ANSI 104",
	iso105: "ISO 105",
	browser: "浏览器",
	drawer: "侧边抽屉",
	page: "独立页面"
};
var HINTS = {
	"capture.store_raw_key_events": "关闭后无法按应用查看键盘热力图，也无法重算历史聚合",
	"privacy.record_window_titles": "标题是最敏感的一档数据，默认关闭。接口默认也不下发",
	"privacy.realtime_stream": "关闭后键盘视图没有实时按压动画，改为 30 秒轮询",
	"ui.heat": "键盘热力图与日历格子的色阶。写入配置，因此换浏览器也一致"
};
function labelOf(key) {
	return LABELS[key] || key;
}
function optionLabel(value) {
	return OPTION_LABELS[String(value)] || String(value);
}
/** 一行设置。控件类型完全由 spec.kind 决定。 */
function Field({ settingKey, spec, onChange }) {
	const note = spec.unavailable_reason || spec.note || HINTS[settingKey] || "";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "field",
		"data-available": String(spec.available !== false),
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "field__label",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: labelOf(settingKey) }), spec.applies === "restart" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "field__tag",
					children: "需重启"
				}) : null]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Control, {
				settingKey,
				spec,
				onChange
			}),
			note ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: note
			}) : null
		]
	});
}
function Control({ settingKey, spec, onChange }) {
	const disabled = spec.available === false;
	const label = labelOf(settingKey);
	if (spec.kind === "bool") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Switch, {
		checked: Boolean(spec.value),
		disabled,
		label,
		onChange: (value) => onChange(settingKey, value)
	});
	if (spec.kind === "enum") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("select", {
		className: "control",
		disabled,
		"aria-label": label,
		value: String(spec.value ?? ""),
		onChange: (event) => onChange(settingKey, event.target.value),
		children: (spec.options || []).map((option) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
			value: String(option),
			children: optionLabel(option)
		}, String(option)))
	});
	if (spec.kind === "int" || spec.kind === "number") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
		className: "control",
		type: "number",
		defaultValue: spec.value === null || spec.value === void 0 ? "" : String(spec.value),
		disabled,
		"aria-label": label,
		min: spec.min === void 0 ? void 0 : String(spec.min),
		max: spec.max === void 0 ? void 0 : String(spec.max),
		step: spec.kind === "int" ? "1" : "any",
		onChange: (event) => {
			const raw = event.target.value;
			const value = spec.kind === "int" ? Number.parseInt(raw, 10) : Number.parseFloat(raw);
			if (Number.isNaN(value)) return;
			onChange(settingKey, value);
		}
	});
	if (spec.kind === "list") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
		className: "control",
		type: "text",
		defaultValue: Array.isArray(spec.value) ? spec.value.join(", ") : "",
		disabled,
		"aria-label": label,
		placeholder: "用逗号分隔",
		onBlur: (event) => onChange(settingKey, event.target.value.split(",").map((item) => item.trim()).filter(Boolean))
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
		className: "control",
		type: "text",
		defaultValue: spec.value === null || spec.value === void 0 ? "" : String(spec.value),
		disabled,
		"aria-label": label,
		onBlur: (event) => onChange(settingKey, event.target.value.trim() || null)
	});
}
/** 暂停走专用端点：它除了写配置还要真的停掉采集线程（05 文档 §7）。 */
function PauseField({ spec }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "field",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__label",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: "暂停采集" })
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Switch, {
				checked: Boolean(spec.value),
				label: "暂停采集",
				onChange: async (value) => {
					try {
						const result = await post("/capture/pause", { paused: value });
						ok(result.paused ? "采集已暂停" : "采集已恢复");
					} catch (error) {
						fail(messageOf(error));
					}
				}
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: "暂停期间不记录任何按键与前台时长。本次运行不会自动恢复。托盘菜单里那一项是同一条路径。"
			})
		]
	});
}
/**
* 走专用端点的开关：开机自启要写注册表、「登录时以管理员身份启动」要建计划任务
* （10 文档 §5.3），能力缺失时后端返回 422（不是"设置失败"）。
*
* **这两项的真源是操作系统，不是 config.json**（注册表项 / 登录计划任务）。写进配置文件
* 就会立刻有两份真相——"配置说开着、注册表里没有"，而 10 文档 §4 有一条不可退让的要求：
* 任何一条机制开着时，界面都不许显示"开机自启：关"。因此它们留在这里而不是进配置。
* 18 批 4 起托盘里那个勾选框撤掉了，这里是它唯一的落脚处。
*
* 不可用的原因**一定要显示**：提权那个开关多数时候是灰的（要装到 Program Files、
* 要先提权），而三种原因对应三种完全不同的下一步动作。
*/
function ActionToggle({ settingKey, spec, path, onReload }) {
	const label = labelOf(settingKey);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "field",
		"data-available": String(spec.available !== false),
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__label",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: label })
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Switch, {
				checked: Boolean(spec.value),
				disabled: spec.available === false,
				label,
				onChange: async (value) => {
					try {
						const result = await post(path, { enabled: value });
						ok([result.enabled ? `已开启${label}` : `已关闭${label}`, result.note].filter(Boolean).join("；"));
					} catch (error) {
						fail(messageOf(error));
					}
					onReload();
				}
			}),
			spec.unavailable_reason ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: spec.unavailable_reason
			}) : null,
			spec.note ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: spec.note
			}) : null
		]
	});
}
//#endregion
//#region frontend/src/components/Confirm.tsx
/** @returns 用户点了确认吗 */
function confirmDialog(options) {
	return new Promise((resolve) => {
		const settle = (value) => {
			closeOverlay();
			resolve(value);
		};
		openOverlay(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ConfirmCard, {
			options,
			onSettle: settle
		}));
	});
}
function ConfirmCard({ options, onSettle }) {
	const confirm = (0, import_react.useRef)(null);
	const opener = (0, import_react.useRef)(typeof document === "undefined" ? null : document.activeElement);
	const settle = (0, import_react.useRef)(onSettle);
	settle.current = onSettle;
	(0, import_react.useEffect)(() => {
		confirm.current?.focus();
		const onKeydown = (event) => {
			if (event.key !== "Escape") return;
			event.preventDefault();
			settle.current(false);
			opener.current?.focus();
		};
		document.addEventListener("keydown", onKeydown, true);
		return () => document.removeEventListener("keydown", onKeydown, true);
	}, []);
	const answer = (value) => {
		onSettle(value);
		opener.current?.focus();
	};
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
		className: "scrim",
		onClick: () => answer(false)
	}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "confirm",
		role: "dialog",
		"aria-modal": "true",
		"aria-labelledby": "confirm-title",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
				id: "confirm-title",
				children: options.title
			}),
			options.detail ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "muted",
				children: options.detail
			}) : null,
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "confirm__foot",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
					className: "button",
					type: "button",
					onClick: () => answer(false),
					children: "取消"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
					className: options.danger ? "button button--danger" : "button button--primary",
					type: "button",
					ref: confirm,
					onClick: () => answer(true),
					children: options.confirmLabel || "确定"
				})]
			})
		]
	})] });
}
//#endregion
//#region frontend/src/pages/system-actions.tsx
/** 探活走免令牌的 `/healthz`（它只回一个字面量，见 web.py）。 */
async function healthy() {
	try {
		return (await fetch("/healthz", {
			cache: "no-store",
			credentials: "omit"
		})).ok;
	} catch {
		return false;
	}
}
/**
* 等到**另一个实例**在应答。
*
* 判据是 `/api/v1/status` 的 `started_at` 变了，而不是"端口上有人应答"——后者分不出新旧，
* 而旧实例在收到重启请求之后还要活一小会儿（响应先出门，停机排在 0.4 秒后的线程里）。
* 原先的写法是"先等它下线、再等它上线"，而整个下线窗口可能落在两次轮询之间：那时页面会
* 立刻刷新，刷到的是正在拆自己的旧实例。
*
* 401 是另一种结局：接班实例换了令牌（继承那一步没成，见 `core/lifecycle._claim_session`），
* 这一页手里那份从此无效。**这时不能刷新**——刷出来是一个连不上数据的空壳，而用户需要知道
* 该回托盘重新打开。
*/
async function nextInstance(before) {
	const deadline = Date.now() + 9e4;
	while (Date.now() < deadline) {
		try {
			const status = await get("/status");
			if (String(status.started_at || "") !== before) return "ready";
		} catch (error) {
			if (error instanceof ApiError && error.status === 401) return "token";
		}
		await new Promise((resolve) => window.setTimeout(resolve, 500));
	}
	return "timeout";
}
/** 轮询到条件成立或超时。@returns 成立了吗 */
async function until(condition, timeoutMs) {
	const deadline = Date.now() + timeoutMs;
	while (Date.now() < deadline) {
		if (await condition()) return true;
		await new Promise((resolve) => window.setTimeout(resolve, 400));
	}
	return false;
}
async function restartApp() {
	if (!await confirmDialog({
		title: "重新启动 OmniSight？",
		detail: "采集会中断几秒，然后自动继续。需重启才生效的设置会在这次启动时生效。",
		confirmLabel: "重新启动"
	})) return;
	try {
		await post("/system/restart", {});
	} catch (error) {
		fail(messageOf(error, "重启请求失败"));
		return;
	}
	openOverlay(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Restarting, {}));
}
async function quitApp() {
	if (!await confirmDialog({
		title: "退出 OmniSight？",
		detail: "退出后不再记录任何按键与前台时长，直到你手动重新启动它。",
		confirmLabel: "退出",
		danger: true
	})) return;
	try {
		await post("/system/quit", {});
	} catch (error) {
		fail(messageOf(error, "退出请求失败"));
		return;
	}
	openOverlay(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Stopping, {}));
}
/** 打开数据目录 / 日志目录。后端负责"管理员模式下降权打开"（lifecycle._open_external）。 */
function RevealButton({ target, label }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
		className: "button",
		type: "button",
		onClick: async () => {
			try {
				await post("/system/reveal", { target });
			} catch (error) {
				fail(messageOf(error, "打开目录失败"));
			}
		},
		children: label
	});
}
/**
* 「正在重启」。等的是"另一个实例在应答"（见 `nextInstance`），不是"端口通了"。
*
* `started_at` 读的是本页启动时那一份状态。读不到时（状态本来就没取到）退回旧办法：先等
* 它下线，再等它上线——那时无从分辨新旧，但至少不会在旧实例还在应答时就刷新。
*/
function Restarting() {
	const [phase, setPhase] = (0, import_react.useState)("wait");
	(0, import_react.useEffect)(() => {
		let cancelled = false;
		const before = String(getState().status?.started_at || "");
		(async () => {
			if (!before) await until(async () => !await healthy(), 15e3);
			const outcome = await nextInstance(before);
			if (cancelled) return;
			if (outcome === "ready") window.location.reload();
			else setPhase(outcome === "token" ? "token" : "failed");
		})();
		return () => {
			cancelled = true;
		};
	}, []);
	if (phase === "token") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Blocker, {
		title: "重启完成，但令牌要重新交接",
		detail: "接班实例换用了新的访问令牌，这一页手里那份已经失效。请从托盘菜单重新打开仪表盘——刷新这一页只会得到一个读不到数据的外壳。",
		action: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "button",
			type: "button",
			onClick: () => closeOverlay(),
			children: "知道了"
		})
	});
	if (phase === "failed") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Blocker, {
		title: "没等到新实例应答",
		detail: "它可能仍在启动，也可能启动失败。请查看日志目录里的 STARTUP_ERROR.txt，或从桌面图标重新打开。",
		action: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "button button--primary",
			type: "button",
			onClick: () => closeOverlay(),
			children: "知道了"
		})
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Blocker, {
		title: "正在重启…",
		detail: "等新实例接手后这一页会自动刷新。",
		spinner: true
	});
}
/** 「已退出」。不刷新页面：刷新只会得到一个连不上的外壳。 */
function Stopping() {
	const [done, setDone] = (0, import_react.useState)(false);
	(0, import_react.useEffect)(() => {
		let cancelled = false;
		(async () => {
			const down = await until(async () => !await healthy(), 2e4);
			if (!cancelled && down) setDone(true);
		})();
		return () => {
			cancelled = true;
		};
	}, []);
	return done ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Blocker, {
		title: "OmniSight 已退出",
		detail: "采集已停止。从开始菜单或桌面图标可以重新启动它；这个标签页可以关掉了。"
	}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Blocker, {
		title: "正在退出…",
		spinner: true
	});
}
/** 挡住整页的一张卡。重启与退出期间点什么都没有意义，因此不给关闭入口（除非传 action）。 */
function Blocker({ title, detail, spinner = false, action }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "scrim" }), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "confirm",
		role: "alertdialog",
		"aria-live": "assertive",
		"aria-label": title,
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", { children: title }),
			detail ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "muted",
				children: detail
			}) : null,
			spinner ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "veil__spinner" }) : null,
			action ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "confirm__foot",
				children: action
			}) : null
		]
	})] });
}
/** 设置页底部那一段。两个动作各自确认，措辞里说清代价。 */
function ProcessActions() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "actions",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "button",
			type: "button",
			onClick: () => void restartApp(),
			children: "重新启动…"
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
			className: "button button--danger",
			type: "button",
			onClick: () => void quitApp(),
			children: "退出 OmniSight…"
		})]
	});
}
//#endregion
//#region frontend/src/pages/settings-sections.tsx
/** 能力名的中文。`capabilities` 只读布尔值，这里只是给它们起个名字。 */
var CAPABILITY_NAMES = {
	keyboard: "键盘采集",
	foreground: "应用归因",
	window_titles: "窗口标题",
	idle: "空闲检测",
	icons: "应用图标",
	autostart: "开机自启",
	tray: "托盘图标",
	keyboard_durations: "按压时长",
	key_position_stable: "左右键位可分"
};
/**
* 导出用普通链接而不是 fetch：响应是流式的附件，交给浏览器下载最省事。
* 令牌走查询串（下载请求带不了自定义头，与图标同一个理由）。
*
* **范围固定 `total`**：设置页没有周期栏，而"从设置页导出"的合理默认是全部数据。原先它
* 长在抽屉里，能读到仪表盘当前那个周期；独立成页之后那个上下文不存在了，继续读 store 里
* 的默认值等于悄悄只导出了今天。
*/
function ExportLink({ scope, format, label }) {
	const params = new URLSearchParams({
		scope,
		format,
		range: "total"
	});
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
		className: "button",
		href: `/api/v1/export?${params.toString()}&token=${encodeURIComponent(tokenParam())}`,
		download: "",
		children: label
	});
}
/** 数据与导出。备份、重算聚合与删除数据排在后续版本——**说明而不是画一个禁用按钮**。 */
function DataCard({ status }) {
	const database = status?.database;
	const range = status?.data_range;
	const size = database?.size_bytes ? `${(database.size_bytes / 1048576).toFixed(1)} MB` : "-";
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Card, {
		title: "数据与导出",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("dl", {
				className: "kv-list",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "数据库" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: size }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "数据范围" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: range?.min_date ? `${range.min_date} 至 ${range.max_date}` : "暂无数据" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "schema" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: String(database?.schema_version || "-") }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "数据库文件" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", {
						className: "mono",
						children: database?.path || "-"
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "actions",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ExportLink, {
						scope: "usage",
						format: "csv",
						label: "导出使用记录 CSV"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ExportLink, {
						scope: "keyboard",
						format: "csv",
						label: "导出键盘统计 CSV"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(ExportLink, {
						scope: "all",
						format: "json",
						label: "导出全部 JSON"
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "actions",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RevealButton, {
						target: "data",
						label: "打开数据目录"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)(RevealButton, {
						target: "logs",
						label: "打开日志目录"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						className: "button",
						type: "button",
						onClick: () => openImportWizard(),
						children: "从旧版导入数据…"
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: "备份、重算聚合与删除数据排在后续版本。"
			})
		]
	});
}
/** 能力说明：所有 degraded 都在这里列全，横幅只上 error 一级。 */
function CapabilityCard() {
	const capabilities = useSlice("capabilities");
	const degraded = useSlice("degraded");
	const read = capabilities;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Card, {
		title: "运行环境能力",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dl", {
			className: "kv-list",
			children: Object.entries(CAPABILITY_NAMES).map(([key, name]) => {
				if (!read || read[key] === void 0) return null;
				return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					style: { display: "contents" },
					children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: name }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: read[key] ? "可用" : "不可用" })]
				}, key);
			})
		}), (degraded || []).map((notice) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
			className: "notice",
			"data-severity": notice.severity,
			children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "notice__mark",
				"aria-hidden": "true",
				children: "i"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "notice__title",
					children: notice.title
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "notice__detail",
					children: notice.detail
				}),
				notice.hint ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "notice__hint",
					children: notice.hint
				}) : null
			] })]
		}, notice.code || notice.title))]
	});
}
/** 关于。详细的隐私说明在 `/about`——这里只留版本、环境与一条去那一页的链接。 */
function AboutCard({ status, configPath }) {
	const platform = status?.platform;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Card, {
		title: "关于",
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
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: String(status?.port || "-") }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: "配置文件" }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", {
						className: "mono",
						children: configPath || "-"
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "actions",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
					className: "button",
					href: pageUrl("/about"),
					children: "关于与隐私说明 →"
				})
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "field__note",
				children: "所有数据只保存在本机，不上传任何服务器。本程序不记录按键内容，只记录按了哪个键、多少次。"
			})
		]
	});
}
//#endregion
//#region frontend/src/pages/SettingsPage.tsx
var GROUPS = [
	{
		id: "appearance",
		title: "外观",
		prefixes: ["ui."]
	},
	{
		id: "capture",
		title: "采集",
		prefixes: ["capture."]
	},
	{
		id: "privacy",
		title: "隐私",
		prefixes: ["privacy."]
	},
	{
		id: "data",
		title: "数据",
		prefixes: ["storage."]
	},
	{
		id: "system",
		title: "系统",
		prefixes: ["server.", "system."]
	}
];
/** 页顶那句话。两档共用同一份措辞：说两遍就会有一天只改了一遍。 */
var LEAD = "改动即时保存；需重启的项会说明，并给出重启入口。";
function groupFromHash() {
	const id = window.location.hash.replace(/^#\/?/, "");
	return GROUPS.some((group) => group.id === id) ? id : GROUPS[0].id;
}
/** 取一次设置与状态。入口首屏与每次改动之后都走它。 */
async function loadSettings() {
	const [settings, status] = await Promise.all([get("/settings"), get("/status")]);
	setState("settings", settings);
	setState("status", status);
}
/** 重读表单。改完、被别处改了、以及一次失败的写入之后都走它。 */
function reload() {
	loadSettings().catch(() => fail("重读设置失败"));
}
function SettingsPage({ surface = "page" }) {
	const payload = useSlice("settings");
	const status = useSlice("status");
	const settings = payload?.settings || {};
	const onPage = surface === "page";
	const [group, setGroup] = (0, import_react.useState)(() => onPage ? groupFromHash() : GROUPS[0].id);
	const [pending, setPending] = (0, import_react.useState)([]);
	(0, import_react.useEffect)(() => {
		if (!onPage) return;
		const onHash = () => setGroup(groupFromHash());
		window.addEventListener("hashchange", onHash);
		return () => window.removeEventListener("hashchange", onHash);
	}, [onPage]);
	(0, import_react.useEffect)(() => on("settings:changed", reload), []);
	const pick = (id) => {
		if (onPage) history.replaceState(null, "", `#${id}`);
		setGroup(id);
	};
	const apply = (key, value) => {
		(async () => {
			try {
				const result = await patch("/settings", { settings: { [key]: value } });
				const rejected = (result.rejected || []).find((item) => item.key === key);
				if (rejected) {
					fail(`${labelOf(key)}：${rejected.message}`);
					reload();
					return;
				}
				const restart = (result.requires_restart || []).includes(key);
				ok(restart ? `${labelOf(key)} 已保存，重启后生效` : `${labelOf(key)} 已生效`);
				if (restart) setPending((keys) => keys.includes(key) ? keys : [...keys, key]);
				if (key === "ui.theme") set(String(value));
				if (key === "ui.heat") setHeat(String(value));
				emit("settings:changed", { key });
			} catch (error) {
				fail(messageOf(error));
				reload();
			}
		})();
	};
	const current = GROUPS.find((item) => item.id === group) || GROUPS[0];
	const keys = Object.keys(settings).filter((key) => current.prefixes.some((prefix) => key.startsWith(prefix))).sort();
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		pending.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(RestartNotice, { keys: pending }) : null,
		onPage ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
			className: "section-heading section-heading--lead",
			children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
				className: "section-title",
				id: "page-title",
				children: "设置"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "section-sub",
				children: LEAD
			})] })
		}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "section-sub",
			children: LEAD
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("nav", {
			className: "viewbar settings-nav",
			role: "tablist",
			"aria-label": "设置分组",
			children: GROUPS.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "viewbar__tab",
				role: "tab",
				type: "button",
				"aria-selected": item.id === current.id,
				onClick: () => pick(item.id),
				children: item.title
			}, item.id))
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)(Card, {
			title: current.title,
			children: keys.length ? keys.map((key) => {
				const spec = settings[key];
				if (key === "capture.paused") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(PauseField, { spec }, key);
				if (key === "system.autostart" || key === "system.autostart_elevated") return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ActionToggle, {
					settingKey: key,
					spec,
					path: key === "system.autostart" ? "/settings/autostart" : "/settings/autostart-elevated",
					onReload: reload
				}, key);
				return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Field, {
					settingKey: key,
					spec,
					onChange: apply
				}, key);
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "muted",
				children: "读不到这一段的设置项。"
			})
		}),
		current.id === "data" ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)(DataCard, { status }) : null,
		current.id === "system" ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(CapabilityCard, {}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(AboutCard, {
				status,
				configPath: payload?.config_path || ""
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)(Card, {
				title: "进程",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "field__note",
					children: "重启会中断采集几秒；退出会一直停到你手动重新启动它。托盘菜单里是同两个入口。"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ProcessActions, {})]
			})
		] }) : null
	] });
}
/** 「有 N 项改动要重启后生效」。它是重启的第二个入口，另一个在「系统」段里。 */
function RestartNotice({ keys }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "banner",
		"data-severity": "warning",
		role: "status",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "banner__mark",
				"aria-hidden": "true",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "warning" })
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "banner__body",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "banner__title",
					children: [
						"本次改动有 ",
						keys.length,
						" 项要重启后生效"
					]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
					className: "banner__detail",
					children: keys.map(labelOf).join("、")
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "button",
				type: "button",
				onClick: () => void restartApp(),
				children: "立即重启…"
			})
		]
	});
}
//#endregion
export { loadSettings as n, SettingsPage as t };
