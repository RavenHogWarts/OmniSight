"""macOS 原生位置码 → HID usage → ``key_id``（04 文档 §3.2、19 文档 §2.2）。

``kVK_*`` 常量是 Carbon 的虚拟键码，但在 macOS 上它们**就是物理位置码**——与
Windows 的 VK 不同，它不随键盘布局变化（换成 Dvorak 布局后 ``kVK_ANSI_A``
仍然是键盘左边第二排第一个键）。因此这里不需要 Windows 那套"改用扫描码"的绕法。

同 Windows 一样是纯函数，不 import 任何 Quartz 符号——常量值写死在表里。
这让本文件在任何平台上都可测（11 文档 §8.1），也是"macOS 适配器的大部分能
在 Windows 开发机上写完并测完"的直接依据（20 文档 B1）。

**修饰键只有 FlagsChanged，没有 KeyDown/KeyUp**（19 文档 §2.3）：事件里没有
"按下还是抬起"这一位，判定要靠 flags 位与该 keycode 的上一状态合起来看，
**左右必须靠 keycode 区分**——左右 ⌘ 的 flags 位是同一个
（``kCGEventFlagMaskCommand``），靠 flags 判定会把左右合并，而能力位仍上报
``key_position_stable=True``，那是最坏的一种坏法。
"""

from __future__ import annotations

from ..hid import key_id_for_hid

#: CGEvent 类型（Quartz 的 ``kCGEventKeyDown`` 等）。写死数值，不 import Quartz。
EVENT_KEY_DOWN = 10
EVENT_KEY_UP = 11
EVENT_FLAGS_CHANGED = 12

#: ``kCGEventFlagMask*`` 的数值。FlagsChanged 事件里判定修饰键当前状态的依据。
FLAG_MASK_ALPHA_SHIFT = 1 << 16  # Caps Lock（这是锁定状态，不是瞬态按压）
FLAG_MASK_SHIFT = 1 << 17
FLAG_MASK_CONTROL = 1 << 18
FLAG_MASK_ALTERNATE = 1 << 19  # Option
FLAG_MASK_COMMAND = 1 << 20

#: ``kVK_*``（Carbon ``HIToolbox/Events.h``）→ HID usage。
#:
#: 刻意**不收录**的键与理由（它们会进"未映射"计数而不是静默消失）：
#:
#: * ``kVK_Function``（0x3F，Fn）：现代 Mac 上它根本不产生事件，映射它是谎报
#:   （19 文档 §8"明确不做"）；
#: * 音量三键（0x48~0x4A）：媒体键，``KEY_IDS`` 没有媒体键这个分区；
#: * JIS 专用键（0x5D/0x5E/0x5F/0x66/0x68，¥/_/小键盘逗号/英数/かな）：
#:   ``KEY_IDS`` 没有对应键，收录等于造幽灵 id（19 文档 §3.1 的同一条原则）。
KVK_TO_HID: dict[int, int] = {
    # ── 字母区（kVK_ANSI_* 是物理位置码，与布局无关）─────────────────────
    0x00: 0x04,  # kVK_ANSI_A
    0x0B: 0x05,  # kVK_ANSI_B
    0x08: 0x06,  # kVK_ANSI_C
    0x02: 0x07,  # kVK_ANSI_D
    0x0E: 0x08,  # kVK_ANSI_E
    0x03: 0x09,  # kVK_ANSI_F
    0x05: 0x0A,  # kVK_ANSI_G
    0x04: 0x0B,  # kVK_ANSI_H
    0x22: 0x0C,  # kVK_ANSI_I
    0x26: 0x0D,  # kVK_ANSI_J
    0x28: 0x0E,  # kVK_ANSI_K
    0x25: 0x0F,  # kVK_ANSI_L
    0x2E: 0x10,  # kVK_ANSI_M
    0x2D: 0x11,  # kVK_ANSI_N
    0x1F: 0x12,  # kVK_ANSI_O
    0x23: 0x13,  # kVK_ANSI_P
    0x0C: 0x14,  # kVK_ANSI_Q
    0x0F: 0x15,  # kVK_ANSI_R
    0x01: 0x16,  # kVK_ANSI_S
    0x11: 0x17,  # kVK_ANSI_T
    0x20: 0x18,  # kVK_ANSI_U
    0x09: 0x19,  # kVK_ANSI_V
    0x0D: 0x1A,  # kVK_ANSI_W
    0x07: 0x1B,  # kVK_ANSI_X
    0x10: 0x1C,  # kVK_ANSI_Y
    0x06: 0x1D,  # kVK_ANSI_Z
    # ── 数字行 ────────────────────────────────────────────────────────────
    0x1A: 0x24, 0x1C: 0x25, 0x19: 0x26,  # 7 8 9（kVK 顺序与数字顺序不同）
    0x1D: 0x27, 0x12: 0x1E, 0x13: 0x1F, 0x14: 0x20,  # 0 1 2 3
    0x15: 0x21, 0x16: 0x22, 0x17: 0x23,              # 4 5 6
    0x1B: 0x2D,  # kVK_ANSI_Minus
    0x18: 0x2E,  # kVK_ANSI_Equal
    # ── 标点 ──────────────────────────────────────────────────────────────
    0x21: 0x2F,  # kVK_ANSI_LeftBracket
    0x1E: 0x30,  # kVK_ANSI_RightBracket
    0x2A: 0x31,  # kVK_ANSI_Backslash
    0x29: 0x33,  # kVK_ANSI_Semicolon
    0x27: 0x34,  # kVK_ANSI_Quote
    0x32: 0x35,  # kVK_ANSI_Grave
    0x2B: 0x36,  # kVK_ANSI_Comma
    0x2F: 0x37,  # kVK_ANSI_Period
    0x2C: 0x38,  # kVK_ANSI_Slash
    0x0A: 0x64,  # kVK_ISO_Section → ISO 第 102 键
    # ── 控制键 ────────────────────────────────────────────────────────────
    0x24: 0x28,  # kVK_Return（主键盘 Enter）
    0x30: 0x2B,  # kVK_Tab
    0x33: 0x2A,  # kVK_Delete（Mac 的 Delete 就是 PC 的 Backspace）
    0x31: 0x2C,  # kVK_Space
    0x35: 0x29,  # kVK_Escape
    0x39: 0x39,  # kVK_CapsLock
    # ── 修饰键（左右成对，keycode 区分）───────────────────────────────────
    0x37: 0xE3,  # kVK_Command       → 左 ⌘（HID Left GUI = win_left）
    0x36: 0xE7,  # kVK_RightCommand  → 右 ⌘
    0x3A: 0xE2,  # kVK_Option        → 左 ⌥（HID Left Alt）
    0x3D: 0xE6,  # kVK_RightOption   → 右 ⌥
    0x3B: 0xE0,  # kVK_Control       → 左 ⌃
    0x3E: 0xE4,  # kVK_RightControl  → 右 ⌃
    0x38: 0xE1,  # kVK_Shift         → 左 ⇧
    0x3C: 0xE5,  # kVK_RightShift    → 右 ⇧
    # ── 功能键（kVK 与 F 序号交叉，逐条列出）─────────────────────────────
    0x7A: 0x3A, 0x78: 0x3B, 0x63: 0x3C, 0x76: 0x3D,  # F1 F2 F3 F4
    0x60: 0x3E, 0x61: 0x3F, 0x62: 0x40, 0x64: 0x41,  # F5 F6 F7 F8
    0x65: 0x42, 0x6D: 0x43, 0x67: 0x44, 0x6F: 0x45,  # F9 F10 F11 F12
    0x69: 0x68,  # F13
    0x6B: 0x69,  # F14
    0x71: 0x6A,  # F15
    0x6A: 0x6B,  # F16
    0x40: 0x6C,  # F17
    0x4F: 0x6D,  # F18
    0x50: 0x6E,  # F19
    0x5A: 0x6F,  # F20
    # ── 导航簇 ────────────────────────────────────────────────────────────
    0x72: 0x49,  # kVK_Help → Insert 位（全尺寸 Mac 键盘上物理同位）
    0x73: 0x4A,  # kVK_Home
    0x74: 0x4B,  # kVK_PageUp
    0x75: 0x4C,  # kVK_ForwardDelete
    0x77: 0x4D,  # kVK_End
    0x79: 0x4E,  # kVK_PageDown
    0x7B: 0x50,  # ←
    0x7C: 0x4F,  # →
    0x7D: 0x51,  # ↓
    0x7E: 0x52,  # ↑
    # ── 小键盘 ────────────────────────────────────────────────────────────
    0x47: 0x53,  # kVK_ANSI_KeypadClear → HID 0x53 本就是 "Keypad NumLock/Clear"
    0x4B: 0x54,  # ÷
    0x43: 0x55,  # ×
    0x4E: 0x56,  # −
    0x45: 0x57,  # +
    0x4C: 0x58,  # kVK_ANSI_KeypadEnter
    0x59: 0x5F, 0x5B: 0x60, 0x5C: 0x61,  # 7 8 9
    0x56: 0x5C, 0x57: 0x5D, 0x58: 0x5E,  # 4 5 6
    0x53: 0x59, 0x54: 0x5A, 0x55: 0x5B,  # 1 2 3
    0x52: 0x62,  # 0
    0x41: 0x63,  # .
    0x51: 0x67,  # kVK_ANSI_KeypadEquals（苹果键盘独有，pynput 认不出的那个）
}

#: FlagsChanged 判定按下/抬起用的位掩码，**按 keycode 查**（左右同位、不同码）。
MODIFIER_MASK_BY_KEYCODE: dict[int, int] = {
    0x37: FLAG_MASK_COMMAND, 0x36: FLAG_MASK_COMMAND,        # ⌘ 左/右
    0x3A: FLAG_MASK_ALTERNATE, 0x3D: FLAG_MASK_ALTERNATE,    # ⌥ 左/右
    0x3B: FLAG_MASK_CONTROL, 0x3E: FLAG_MASK_CONTROL,        # ⌃ 左/右
    0x38: FLAG_MASK_SHIFT, 0x3C: FLAG_MASK_SHIFT,            # ⇧ 左/右
    0x39: FLAG_MASK_ALPHA_SHIFT,                             # Caps Lock
}


def resolve(
    keycode: int,
    event_type: int,
    flags: int = 0,
    previous_held: bool = False,
) -> tuple[str | None, int | None, bool]:
    """把一次 event tap 上报解析为 ``(key_id, hid_usage, is_down)``。

    纯函数、无副作用，因此可以用录制的原生事件做表驱动测试（11 文档 §8.1）。
    与 Windows 版同一条约定：``key_id`` 为 ``None`` 表示该键不在表内（媒体键、
    JIS 专用键、Fn），调用方计入"未映射"计数而不是静默忽略。

    修饰键走 ``kCGEventFlagsChanged``，**单凭事件自身判不出按下还是抬起**：

    * flags 位左右共用——左右 ⌘ 是同一个 ``kCGEventFlagMaskCommand``；
    * 更糟的是**重叠区**：两个 ⌘ 都按住再放开左边那颗，flags 的位根本不变。

    因此左右靠 keycode 区分，按压方向靠"flags 位 × 该 keycode 的上一状态"：
    位是 0 → 必然抬起；位是 1 且上一状态未按 → 按下；位是 1 且上一状态已按 →
    抬起（事件只会因为**这个键**状态翻转才投递，位没变说明是孪生键还按着）。
    ``previous_held`` 由调用方（event tap 的事件泵/测试解码器）按 keycode 维护
    ——状态留在泵里、解码保持纯函数，与 Windows 版的分工完全一致。

    Caps Lock 的位是**锁定状态**而非瞬态：开启记一次按下、关闭记一次抬起，
    配对仍然完整，``duration`` 的语义是"大写锁定持续时长"。
    """
    if event_type == EVENT_FLAGS_CHANGED:
        mask = MODIFIER_MASK_BY_KEYCODE.get(keycode)
        usage = KVK_TO_HID.get(keycode)
        if mask is None or usage is None:
            return None, None, False
        held_now = bool(flags & mask)
        return key_id_for_hid(usage), usage, held_now and not previous_held

    # KeyDown / KeyUp：普通键，flags 不参与判定。
    usage = KVK_TO_HID.get(keycode)
    return key_id_for_hid(usage), usage, event_type == EVENT_KEY_DOWN


__all__ = [
    "EVENT_FLAGS_CHANGED",
    "EVENT_KEY_DOWN",
    "EVENT_KEY_UP",
    "FLAG_MASK_ALPHA_SHIFT",
    "FLAG_MASK_ALTERNATE",
    "FLAG_MASK_COMMAND",
    "FLAG_MASK_CONTROL",
    "FLAG_MASK_SHIFT",
    "KVK_TO_HID",
    "MODIFIER_MASK_BY_KEYCODE",
    "resolve",
]
