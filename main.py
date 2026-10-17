"""回复清理：把模型输出里「不该发出去的东西」清掉，不改人格提示词。

主要功能（都可单独开关）：

1. **去掉开头的标记**（默认「……」）—— 很多人格习惯每条都「……」开头，
   发出去显得每句都欲言又止。默认**逐行清理**（因为分段插件会把每行拆成独立消息，
   只清整条开头的话后续分段仍会带「……」）。
2. **去掉思维链标签** —— 有些模型会把 <think>…</think> 之类的推理内容漏进正文。
3. **零宽字符清理** —— U+200B/U+200C/U+200D/U+FEFF 这类看不见的字符会搞得排版诡异。
4. **合并重复标点**（可选）—— 「。。。」→「。」「？？？」→「？」。
5. **去掉自称前缀**（可选）—— 开头的「AI：」「助手：」等角色前缀。

设计原则：
- 只处理**纯文本的模型回复**，带图片/引用/@ 的消息一律不动
- 清理后如果整条变成空的，就**还原成原文**，绝不发出空消息
- 用 priority=100 注册，**先于**分段类插件执行（否则开头的「……」已经被切成单独一条了）
"""

from __future__ import annotations

import re

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, register

DEFAULT_LEADING_MARKS = "……"
DEFAULT_TRAILING_MARKS = "……"
_ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff"
_THINK_RES = (
    re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.S | re.I),
    re.compile(r"<reason(?:ing)?>.*?</reason(?:ing)?>", re.S | re.I),
    re.compile(r"<analysis>.*?</analysis>", re.S | re.I),
    re.compile(r"<\|?think\|?>.*?<\|?/think\|?>", re.S | re.I),
)
_SELF_PREFIX_RE = re.compile(r"^\s*(?:AI|Bot|Assistant|助手|机器人|系统)\s*[:：]\s*", re.I)
_PUNCT_REPEAT_RE = re.compile(r"([。！？，、；：])\1{1,}")


@register(
    "astrbot_plugin_reply_cleaner",
    "q1w2e3r4t5y6658",
    "清理模型输出：去掉开头的「……」、思维链标签、零宽字符、重复标点等，不改人格提示词",
    "1.0.3",
    "https://github.com/q1w2e3r4t5y6658/astrbot_plugin_reply_cleaner",
)
class ReplyCleanerPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config

    # ------------------------------------------------------------------ #
    # 配置
    # ------------------------------------------------------------------ #
    def _cfg(self, key: str, default):
        try:
            if self.config is None:
                return default
            value = self.config.get(key, default)
            return default if value in (None, "") else value
        except Exception:  # noqa: BLE001
            return default

    def _cfg_bool(self, key: str, default: bool) -> bool:
        try:
            if self.config is None:
                return default
            return bool(self.config.get(key, default))
        except Exception:  # noqa: BLE001
            return default

    def _cfg_list(self, key: str) -> list:
        try:
            if self.config is None:
                return []
            value = self.config.get(key, [])
            if isinstance(value, str):
                return [x for x in value.replace(",", "\n").split("\n") if x.strip()]
            if isinstance(value, (list, tuple)):
                return list(value)
            return []
        except Exception:  # noqa: BLE001
            return []

    def _in_blacklist(self, event: AstrMessageEvent) -> bool:
        entries = self._cfg_list("blacklist")
        if not entries:
            return False
        umo = str(getattr(event, "unified_msg_origin", "") or "").strip()
        sid = umo.split(":")[-1].strip() if umo else ""
        try:
            gid = str(event.get_group_id() or "").strip()
        except Exception:  # noqa: BLE001
            gid = ""
        for raw in entries:
            entry = str(raw).strip()
            if entry and (entry == umo or (sid and entry == sid) or (gid and entry == gid)):
                return True
        return False

    # ------------------------------------------------------------------ #
    # 清理逻辑
    # ------------------------------------------------------------------ #
    @staticmethod
    def strip_leading(text: str, marks: str) -> str:
        """去掉开头连续的指定字符，再去掉残留空白。只在开头生效。"""
        if not marks:
            return text
        i = 0
        while i < len(text) and text[i] in marks:
            i += 1
        return text[i:].lstrip() if i else text

    @staticmethod
    def strip_trailing(text: str, marks: str) -> str:
        """去掉结尾连续的指定字符，再去掉残留空白。"""
        if not marks:
            return text
        i = len(text)
        while i > 0 and text[i - 1] in marks:
            i -= 1
        return text[:i].rstrip() if i < len(text) else text

    def clean_text(self, text: str, is_first: bool) -> str:
        """按配置逐项清理一段文本。"""
        if not text:
            return text
        out = text

        # ① 思维链标签
        if self._cfg_bool("strip_think_tags", True):
            for pattern in _THINK_RES:
                out = pattern.sub("", out)

        # ② 零宽字符
        if self._cfg_bool("strip_zero_width", True):
            out = out.translate({ord(ch): None for ch in _ZERO_WIDTH})

        # ③ 重复标点
        if self._cfg_bool("collapse_punctuation", False):
            out = _PUNCT_REPEAT_RE.sub(r"\1", out)

        # ④ 自称前缀（只可能出现在开头）
        if is_first and self._cfg_bool("strip_self_prefix", False):
            out = _SELF_PREFIX_RE.sub("", out)

        # ⑤ 首尾标记（本插件的主功能）：去掉开头的「……」和结尾的「……」
        do_lead = self._cfg_bool("strip_leading_marks", True)
        do_trail = self._cfg_bool("strip_trailing_marks", True)
        lead_marks = str(self._cfg("leading_marks", DEFAULT_LEADING_MARKS))
        trail_marks = str(self._cfg("trailing_marks", DEFAULT_TRAILING_MARKS))

        if do_lead or do_trail:
            if self._cfg_bool("strip_per_line", True):
                # 开头标记【逐行】清：模型常常每一行都以「……」开头，
                # 而分段插件会按行拆成多条消息，只清整条开头的话后续分段还是带「……」
                cleaned: list[str] = []
                for line in out.split("\n"):
                    if do_lead:
                        line = ReplyCleanerPlugin.strip_leading(line, lead_marks)
                    cleaned.append(line)
                if self._cfg_bool("drop_empty_lines", True):
                    kept = [line for line in cleaned if line.strip()]
                    cleaned = kept if kept else []
                out = "\n".join(cleaned)
            elif is_first and do_lead:
                out = ReplyCleanerPlugin.strip_leading(out, lead_marks)

            # 结尾标记【只清整条消息的最末尾】：
            # 中间的省略号（比如拟声词后面的「...」）要保留，只删最后那一个
            if do_trail:
                out = ReplyCleanerPlugin.strip_trailing(out, trail_marks)

        return out

    @staticmethod
    def _is_plain_model_result(result) -> bool:
        chain = getattr(result, "chain", None)
        if not isinstance(chain, list) or not chain:
            return False
        if not all(isinstance(c, Plain) for c in chain):
            return False
        for name in ("is_model_result", "is_llm_result"):
            fn = getattr(result, name, None)
            if callable(fn):
                try:
                    return bool(fn())
                except Exception:  # noqa: BLE001
                    return False
        return True

    # ------------------------------------------------------------------ #
    # Hook：发送前清理（priority=100，保证先于分段插件跑）
    # ------------------------------------------------------------------ #
    @filter.on_decorating_result(priority=100)
    async def clean_result(self, event: AstrMessageEvent) -> None:
        if not self._cfg_bool("enabled", True):
            return
        if self._in_blacklist(event):
            return
        is_group = bool(event.get_group_id())
        if is_group and not self._cfg_bool("group_enable", True):
            return
        if (not is_group) and not self._cfg_bool("private_enable", True):
            return

        result = event.get_result()
        chain = getattr(result, "chain", None)
        if not chain or not self._is_plain_model_result(result):
            return

        before = "".join(c.text for c in chain)
        if not before.strip():
            return

        originals = [c.text for c in chain]
        changed = False
        for idx, comp in enumerate(chain):
            cleaned = self.clean_text(comp.text, is_first=(idx == 0))
            if cleaned != comp.text:
                comp.text = cleaned
                changed = True

        after = "".join(c.text for c in chain)
        if not after.strip():
            if self._cfg_bool("drop_whole_if_empty", True):
                # 整条都只剩被清掉的内容（例如只发了「……」）→ 干脆不发
                for comp in chain:
                    comp.text = ""
                logger.debug("[reply_cleaner] 清理后整条为空，已置空不发送")
                return
            # 否则还原原文，绝不发出空消息
            for idx, comp in enumerate(chain):
                comp.text = originals[idx]
            logger.debug("[reply_cleaner] 清理后为空，已还原原文")
            return

        if changed:
            logger.debug("[reply_cleaner] %r -> %r", before[:40], after[:40])
