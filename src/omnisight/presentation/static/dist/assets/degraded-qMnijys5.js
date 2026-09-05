//#region \0rolldown/runtime.js
var __commonJSMin = (cb, mod) => () => (mod || (cb((mod = { exports: {} }).exports, mod), cb = null), mod.exports);
//#endregion
//#region node_modules/.pnpm/react@19.2.8/node_modules/react/cjs/react.production.js
/**
* @license React
* react.production.js
*
* Copyright (c) Meta Platforms, Inc. and affiliates.
*
* This source code is licensed under the MIT license found in the
* LICENSE file in the root directory of this source tree.
*/
var require_react_production = /* @__PURE__ */ __commonJSMin(((exports) => {
	var REACT_ELEMENT_TYPE = Symbol.for("react.transitional.element");
	var REACT_PORTAL_TYPE = Symbol.for("react.portal");
	var REACT_FRAGMENT_TYPE = Symbol.for("react.fragment");
	var REACT_STRICT_MODE_TYPE = Symbol.for("react.strict_mode");
	var REACT_PROFILER_TYPE = Symbol.for("react.profiler");
	var REACT_CONSUMER_TYPE = Symbol.for("react.consumer");
	var REACT_CONTEXT_TYPE = Symbol.for("react.context");
	var REACT_FORWARD_REF_TYPE = Symbol.for("react.forward_ref");
	var REACT_SUSPENSE_TYPE = Symbol.for("react.suspense");
	var REACT_MEMO_TYPE = Symbol.for("react.memo");
	var REACT_LAZY_TYPE = Symbol.for("react.lazy");
	var REACT_ACTIVITY_TYPE = Symbol.for("react.activity");
	var MAYBE_ITERATOR_SYMBOL = Symbol.iterator;
	function getIteratorFn(maybeIterable) {
		if (null === maybeIterable || "object" !== typeof maybeIterable) return null;
		maybeIterable = MAYBE_ITERATOR_SYMBOL && maybeIterable[MAYBE_ITERATOR_SYMBOL] || maybeIterable["@@iterator"];
		return "function" === typeof maybeIterable ? maybeIterable : null;
	}
	var ReactNoopUpdateQueue = {
		isMounted: function() {
			return !1;
		},
		enqueueForceUpdate: function() {},
		enqueueReplaceState: function() {},
		enqueueSetState: function() {}
	};
	var assign = Object.assign;
	var emptyObject = {};
	function Component(props, context, updater) {
		this.props = props;
		this.context = context;
		this.refs = emptyObject;
		this.updater = updater || ReactNoopUpdateQueue;
	}
	Component.prototype.isReactComponent = {};
	Component.prototype.setState = function(partialState, callback) {
		if ("object" !== typeof partialState && "function" !== typeof partialState && null != partialState) throw Error("takes an object of state variables to update or a function which returns an object of state variables.");
		this.updater.enqueueSetState(this, partialState, callback, "setState");
	};
	Component.prototype.forceUpdate = function(callback) {
		this.updater.enqueueForceUpdate(this, callback, "forceUpdate");
	};
	function ComponentDummy() {}
	ComponentDummy.prototype = Component.prototype;
	function PureComponent(props, context, updater) {
		this.props = props;
		this.context = context;
		this.refs = emptyObject;
		this.updater = updater || ReactNoopUpdateQueue;
	}
	var pureComponentPrototype = PureComponent.prototype = new ComponentDummy();
	pureComponentPrototype.constructor = PureComponent;
	assign(pureComponentPrototype, Component.prototype);
	pureComponentPrototype.isPureReactComponent = !0;
	var isArrayImpl = Array.isArray;
	function noop() {}
	var ReactSharedInternals = {
		H: null,
		A: null,
		T: null,
		S: null
	};
	var hasOwnProperty = Object.prototype.hasOwnProperty;
	function ReactElement(type, key, props) {
		var refProp = props.ref;
		return {
			$$typeof: REACT_ELEMENT_TYPE,
			type,
			key,
			ref: void 0 !== refProp ? refProp : null,
			props
		};
	}
	function cloneAndReplaceKey(oldElement, newKey) {
		return ReactElement(oldElement.type, newKey, oldElement.props);
	}
	function isValidElement(object) {
		return "object" === typeof object && null !== object && object.$$typeof === REACT_ELEMENT_TYPE;
	}
	function escape(key) {
		var escaperLookup = {
			"=": "=0",
			":": "=2"
		};
		return "$" + key.replace(/[=:]/g, function(match) {
			return escaperLookup[match];
		});
	}
	var userProvidedKeyEscapeRegex = /\/+/g;
	function getElementKey(element, index) {
		return "object" === typeof element && null !== element && null != element.key ? escape("" + element.key) : index.toString(36);
	}
	function resolveThenable(thenable) {
		switch (thenable.status) {
			case "fulfilled": return thenable.value;
			case "rejected": throw thenable.reason;
			default: switch ("string" === typeof thenable.status ? thenable.then(noop, noop) : (thenable.status = "pending", thenable.then(function(fulfilledValue) {
				"pending" === thenable.status && (thenable.status = "fulfilled", thenable.value = fulfilledValue);
			}, function(error) {
				"pending" === thenable.status && (thenable.status = "rejected", thenable.reason = error);
			})), thenable.status) {
				case "fulfilled": return thenable.value;
				case "rejected": throw thenable.reason;
			}
		}
		throw thenable;
	}
	function mapIntoArray(children, array, escapedPrefix, nameSoFar, callback) {
		var type = typeof children;
		if ("undefined" === type || "boolean" === type) children = null;
		var invokeCallback = !1;
		if (null === children) invokeCallback = !0;
		else switch (type) {
			case "bigint":
			case "string":
			case "number":
				invokeCallback = !0;
				break;
			case "object": switch (children.$$typeof) {
				case REACT_ELEMENT_TYPE:
				case REACT_PORTAL_TYPE:
					invokeCallback = !0;
					break;
				case REACT_LAZY_TYPE: return invokeCallback = children._init, mapIntoArray(invokeCallback(children._payload), array, escapedPrefix, nameSoFar, callback);
			}
		}
		if (invokeCallback) return callback = callback(children), invokeCallback = "" === nameSoFar ? "." + getElementKey(children, 0) : nameSoFar, isArrayImpl(callback) ? (escapedPrefix = "", null != invokeCallback && (escapedPrefix = invokeCallback.replace(userProvidedKeyEscapeRegex, "$&/") + "/"), mapIntoArray(callback, array, escapedPrefix, "", function(c) {
			return c;
		})) : null != callback && (isValidElement(callback) && (callback = cloneAndReplaceKey(callback, escapedPrefix + (null == callback.key || children && children.key === callback.key ? "" : ("" + callback.key).replace(userProvidedKeyEscapeRegex, "$&/") + "/") + invokeCallback)), array.push(callback)), 1;
		invokeCallback = 0;
		var nextNamePrefix = "" === nameSoFar ? "." : nameSoFar + ":";
		if (isArrayImpl(children)) for (var i = 0; i < children.length; i++) nameSoFar = children[i], type = nextNamePrefix + getElementKey(nameSoFar, i), invokeCallback += mapIntoArray(nameSoFar, array, escapedPrefix, type, callback);
		else if (i = getIteratorFn(children), "function" === typeof i) for (children = i.call(children), i = 0; !(nameSoFar = children.next()).done;) nameSoFar = nameSoFar.value, type = nextNamePrefix + getElementKey(nameSoFar, i++), invokeCallback += mapIntoArray(nameSoFar, array, escapedPrefix, type, callback);
		else if ("object" === type) {
			if ("function" === typeof children.then) return mapIntoArray(resolveThenable(children), array, escapedPrefix, nameSoFar, callback);
			array = String(children);
			throw Error("Objects are not valid as a React child (found: " + ("[object Object]" === array ? "object with keys {" + Object.keys(children).join(", ") + "}" : array) + "). If you meant to render a collection of children, use an array instead.");
		}
		return invokeCallback;
	}
	function mapChildren(children, func, context) {
		if (null == children) return children;
		var result = [], count = 0;
		mapIntoArray(children, result, "", "", function(child) {
			return func.call(context, child, count++);
		});
		return result;
	}
	function lazyInitializer(payload) {
		if (-1 === payload._status) {
			var ctor = payload._result;
			ctor = ctor();
			ctor.then(function(moduleObject) {
				if (0 === payload._status || -1 === payload._status) payload._status = 1, payload._result = moduleObject;
			}, function(error) {
				if (0 === payload._status || -1 === payload._status) payload._status = 2, payload._result = error;
			});
			-1 === payload._status && (payload._status = 0, payload._result = ctor);
		}
		if (1 === payload._status) return payload._result.default;
		throw payload._result;
	}
	var reportGlobalError = "function" === typeof reportError ? reportError : function(error) {
		if ("object" === typeof window && "function" === typeof window.ErrorEvent) {
			var event = new window.ErrorEvent("error", {
				bubbles: !0,
				cancelable: !0,
				message: "object" === typeof error && null !== error && "string" === typeof error.message ? String(error.message) : String(error),
				error
			});
			if (!window.dispatchEvent(event)) return;
		} else if ("object" === typeof process && "function" === typeof process.emit) {
			process.emit("uncaughtException", error);
			return;
		}
		console.error(error);
	};
	var Children = {
		map: mapChildren,
		forEach: function(children, forEachFunc, forEachContext) {
			mapChildren(children, function() {
				forEachFunc.apply(this, arguments);
			}, forEachContext);
		},
		count: function(children) {
			var n = 0;
			mapChildren(children, function() {
				n++;
			});
			return n;
		},
		toArray: function(children) {
			return mapChildren(children, function(child) {
				return child;
			}) || [];
		},
		only: function(children) {
			if (!isValidElement(children)) throw Error("React.Children.only expected to receive a single React element child.");
			return children;
		}
	};
	exports.Activity = REACT_ACTIVITY_TYPE;
	exports.Children = Children;
	exports.Component = Component;
	exports.Fragment = REACT_FRAGMENT_TYPE;
	exports.Profiler = REACT_PROFILER_TYPE;
	exports.PureComponent = PureComponent;
	exports.StrictMode = REACT_STRICT_MODE_TYPE;
	exports.Suspense = REACT_SUSPENSE_TYPE;
	exports.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE = ReactSharedInternals;
	exports.__COMPILER_RUNTIME = {
		__proto__: null,
		c: function(size) {
			return ReactSharedInternals.H.useMemoCache(size);
		}
	};
	exports.cache = function(fn) {
		return function() {
			return fn.apply(null, arguments);
		};
	};
	exports.cacheSignal = function() {
		return null;
	};
	exports.cloneElement = function(element, config, children) {
		if (null === element || void 0 === element) throw Error("The argument must be a React element, but you passed " + element + ".");
		var props = assign({}, element.props), key = element.key;
		if (null != config) for (propName in void 0 !== config.key && (key = "" + config.key), config) !hasOwnProperty.call(config, propName) || "key" === propName || "__self" === propName || "__source" === propName || "ref" === propName && void 0 === config.ref || (props[propName] = config[propName]);
		var propName = arguments.length - 2;
		if (1 === propName) props.children = children;
		else if (1 < propName) {
			for (var childArray = Array(propName), i = 0; i < propName; i++) childArray[i] = arguments[i + 2];
			props.children = childArray;
		}
		return ReactElement(element.type, key, props);
	};
	exports.createContext = function(defaultValue) {
		defaultValue = {
			$$typeof: REACT_CONTEXT_TYPE,
			_currentValue: defaultValue,
			_currentValue2: defaultValue,
			_threadCount: 0,
			Provider: null,
			Consumer: null
		};
		defaultValue.Provider = defaultValue;
		defaultValue.Consumer = {
			$$typeof: REACT_CONSUMER_TYPE,
			_context: defaultValue
		};
		return defaultValue;
	};
	exports.createElement = function(type, config, children) {
		var propName, props = {}, key = null;
		if (null != config) for (propName in void 0 !== config.key && (key = "" + config.key), config) hasOwnProperty.call(config, propName) && "key" !== propName && "__self" !== propName && "__source" !== propName && (props[propName] = config[propName]);
		var childrenLength = arguments.length - 2;
		if (1 === childrenLength) props.children = children;
		else if (1 < childrenLength) {
			for (var childArray = Array(childrenLength), i = 0; i < childrenLength; i++) childArray[i] = arguments[i + 2];
			props.children = childArray;
		}
		if (type && type.defaultProps) for (propName in childrenLength = type.defaultProps, childrenLength) void 0 === props[propName] && (props[propName] = childrenLength[propName]);
		return ReactElement(type, key, props);
	};
	exports.createRef = function() {
		return { current: null };
	};
	exports.forwardRef = function(render) {
		return {
			$$typeof: REACT_FORWARD_REF_TYPE,
			render
		};
	};
	exports.isValidElement = isValidElement;
	exports.lazy = function(ctor) {
		return {
			$$typeof: REACT_LAZY_TYPE,
			_payload: {
				_status: -1,
				_result: ctor
			},
			_init: lazyInitializer
		};
	};
	exports.memo = function(type, compare) {
		return {
			$$typeof: REACT_MEMO_TYPE,
			type,
			compare: void 0 === compare ? null : compare
		};
	};
	exports.startTransition = function(scope) {
		var prevTransition = ReactSharedInternals.T, currentTransition = {};
		ReactSharedInternals.T = currentTransition;
		try {
			var returnValue = scope(), onStartTransitionFinish = ReactSharedInternals.S;
			null !== onStartTransitionFinish && onStartTransitionFinish(currentTransition, returnValue);
			"object" === typeof returnValue && null !== returnValue && "function" === typeof returnValue.then && returnValue.then(noop, reportGlobalError);
		} catch (error) {
			reportGlobalError(error);
		} finally {
			null !== prevTransition && null !== currentTransition.types && (prevTransition.types = currentTransition.types), ReactSharedInternals.T = prevTransition;
		}
	};
	exports.unstable_useCacheRefresh = function() {
		return ReactSharedInternals.H.useCacheRefresh();
	};
	exports.use = function(usable) {
		return ReactSharedInternals.H.use(usable);
	};
	exports.useActionState = function(action, initialState, permalink) {
		return ReactSharedInternals.H.useActionState(action, initialState, permalink);
	};
	exports.useCallback = function(callback, deps) {
		return ReactSharedInternals.H.useCallback(callback, deps);
	};
	exports.useContext = function(Context) {
		return ReactSharedInternals.H.useContext(Context);
	};
	exports.useDebugValue = function() {};
	exports.useDeferredValue = function(value, initialValue) {
		return ReactSharedInternals.H.useDeferredValue(value, initialValue);
	};
	exports.useEffect = function(create, deps) {
		return ReactSharedInternals.H.useEffect(create, deps);
	};
	exports.useEffectEvent = function(callback) {
		return ReactSharedInternals.H.useEffectEvent(callback);
	};
	exports.useId = function() {
		return ReactSharedInternals.H.useId();
	};
	exports.useImperativeHandle = function(ref, create, deps) {
		return ReactSharedInternals.H.useImperativeHandle(ref, create, deps);
	};
	exports.useInsertionEffect = function(create, deps) {
		return ReactSharedInternals.H.useInsertionEffect(create, deps);
	};
	exports.useLayoutEffect = function(create, deps) {
		return ReactSharedInternals.H.useLayoutEffect(create, deps);
	};
	exports.useMemo = function(create, deps) {
		return ReactSharedInternals.H.useMemo(create, deps);
	};
	exports.useOptimistic = function(passthrough, reducer) {
		return ReactSharedInternals.H.useOptimistic(passthrough, reducer);
	};
	exports.useReducer = function(reducer, initialArg, init) {
		return ReactSharedInternals.H.useReducer(reducer, initialArg, init);
	};
	exports.useRef = function(initialValue) {
		return ReactSharedInternals.H.useRef(initialValue);
	};
	exports.useState = function(initialState) {
		return ReactSharedInternals.H.useState(initialState);
	};
	exports.useSyncExternalStore = function(subscribe, getSnapshot, getServerSnapshot) {
		return ReactSharedInternals.H.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
	};
	exports.useTransition = function() {
		return ReactSharedInternals.H.useTransition();
	};
	exports.version = "19.2.8";
}));
//#endregion
//#region node_modules/.pnpm/react@19.2.8/node_modules/react/index.js
var require_react = /* @__PURE__ */ __commonJSMin(((exports, module) => {
	module.exports = require_react_production();
}));
//#endregion
//#region node_modules/.pnpm/react-dom@19.2.8_react@19.2.8/node_modules/react-dom/cjs/react-dom.production.js
/**
* @license React
* react-dom.production.js
*
* Copyright (c) Meta Platforms, Inc. and affiliates.
*
* This source code is licensed under the MIT license found in the
* LICENSE file in the root directory of this source tree.
*/
var require_react_dom_production = /* @__PURE__ */ __commonJSMin(((exports) => {
	var React = require_react();
	function formatProdErrorMessage(code) {
		var url = "https://react.dev/errors/" + code;
		if (1 < arguments.length) {
			url += "?args[]=" + encodeURIComponent(arguments[1]);
			for (var i = 2; i < arguments.length; i++) url += "&args[]=" + encodeURIComponent(arguments[i]);
		}
		return "Minified React error #" + code + "; visit " + url + " for the full message or use the non-minified dev environment for full errors and additional helpful warnings.";
	}
	function noop() {}
	var Internals = {
		d: {
			f: noop,
			r: function() {
				throw Error(formatProdErrorMessage(522));
			},
			D: noop,
			C: noop,
			L: noop,
			m: noop,
			X: noop,
			S: noop,
			M: noop
		},
		p: 0,
		findDOMNode: null
	};
	var REACT_PORTAL_TYPE = Symbol.for("react.portal");
	function createPortal$1(children, containerInfo, implementation) {
		var key = 3 < arguments.length && void 0 !== arguments[3] ? arguments[3] : null;
		return {
			$$typeof: REACT_PORTAL_TYPE,
			key: null == key ? null : "" + key,
			children,
			containerInfo,
			implementation
		};
	}
	var ReactSharedInternals = React.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;
	function getCrossOriginStringAs(as, input) {
		if ("font" === as) return "";
		if ("string" === typeof input) return "use-credentials" === input ? input : "";
	}
	exports.__DOM_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE = Internals;
	exports.createPortal = function(children, container) {
		var key = 2 < arguments.length && void 0 !== arguments[2] ? arguments[2] : null;
		if (!container || 1 !== container.nodeType && 9 !== container.nodeType && 11 !== container.nodeType) throw Error(formatProdErrorMessage(299));
		return createPortal$1(children, container, null, key);
	};
	exports.flushSync = function(fn) {
		var previousTransition = ReactSharedInternals.T, previousUpdatePriority = Internals.p;
		try {
			if (ReactSharedInternals.T = null, Internals.p = 2, fn) return fn();
		} finally {
			ReactSharedInternals.T = previousTransition, Internals.p = previousUpdatePriority, Internals.d.f();
		}
	};
	exports.preconnect = function(href, options) {
		"string" === typeof href && (options ? (options = options.crossOrigin, options = "string" === typeof options ? "use-credentials" === options ? options : "" : void 0) : options = null, Internals.d.C(href, options));
	};
	exports.prefetchDNS = function(href) {
		"string" === typeof href && Internals.d.D(href);
	};
	exports.preinit = function(href, options) {
		if ("string" === typeof href && options && "string" === typeof options.as) {
			var as = options.as, crossOrigin = getCrossOriginStringAs(as, options.crossOrigin), integrity = "string" === typeof options.integrity ? options.integrity : void 0, fetchPriority = "string" === typeof options.fetchPriority ? options.fetchPriority : void 0;
			"style" === as ? Internals.d.S(href, "string" === typeof options.precedence ? options.precedence : void 0, {
				crossOrigin,
				integrity,
				fetchPriority
			}) : "script" === as && Internals.d.X(href, {
				crossOrigin,
				integrity,
				fetchPriority,
				nonce: "string" === typeof options.nonce ? options.nonce : void 0
			});
		}
	};
	exports.preinitModule = function(href, options) {
		if ("string" === typeof href) if ("object" === typeof options && null !== options) {
			if (null == options.as || "script" === options.as) {
				var crossOrigin = getCrossOriginStringAs(options.as, options.crossOrigin);
				Internals.d.M(href, {
					crossOrigin,
					integrity: "string" === typeof options.integrity ? options.integrity : void 0,
					nonce: "string" === typeof options.nonce ? options.nonce : void 0
				});
			}
		} else options ?? Internals.d.M(href);
	};
	exports.preload = function(href, options) {
		if ("string" === typeof href && "object" === typeof options && null !== options && "string" === typeof options.as) {
			var as = options.as, crossOrigin = getCrossOriginStringAs(as, options.crossOrigin);
			Internals.d.L(href, as, {
				crossOrigin,
				integrity: "string" === typeof options.integrity ? options.integrity : void 0,
				nonce: "string" === typeof options.nonce ? options.nonce : void 0,
				type: "string" === typeof options.type ? options.type : void 0,
				fetchPriority: "string" === typeof options.fetchPriority ? options.fetchPriority : void 0,
				referrerPolicy: "string" === typeof options.referrerPolicy ? options.referrerPolicy : void 0,
				imageSrcSet: "string" === typeof options.imageSrcSet ? options.imageSrcSet : void 0,
				imageSizes: "string" === typeof options.imageSizes ? options.imageSizes : void 0,
				media: "string" === typeof options.media ? options.media : void 0
			});
		}
	};
	exports.preloadModule = function(href, options) {
		if ("string" === typeof href) if (options) {
			var crossOrigin = getCrossOriginStringAs(options.as, options.crossOrigin);
			Internals.d.m(href, {
				as: "string" === typeof options.as && "script" !== options.as ? options.as : void 0,
				crossOrigin,
				integrity: "string" === typeof options.integrity ? options.integrity : void 0
			});
		} else Internals.d.m(href);
	};
	exports.requestFormReset = function(form) {
		Internals.d.r(form);
	};
	exports.unstable_batchedUpdates = function(fn, a) {
		return fn(a);
	};
	exports.useFormState = function(action, initialState, permalink) {
		return ReactSharedInternals.H.useFormState(action, initialState, permalink);
	};
	exports.useFormStatus = function() {
		return ReactSharedInternals.H.useHostTransitionStatus();
	};
	exports.version = "19.2.8";
}));
//#endregion
//#region node_modules/.pnpm/react-dom@19.2.8_react@19.2.8/node_modules/react-dom/index.js
var require_react_dom = /* @__PURE__ */ __commonJSMin(((exports, module) => {
	function checkDCE() {
		if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ === "undefined" || typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE !== "function") return;
		try {
			__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(checkDCE);
		} catch (err) {
			console.error(err);
		}
	}
	checkDCE();
	module.exports = require_react_dom_production();
}));
//#endregion
//#region node_modules/.pnpm/lucide-react@1.40.0_react@19.2.8/node_modules/lucide-react/dist/esm/shared/src/utils/mergeClasses.mjs
var import_react = require_react();
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var mergeClasses = (...classes) => classes.filter((className, index, array) => {
	return Boolean(className) && className.trim() !== "" && array.indexOf(className) === index;
}).join(" ").trim();
//#endregion
//#region node_modules/.pnpm/lucide-react@1.40.0_react@19.2.8/node_modules/lucide-react/dist/esm/shared/src/utils/toKebabCase.mjs
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var toKebabCase = (string) => string.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
//#endregion
//#region node_modules/.pnpm/lucide-react@1.40.0_react@19.2.8/node_modules/lucide-react/dist/esm/shared/src/utils/toCamelCase.mjs
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var toCamelCase = (string) => string.replace(/^([A-Z])|[\s-_]+(\w)/g, (match, p1, p2) => p2 ? p2.toUpperCase() : p1.toLowerCase());
//#endregion
//#region node_modules/.pnpm/lucide-react@1.40.0_react@19.2.8/node_modules/lucide-react/dist/esm/shared/src/utils/toPascalCase.mjs
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var toPascalCase = (string) => {
	const camelCase = toCamelCase(string);
	return camelCase.charAt(0).toUpperCase() + camelCase.slice(1);
};
//#endregion
//#region node_modules/.pnpm/lucide-react@1.40.0_react@19.2.8/node_modules/lucide-react/dist/esm/defaultAttributes.mjs
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var defaultAttributes = {
	xmlns: "http://www.w3.org/2000/svg",
	width: 24,
	height: 24,
	viewBox: "0 0 24 24",
	fill: "none",
	stroke: "currentColor",
	strokeWidth: 2,
	strokeLinecap: "round",
	strokeLinejoin: "round"
};
//#endregion
//#region node_modules/.pnpm/lucide-react@1.40.0_react@19.2.8/node_modules/lucide-react/dist/esm/shared/src/utils/hasA11yProp.mjs
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var hasA11yProp = (props) => {
	for (const prop in props) if (prop.startsWith("aria-") || prop === "role" || prop === "title") return true;
	return false;
};
//#endregion
//#region node_modules/.pnpm/lucide-react@1.40.0_react@19.2.8/node_modules/lucide-react/dist/esm/context.mjs
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var LucideContext = (0, import_react.createContext)({});
var useLucideContext = () => (0, import_react.useContext)(LucideContext);
//#endregion
//#region node_modules/.pnpm/lucide-react@1.40.0_react@19.2.8/node_modules/lucide-react/dist/esm/Icon.mjs
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Icon$1 = (0, import_react.forwardRef)(({ color, size, strokeWidth, absoluteStrokeWidth, className = "", children, iconNode, ...rest }, ref) => {
	const { size: contextSize = 24, strokeWidth: contextStrokeWidth = 2, absoluteStrokeWidth: contextAbsoluteStrokeWidth = false, color: contextColor = "currentColor", className: contextClass = "" } = useLucideContext() ?? {};
	const calculatedStrokeWidth = absoluteStrokeWidth ?? contextAbsoluteStrokeWidth ? Number(strokeWidth ?? contextStrokeWidth) * 24 / Number(size ?? contextSize) : strokeWidth ?? contextStrokeWidth;
	return (0, import_react.createElement)("svg", {
		ref,
		...defaultAttributes,
		width: size ?? contextSize ?? defaultAttributes.width,
		height: size ?? contextSize ?? defaultAttributes.height,
		stroke: color ?? contextColor,
		strokeWidth: calculatedStrokeWidth,
		className: mergeClasses("lucide", contextClass, className),
		...!children && !hasA11yProp(rest) && { "aria-hidden": "true" },
		...rest
	}, [...iconNode.map(([tag, attrs]) => (0, import_react.createElement)(tag, attrs)), ...Array.isArray(children) ? children : [children]]);
});
//#endregion
//#region node_modules/.pnpm/lucide-react@1.40.0_react@19.2.8/node_modules/lucide-react/dist/esm/createLucideIcon.mjs
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var createLucideIcon = (iconName, iconNode) => {
	const Component = (0, import_react.forwardRef)(({ className, ...props }, ref) => (0, import_react.createElement)(Icon$1, {
		ref,
		iconNode,
		className: mergeClasses(`lucide-${toKebabCase(toPascalCase(iconName))}`, `lucide-${iconName}`, className),
		...props
	}));
	Component.displayName = toPascalCase(iconName);
	return Component;
};
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var ChartColumn = createLucideIcon("chart-column", [
	["path", {
		d: "M3 3v16a2 2 0 0 0 2 2h16",
		key: "c24i48"
	}],
	["path", {
		d: "M18 17V9",
		key: "2bz60n"
	}],
	["path", {
		d: "M13 17V5",
		key: "1frdt8"
	}],
	["path", {
		d: "M8 17v-3",
		key: "17ska0"
	}]
]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Check = createLucideIcon("check", [["path", {
	d: "M20 6 9 17l-5-5",
	key: "1gmf2c"
}]]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var ChevronDown = createLucideIcon("chevron-down", [["path", {
	d: "m6 9 6 6 6-6",
	key: "qrunsl"
}]]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var ChevronLeft = createLucideIcon("chevron-left", [["path", {
	d: "m15 18-6-6 6-6",
	key: "1wnfg3"
}]]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var ChevronRight = createLucideIcon("chevron-right", [["path", {
	d: "m9 18 6-6-6-6",
	key: "mthhwq"
}]]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Download = createLucideIcon("download", [
	["path", {
		d: "M12 15V3",
		key: "m9g1x1"
	}],
	["path", {
		d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4",
		key: "ih7n3h"
	}],
	["path", {
		d: "m7 10 5 5 5-5",
		key: "brsn70"
	}]
]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var EllipsisVertical = createLucideIcon("ellipsis-vertical", [
	["circle", {
		cx: "12",
		cy: "12",
		r: "1",
		key: "41hilf"
	}],
	["circle", {
		cx: "12",
		cy: "5",
		r: "1",
		key: "gxeob9"
	}],
	["circle", {
		cx: "12",
		cy: "19",
		r: "1",
		key: "lyex9k"
	}]
]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var House = createLucideIcon("house", [["path", {
	d: "M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8",
	key: "5wwlr5"
}], ["path", {
	d: "M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
	key: "r6nss1"
}]]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Info = createLucideIcon("info", [
	["circle", {
		cx: "12",
		cy: "12",
		r: "10",
		key: "1mglay"
	}],
	["path", {
		d: "M12 16v-4",
		key: "1dtifu"
	}],
	["path", {
		d: "M12 8h.01",
		key: "e9boi3"
	}]
]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Keyboard = createLucideIcon("keyboard", [
	["path", {
		d: "M10 8h.01",
		key: "1r9ogq"
	}],
	["path", {
		d: "M12 12h.01",
		key: "1mp3jc"
	}],
	["path", {
		d: "M14 8h.01",
		key: "1primd"
	}],
	["path", {
		d: "M16 12h.01",
		key: "1l6xoz"
	}],
	["path", {
		d: "M18 8h.01",
		key: "emo2bl"
	}],
	["path", {
		d: "M6 8h.01",
		key: "x9i8wu"
	}],
	["path", {
		d: "M7 16h10",
		key: "wp8him"
	}],
	["path", {
		d: "M8 12h.01",
		key: "czm47f"
	}],
	["rect", {
		width: "20",
		height: "16",
		x: "2",
		y: "4",
		rx: "2",
		key: "18n3k1"
	}]
]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var LayoutGrid = createLucideIcon("layout-grid", [
	["rect", {
		width: "7",
		height: "7",
		x: "3",
		y: "3",
		rx: "1",
		key: "1g98yp"
	}],
	["rect", {
		width: "7",
		height: "7",
		x: "14",
		y: "3",
		rx: "1",
		key: "6d4xhi"
	}],
	["rect", {
		width: "7",
		height: "7",
		x: "14",
		y: "14",
		rx: "1",
		key: "nxv5o0"
	}],
	["rect", {
		width: "7",
		height: "7",
		x: "3",
		y: "14",
		rx: "1",
		key: "1bb6yr"
	}]
]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Monitor = createLucideIcon("monitor", [
	["rect", {
		width: "20",
		height: "14",
		x: "2",
		y: "3",
		rx: "2",
		key: "48i651"
	}],
	["line", {
		x1: "8",
		x2: "16",
		y1: "21",
		y2: "21",
		key: "1svkeh"
	}],
	["line", {
		x1: "12",
		x2: "12",
		y1: "17",
		y2: "21",
		key: "vw1qmm"
	}]
]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Moon = createLucideIcon("moon", [["path", {
	d: "M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401",
	key: "kfwtm"
}]]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Pause = createLucideIcon("pause", [["rect", {
	x: "14",
	y: "3",
	width: "5",
	height: "18",
	rx: "1",
	key: "kaeet6"
}], ["rect", {
	x: "5",
	y: "3",
	width: "5",
	height: "18",
	rx: "1",
	key: "1wsw3u"
}]]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Search = createLucideIcon("search", [["path", {
	d: "m21 21-4.34-4.34",
	key: "14j7rj"
}], ["circle", {
	cx: "11",
	cy: "11",
	r: "8",
	key: "4ej97u"
}]]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Settings = createLucideIcon("settings", [["path", {
	d: "M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915",
	key: "1i5ecw"
}], ["circle", {
	cx: "12",
	cy: "12",
	r: "3",
	key: "1v7zrd"
}]]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var Sun = createLucideIcon("sun", [
	["circle", {
		cx: "12",
		cy: "12",
		r: "4",
		key: "4exip2"
	}],
	["path", {
		d: "M12 2v2",
		key: "tus03m"
	}],
	["path", {
		d: "M12 20v2",
		key: "1lh1kg"
	}],
	["path", {
		d: "m4.93 4.93 1.41 1.41",
		key: "149t6j"
	}],
	["path", {
		d: "m17.66 17.66 1.41 1.41",
		key: "ptbguv"
	}],
	["path", {
		d: "M2 12h2",
		key: "1t8f8n"
	}],
	["path", {
		d: "M20 12h2",
		key: "1q8mjw"
	}],
	["path", {
		d: "m6.34 17.66-1.41 1.41",
		key: "1m8zz5"
	}],
	["path", {
		d: "m19.07 4.93-1.41 1.41",
		key: "1shlcs"
	}]
]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var TriangleAlert = createLucideIcon("triangle-alert", [
	["path", {
		d: "m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3",
		key: "wmoenq"
	}],
	["path", {
		d: "M12 9v4",
		key: "juzpu7"
	}],
	["path", {
		d: "M12 17h.01",
		key: "p32p05"
	}]
]);
/**
* @license lucide-react v1.40.0 - ISC
*
* This source code is licensed under the ISC license.
* See the LICENSE file in the root directory of this source tree.
*/
var X = createLucideIcon("x", [["path", {
	d: "M18 6 6 18",
	key: "1bl5f8"
}], ["path", {
	d: "m6 6 12 12",
	key: "d8bk6v"
}]]);
//#endregion
//#region node_modules/.pnpm/react@19.2.8/node_modules/react/cjs/react-jsx-runtime.production.js
/**
* @license React
* react-jsx-runtime.production.js
*
* Copyright (c) Meta Platforms, Inc. and affiliates.
*
* This source code is licensed under the MIT license found in the
* LICENSE file in the root directory of this source tree.
*/
var require_react_jsx_runtime_production = /* @__PURE__ */ __commonJSMin(((exports) => {
	var REACT_ELEMENT_TYPE = Symbol.for("react.transitional.element");
	var REACT_FRAGMENT_TYPE = Symbol.for("react.fragment");
	function jsxProd(type, config, maybeKey) {
		var key = null;
		void 0 !== maybeKey && (key = "" + maybeKey);
		void 0 !== config.key && (key = "" + config.key);
		if ("key" in config) {
			maybeKey = {};
			for (var propName in config) "key" !== propName && (maybeKey[propName] = config[propName]);
		} else maybeKey = config;
		config = maybeKey.ref;
		return {
			$$typeof: REACT_ELEMENT_TYPE,
			type,
			key,
			ref: void 0 !== config ? config : null,
			props: maybeKey
		};
	}
	exports.Fragment = REACT_FRAGMENT_TYPE;
	exports.jsx = jsxProd;
	exports.jsxs = jsxProd;
}));
//#endregion
//#region node_modules/.pnpm/react@19.2.8/node_modules/react/jsx-runtime.js
var require_jsx_runtime = /* @__PURE__ */ __commonJSMin(((exports, module) => {
	module.exports = require_react_jsx_runtime_production();
}));
//#endregion
//#region frontend/src/components/Icon.tsx
var import_jsx_runtime = require_jsx_runtime();
/**
* 我们的 id → lucide 组件。
*
* **保留这张映射表而不是直接用 lucide 的名字**：id 说的是"它在界面上是什么角色"，glyph 说
* 的是"它长什么样"，而"为什么挑这个 glyph"需要一个落脚处。调用点写 `<Icon name="gear" />`
* 也比 `<Settings />` 更贴近它在界面上的角色。
*
* 主题那三档是这张表最值钱的一条注记：`theme-system` / `theme-light` / `theme-dark` 分别是
* 显示器 / 太阳 / 月亮，因为主题现在是一张三行的列表（ThemeMenu.tsx），每一行都得自己说清
* 是哪一档。它原先是一个三态循环钮，那时只有一个图标位，用的是不暗示态数的 `Contrast`
* ——日月会让人以为只有两态。
*/
var ICONS = {
	gear: Settings,
	"theme-system": Monitor,
	"theme-light": Sun,
	"theme-dark": Moon,
	left: ChevronLeft,
	right: ChevronRight,
	down: ChevronDown,
	info: Info,
	keyboard: Keyboard,
	apps: LayoutGrid,
	insights: ChartColumn,
	overview: House,
	download: Download,
	pause: Pause,
	more: EllipsisVertical,
	search: Search,
	check: Check,
	close: X,
	warning: TriangleAlert
};
Object.keys(ICONS);
function Icon({ name, size, className = "icon", title }) {
	const Glyph = ICONS[name];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Glyph, {
		className,
		"aria-hidden": title ? void 0 : true,
		"aria-label": title,
		role: title ? "img" : void 0,
		focusable: "false",
		style: size ? {
			width: size,
			height: size
		} : void 0
	});
}
//#endregion
//#region frontend/src/core/bus.ts
var topics = /* @__PURE__ */ new Map();
/** @returns 注销函数 */
function on(topic, handler) {
	let handlers = topics.get(topic);
	if (!handlers) {
		handlers = /* @__PURE__ */ new Set();
		topics.set(topic, handlers);
	}
	handlers.add(handler);
	return () => off(topic, handler);
}
function off(topic, handler) {
	topics.get(topic)?.delete(handler);
}
function emit(topic, payload) {
	const handlers = topics.get(topic);
	if (!handlers) return;
	for (const handler of [...handlers]) try {
		handler(payload, topic);
	} catch (error) {
		console.error(`总线处理器失败：${topic}`, error);
	}
}
//#endregion
//#region \0@oxc-project+runtime@0.148.0/helpers/esm/typeof.js
function _typeof(o) {
	"@babel/helpers - typeof";
	return _typeof = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function(o) {
		return typeof o;
	} : function(o) {
		return o && "function" == typeof Symbol && o.constructor === Symbol && o !== Symbol.prototype ? "symbol" : typeof o;
	}, _typeof(o);
}
//#endregion
//#region \0@oxc-project+runtime@0.148.0/helpers/esm/toPrimitive.js
function toPrimitive(t, r) {
	if ("object" != _typeof(t) || !t) return t;
	var e = t[Symbol.toPrimitive];
	if (void 0 !== e) {
		var i = e.call(t, r || "default");
		if ("object" != _typeof(i)) return i;
		throw new TypeError("@@toPrimitive must return a primitive value.");
	}
	return ("string" === r ? String : Number)(t);
}
//#endregion
//#region \0@oxc-project+runtime@0.148.0/helpers/esm/toPropertyKey.js
function toPropertyKey(t) {
	var i = toPrimitive(t, "string");
	return "symbol" == _typeof(i) ? i : i + "";
}
//#endregion
//#region \0@oxc-project+runtime@0.148.0/helpers/esm/defineProperty.js
function _defineProperty(e, r, t) {
	return (r = toPropertyKey(r)) in e ? Object.defineProperty(e, r, {
		value: t,
		enumerable: !0,
		configurable: !0,
		writable: !0
	}) : e[r] = t, e;
}
//#endregion
//#region frontend/src/core/api.ts
var BASE = "/api/v1";
var TOKEN_HEADER = "X-OmniSight-Token";
var TOKEN_KEY = "omnisight.token";
var inflight = /* @__PURE__ */ new Map();
var cache = /* @__PURE__ */ new Map();
var token = "";
var ApiError = class extends Error {
	/**
	* @param body 响应体里的 `error` 段
	*/
	constructor(body, status) {
		super(body?.message || `HTTP ${status}`);
		_defineProperty(this, "code", void 0);
		_defineProperty(this, "field", void 0);
		_defineProperty(this, "status", void 0);
		this.name = "ApiError";
		this.code = body?.code || "http_error";
		this.field = body?.field || null;
		this.status = status;
	}
};
/**
* 令牌只经 URL 交接一次，随后存 sessionStorage 并从地址栏抹掉（08 文档 §3.2b）。
* @param fromPage 模板注入的 data-token
*/
function adoptToken(fromPage) {
	if (fromPage) {
		token = fromPage;
		try {
			sessionStorage.setItem(TOKEN_KEY, fromPage);
		} catch {}
		history.replaceState(null, "", window.location.pathname + window.location.hash);
		return token;
	}
	try {
		token = sessionStorage.getItem(TOKEN_KEY) || "";
	} catch {
		token = "";
	}
	return token;
}
/**
* 把 catch 到的东西说成人话。写操作失败后进 toast 的文案都经这里。
*
* 原先每个调用点各写一遍 `error.field ? ... : error.message`，而 `error` 在类型上
* 是 `unknown`——非 ApiError 的抛出（网络层的 TypeError）会让 toast 显示
* `undefined`。这里兜住那一种。
*/
function messageOf(error, fallback = "操作失败") {
	if (error instanceof ApiError) return error.field ? `${error.field}：${error.message}` : error.message;
	if (error instanceof Error && error.message) return error.message;
	return fallback;
}
/** SSE 用得到：EventSource 无法设置请求头，只能把令牌放查询串。 */
function tokenParam() {
	return token;
}
/** @param path `/api/v1` 之后的部分 */
function buildUrl(path, params = {}) {
	const url = new URL(BASE + path, window.location.origin);
	for (const [key, value] of Object.entries(params)) {
		if (value === null || value === void 0 || value === "") continue;
		url.searchParams.set(key, String(value));
	}
	return url.pathname + url.search;
}
/** @returns 未经校验的 JSON；204 与 abort 给 null */
async function get(path, params = {}, options = {}) {
	const { signal, maxAge = 0 } = options;
	const url = buildUrl(path, params);
	const cached = cache.get(url);
	if (cached && maxAge && Date.now() - cached.at < maxAge) return cached.data;
	const pending = inflight.get(url);
	if (pending) return pending;
	const headers = { [TOKEN_HEADER]: token };
	if (cached?.etag) headers["If-None-Match"] = cached.etag;
	const promise = fetch(url, {
		signal,
		headers,
		credentials: "omit"
	}).then(async (response) => {
		if (response.status === 304 && cached) return cached.data;
		if (response.status === 204) return null;
		const body = await response.json().catch(() => null);
		if (!response.ok) throw new ApiError(body?.error, response.status);
		cache.set(url, {
			data: body,
			at: Date.now(),
			etag: response.headers.get("ETag")
		});
		return body;
	}).finally(() => inflight.delete(url));
	inflight.set(url, promise);
	return promise;
}
async function write(method, path, body) {
	const response = await fetch(buildUrl(path), {
		method,
		credentials: "omit",
		headers: {
			[TOKEN_HEADER]: token,
			"Content-Type": "application/json"
		},
		body: body === void 0 ? void 0 : JSON.stringify(body)
	});
	const payload = await response.json().catch(() => null);
	if (!response.ok) throw new ApiError(payload?.error, response.status);
	invalidate();
	emit("data:changed", { path });
	return payload;
}
var patch = (path, body) => write("PATCH", path, body);
var post = (path, body) => write("POST", path, body);
var del = (path, body) => write("DELETE", path, body);
/**
* 清缓存。传前缀只清匹配的（周期变化时不必丢弃布局与设置）。
*/
function invalidate(prefix = "") {
	if (!prefix) {
		cache.clear();
		return;
	}
	for (const key of [...cache.keys()]) if (key.startsWith(BASE + prefix)) cache.delete(key);
}
/**
* 图标 URL 后端已给（`icon_url`），这里只补令牌——<img> 发不出自定义头。
*/
function assetUrl(path) {
	if (!path) return "";
	return `${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
}
//#endregion
//#region frontend/src/components/toast.tsx
var LIFETIME_MS = 4200;
var items = [];
var nextId = 1;
var listeners$2 = /* @__PURE__ */ new Set();
function publish$1(next) {
	items = next;
	for (const listener of [...listeners$2]) listener();
}
function toast(message, kind = "info") {
	const id = nextId++;
	publish$1([...items, {
		id,
		message,
		kind
	}]);
	window.setTimeout(() => publish$1(items.filter((item) => item.id !== id)), LIFETIME_MS);
}
var ok = (message) => toast(message, "ok");
var fail = (message) => toast(message, "error");
/** 挂在模板的 `#toasts` 里（它带着 aria-live="polite"）。 */
function ToastHost() {
	const current = (0, import_react.useSyncExternalStore)((onChange) => {
		listeners$2.add(onChange);
		return () => listeners$2.delete(onChange);
	}, () => items);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_jsx_runtime.Fragment, { children: current.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "toast",
		"data-kind": item.kind,
		role: item.kind === "error" ? "alert" : "status",
		children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
			className: "toast__dot",
			"aria-hidden": "true"
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: item.message })]
	}, item.id)) });
}
//#endregion
//#region frontend/src/core/store.ts
var state$1 = {
	route: "overview",
	period: {
		range: "day",
		date: null,
		start: null,
		end: null
	},
	metric: "press_count",
	scopeAppId: null,
	appsGroup: "recent",
	selectedAppId: null,
	selectedKeyId: null,
	theme: "system",
	heat: "blue",
	prefs: {
		weekStartsOn: 0,
		defaultRange: "day",
		keyboardLayout: "auto",
		titlesRecorded: false,
		settingsSurface: "drawer"
	},
	settings: null,
	status: null,
	capabilities: null,
	degraded: [],
	layout: null,
	periodMeta: null,
	coverage: null,
	live: {
		connected: false,
		mode: "offline",
		currentApp: null,
		counters: null
	},
	data: {},
	loading: {},
	errors: {}
};
var listeners$1 = /* @__PURE__ */ new Map();
function getState() {
	return state$1;
}
/**
* 写一个切片。对象切片按浅合并，其余整体替换。
* @returns 是否真的变了（无变化不通知订阅者）
*/
function setState(slice, patch) {
	const previous = state$1[slice];
	let next;
	if (Array.isArray(patch) || patch === null || typeof patch !== "object") next = patch;
	else next = {
		...previous,
		...patch
	};
	if (equal(previous, next)) return false;
	state$1[slice] = next;
	notify(slice);
	return true;
}
/**
* 强制替换（用于 data/loading/errors 这类以 key 为单位的映射）。
*
* 写入侧刻意收得松（unknown）：精度要在**读取侧**——视图读 state.data.appsPeriod
* 时必须是 UsagePeriodResponse | undefined。写入侧唯一的调用者是 core/loader.ts，
* 它在那里做一次"JSON 到声明类型"的断言，而那次断言由契约测试兜着
* （tests/integration/test_frontend_contract.py）。
*/
function setEntry(slice, key, value) {
	const bag = state$1[slice];
	if (equal(bag[key], value)) return false;
	state$1[slice] = {
		...bag,
		[key]: value
	};
	notify(slice);
	return true;
}
/** @returns 注销函数 */
function subscribe(slice, handler) {
	let handlers = listeners$1.get(slice);
	if (!handlers) {
		handlers = /* @__PURE__ */ new Set();
		listeners$1.set(slice, handlers);
	}
	handlers.add(handler);
	return () => {
		handlers?.delete(handler);
	};
}
function notify(slice) {
	const handlers = listeners$1.get(slice);
	if (!handlers) return;
	for (const handler of [...handlers]) try {
		handler(state$1[slice], slice);
	} catch (error) {
		console.error(`订阅者失败：${slice}`, error);
	}
}
/** 浅比较。数据是"整块替换"的接口响应，深比较不划算（07 文档 §4.1）。 */
function equal(a, b) {
	if (a === b) return true;
	if (a === null || b === null || a === void 0 || b === void 0) return false;
	if (typeof a !== "object" || typeof b !== "object") return false;
	if (Array.isArray(a) !== Array.isArray(b)) return false;
	const left = a;
	const right = b;
	const keysA = Object.keys(left);
	const keysB = Object.keys(right);
	if (keysA.length !== keysB.length) return false;
	return keysA.every((key) => left[key] === right[key]);
}
//#endregion
//#region frontend/src/core/useStore.ts
/**
* 订阅一个切片。切片没变就不重渲染——setState 里的 shallowEqual 已经拦住无变化写入，
* 因此这里不需要再比一次。
*/
function useSlice(slice) {
	return (0, import_react.useSyncExternalStore)((onChange) => subscribe(slice, onChange), () => getState()[slice]);
}
/**
* 取数状态：data / loading / errors 三个切片按同一个 key 索引。
*
* 这是视图里最常见的读法，收在这里免得每个视图各写三次 useSlice。
*/
function useResource(key) {
	return {
		data: useSlice("data")[key],
		loading: Boolean(useSlice("loading")[key]),
		error: useSlice("errors")[key]
	};
}
//#endregion
//#region frontend/src/domain/format.ts
/** 人类可读时长。参数是秒。 */
function formatDuration(seconds) {
	const value = Number(seconds) || 0;
	if (value <= 0) return "0秒";
	if (value < 60) return `${Math.trunc(value)}秒`;
	const minutes = Math.trunc(value / 60);
	if (minutes < 60) return `${minutes}分钟`;
	const hours = Math.trunc(minutes / 60);
	const rest = minutes % 60;
	return rest === 0 ? `${hours}小时` : `${hours}小时${rest}分钟`;
}
/** 紧凑时长，图表轴与窄列用。7h33m 而不是"7小时33分钟"。 */
function formatDurationShort(seconds) {
	const value = Number(seconds) || 0;
	if (value <= 0) return "0";
	if (value < 60) return `${Math.trunc(value)}s`;
	const minutes = Math.trunc(value / 60);
	if (minutes < 60) return `${minutes}m`;
	const hours = Math.trunc(minutes / 60);
	const rest = minutes % 60;
	return rest === 0 ? `${hours}h` : `${hours}h${rest}m`;
}
/** 千分位。按键数动辄六位，不分组读不出量级。 */
function formatCount(value) {
	return Math.trunc(Number(value) || 0).toLocaleString("zh-CN");
}
function formatMs(ms) {
	const value = Number(ms) || 0;
	if (value < 1e3) return `${value.toFixed(value < 10 ? 1 : 0)}ms`;
	return `${(value / 1e3).toFixed(2)}s`;
}
function formatPercent(value, digits = 1) {
	return `${(Number(value) || 0).toFixed(digits)}%`;
}
/**
* ISO 时间戳 -> `M/D HH:MM`。"最近用过"这类副行要日期也要钟点：只给钟点的话
* 昨天 18:32 与今天 18:32 长得一样。
*/
function formatDayTime(iso) {
	if (!iso) return "";
	const value = new Date(iso);
	if (Number.isNaN(value.getTime())) return "";
	return `${value.getMonth() + 1}/${value.getDate()} ${pad(value.getHours())}:${pad(value.getMinutes())}`;
}
/** ISO 时间戳 -> `HH:MM`。后端给的是带时区偏移的字符串，Date 能正确解析。 */
function formatClock(iso) {
	if (!iso) return "";
	const date = new Date(iso);
	if (Number.isNaN(date.getTime())) return "";
	return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
function pad(value) {
	return String(value).padStart(2, "0");
}
/** 首字母色块用（无图标时）。取第一个字符，中文与 emoji 都能正确取到。 */
function initialOf(name) {
	const text = String(name || "").trim();
	if (!text) return "?";
	return [...text][0].toUpperCase();
}
//#endregion
//#region frontend/src/components/tooltip.tsx
var CLOSED = {
	open: false,
	rows: [],
	x: 0,
	y: 0
};
var state = CLOSED;
var listeners = /* @__PURE__ */ new Set();
function publish(next) {
	state = next;
	for (const listener of [...listeners]) listener();
}
function show(options) {
	publish({
		...options,
		rows: options.rows || [],
		open: true
	});
}
function hide() {
	if (state.open) publish(CLOSED);
}
function TooltipHost() {
	const current = (0, import_react.useSyncExternalStore)((onChange) => {
		listeners.add(onChange);
		return () => listeners.delete(onChange);
	}, () => state);
	const node = (0, import_react.useRef)(null);
	(0, import_react.useLayoutEffect)(() => {
		const tip = node.current;
		if (!tip || !current.open) return;
		const rect = tip.getBoundingClientRect();
		const margin = 12;
		let left = current.x + margin;
		let top = current.y + margin;
		if (left + rect.width > window.innerWidth - margin) left = current.x - rect.width - margin;
		if (top + rect.height > window.innerHeight - margin) top = current.y - rect.height - margin;
		tip.style.left = `${Math.max(margin, left)}px`;
		tip.style.top = `${Math.max(margin, top)}px`;
	}, [current]);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		ref: node,
		className: "tooltip",
		role: "tooltip",
		"aria-hidden": current.open ? void 0 : "true",
		"data-open": current.open ? "true" : "false",
		children: [
			current.title ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "tooltip__title",
				children: current.title
			}) : null,
			current.rows.map(([label, value]) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "tooltip__row",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: label }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: String(value) })]
			}, label)),
			current.note ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "tooltip__note",
				children: current.note
			}) : null
		]
	});
}
//#endregion
//#region frontend/src/core/theme.ts
var THEME_KEY = "omnisight.theme";
var HEAT_KEY = "omnisight.heat";
var THEMES = [
	"system",
	"light",
	"dark"
];
/** 导出给 ThemeMenu：store 里的 theme 切片是 string（它还要承接服务端 `ui.theme` 的值）。 */
function isTheme(value) {
	return THEMES.includes(value);
}
function apply(theme, heat) {
	const root = document.documentElement;
	if (theme === "light" || theme === "dark") root.dataset.theme = theme;
	else delete root.dataset.theme;
	if (heat === "warm") root.dataset.heat = "warm";
	else delete root.dataset.heat;
	try {
		localStorage.setItem(THEME_KEY, theme);
		localStorage.setItem(HEAT_KEY, heat === "warm" ? "warm" : "blue");
	} catch {}
	emit("theme:changed", {
		theme,
		heat
	});
}
function set(theme) {
	const next = isTheme(theme) ? theme : "system";
	setState("theme", next);
	apply(next, getState().heat);
	return next;
}
function setHeat(heat) {
	const next = heat === "warm" ? "warm" : "blue";
	setState("heat", next);
	apply(getState().theme, next);
	return next;
}
/**
* 启动时读回本地偏好；随后 /settings 的值到位会覆盖它。
*
* **服务端渲染的那一档是回退值，不是被覆盖的值。** 优先级是
* localStorage（本浏览器）> `<html data-theme>`（服务端按配置渲染）> 跟随系统。
* 少了中间那一档，换一个浏览器首次打开时会从深色闪回跟随系统——服务端刚渲染对的
* 东西被前端第一件事擦掉，比不渲染更糟。
*
* **热力色现在与主题同一条路**（18 文档 批 3）：它有了配置键 `ui.heat`，服务端也一并
* 渲染 `<html data-heat>`，因此三档优先级对它同样成立。原先它只有 localStorage 一个来源
* ——那时换一个浏览器打开，色阶就回到蓝色，而用户以为自己已经把它设成暖色了。
*/
function restore() {
	const rendered = document.documentElement.dataset;
	const renderedTheme = rendered.theme || "system";
	const renderedHeat = rendered.heat || "blue";
	let theme = renderedTheme;
	let heat = renderedHeat;
	try {
		theme = localStorage.getItem(THEME_KEY) || renderedTheme;
		heat = localStorage.getItem(HEAT_KEY) || renderedHeat;
	} catch {}
	setState("theme", isTheme(theme) ? theme : "system");
	setState("heat", heat === "warm" ? "warm" : "blue");
	apply(getState().theme, getState().heat);
}
/** 跟随系统时，系统切换深浅要重绘图表——CSS 会自己换色，canvas 不会。 */
function watchSystem() {
	window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
		if (getState().theme === "system") emit("theme:changed", {
			theme: "system",
			heat: getState().heat
		});
	});
}
function prefersReducedMotion() {
	return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
//#endregion
//#region frontend/src/components/degraded.tsx
var DISMISS_KEY = "omnisight.dismissed";
function dismissed() {
	try {
		const raw = localStorage.getItem(DISMISS_KEY);
		return new Set(raw ? JSON.parse(raw) : []);
	} catch {
		return /* @__PURE__ */ new Set();
	}
}
function remember(code) {
	const codes = dismissed();
	codes.add(code);
	try {
		localStorage.setItem(DISMISS_KEY, JSON.stringify([...codes]));
	} catch {}
	return codes;
}
/** 挂在模板的 `#banners` 里（它带着 aria-live="polite"）。 */
function Banners() {
	const degraded = useSlice("degraded");
	const [hidden, setHidden] = (0, import_react.useState)(dismissed);
	const shown = (degraded || []).filter((notice) => notice.severity === "error" && !hidden.has(notice.code || notice.title));
	if (!shown.length) return null;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_jsx_runtime.Fragment, { children: shown.map((notice) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Banner, {
		notice,
		onClose: () => setHidden(remember(notice.code || notice.title))
	}, notice.code || notice.title)) });
}
function Banner({ notice, onClose }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "banner",
		"data-severity": notice.severity || "warning",
		role: "alert",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "banner__mark",
				"aria-hidden": "true",
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "warning" })
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "banner__body",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "banner__title",
						children: notice.title || "能力受限"
					}),
					notice.detail ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "banner__detail",
						children: notice.detail
					}) : null,
					notice.hint ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "banner__hint",
						children: notice.hint
					}) : null
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
				className: "banner__close",
				type: "button",
				"aria-label": "关闭提示",
				onClick: onClose,
				children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(Icon, { name: "close" })
			})
		]
	});
}
/** 面板问"我依赖的能力在不在"。**只读布尔值，不读 platform.id**（07 文档 §10）。 */
function capabilityOf(capabilities, name) {
	if (!capabilities) return true;
	return capabilities[name] !== false;
}
/**
* 找出与某个能力相关的那条 degraded 说明，好把后端文案原样显示在面板里。
*
* 只按 `code` 匹配。原先还有一个 `notice.capability === capability` 分支，而
* `DegradedNotice` 上**没有** `capability` 字段（types/api.d.ts，由契约测试对着真实
* 响应核对）——那个分支永远是 undefined 比较，从来没命中过。
*/
function noticeFor(degraded, capability) {
	return (degraded || []).find((notice) => notice.code === capability) || null;
}
//#endregion
export { ok as A, tokenParam as B, useSlice as C, subscribe as D, setState as E, get as F, require_react_dom as G, on as H, invalidate as I, require_react as K, messageOf as L, adoptToken as M, assetUrl as N, ToastHost as O, del as P, patch as R, useResource as S, setEntry as T, Icon as U, emit as V, require_jsx_runtime as W, formatDuration as _, isTheme as a, formatPercent as b, set as c, TooltipHost as d, hide as f, formatDayTime as g, formatCount as h, THEMES as i, ApiError as j, fail as k, setHeat as l, formatClock as m, capabilityOf as n, prefersReducedMotion as o, show as p, __commonJSMin as q, noticeFor as r, restore as s, Banners as t, watchSystem as u, formatDurationShort as v, getState as w, initialOf as x, formatMs as y, post as z };
