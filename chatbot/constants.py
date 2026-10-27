# -*- coding: utf-8 -*-
"""全局常量。用户可以在设置界面调整的项不放在这里。"""

APP_NAME = "GeneralChatbot"
APP_TITLE = "群聊自动回复助手"
APP_VERSION = "2.0"

# 最低 Windows 10 1809 (build 17763)
MIN_WINDOWS_BUILD = 17763

# 识别循环
POLL_INTERVAL = 1.2          # 秒
SEEN_EXPIRE = 600            # 同一段文字多少秒内不重复回复
MAX_SEEN = 500

# 上下文与 API
MAX_CONTEXT_PAIRS = 20       # 最多发送最近 20 组问答
API_TIMEOUT = 45             # 秒
COMPRESS_TIMEOUT = 90        # 秒
TEST_TIMEOUT = 20            # 秒

# 发送动作之间的等待时间（秒）
SEND_CLICK_WAIT = 0.18
SEND_SELECT_WAIT = 0.06
SEND_PASTE_WAIT = 0.22
SEND_ENTER_WAIT = 0.15

# 剪贴板被占用时的重试
CLIPBOARD_RETRIES = 12
CLIPBOARD_RETRY_DELAY = 0.05

# 日志
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3
UI_LOG_MAX_LINES = 800

# 设置默认值
DEFAULT_TRIGGER = "@周"
DEFAULT_OCR_LANGUAGE = "zh-Hans-CN"
DEFAULT_OCR_SCALE = 2
MAX_OCR_SCALE = 3
