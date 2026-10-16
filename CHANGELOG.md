# 更新日志

本文件记录 **回复清理**（astrbot_plugin_reply_cleaner）的版本变更。
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [1.0.0] - 2026-10-16

### 新增
- **去掉消息开头的标记**（默认「……」）：只在开头生效，可自定义字符集
- **去掉思维链标签**：`<think>` / `<thinking>` / `<reasoning>` / `<analysis>` 等
- **去掉零宽字符**：U+200B/200C/200D/2060/FEFF
- 可选的**重复标点合并**（`。。。`→`。`）与**自称前缀清理**（`AI：`等）
- 群聊/私聊开关 + 会话黑名单
- 用 `priority=100` 注册，保证**先于分段插件**执行
- 清理后整条为空时**自动还原原文**，不会发出空消息

---

[1.0.0]: https://github.com/q1w2e3r4t5y6658/astrbot_plugin_reply_cleaner/releases/tag/v1.0.0
