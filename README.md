# 通用群聊自动回复助手

一个使用 OpenAI Chat Completions 兼容 API 的 Windows 群聊自动回复工具。

- 启动后显示 Tk 主窗口；
- “设置模型”里填写 API Base、API Key、Model，可选用“测试连接”；
- “选择输入框位置”后在屏幕上点击聊天输入框；
- “选择识别区域”后在屏幕上拖拽框选消息区域；
- “消息与识别设置”里设置触发关键词、OCR 语言、识别放大倍数；
- “编辑系统提示词”支持多行编辑，保存到 `settings.json`；
- “预览识别区域”会隐藏主窗口、截取区域、显示 OCR 结果和触发词命中情况；
- “开始识别/回复”后，识别到触发消息就排队，按顺序逐条回复。

本项目**只支持 Windows 10 x64 1809（build 17763）及以上版本**。

---

## 功能特点

- **Windows 系统自带 OCR**：使用 `Windows.Media.Ocr`，不依赖 RapidOCR、PaddleOCR、Tesseract 等第三方 OCR 引擎。
- **最终用户零安装**：Python、Tk、winrt 绑定全部打包进 exe，不需要安装 Python、pip 包、VC++ 运行库或 .NET。
- **轻量**：单文件 exe 约 10–13MB，不再携带 onnxruntime / opencv / numpy / 模型文件。
- **单线程串行流水线**：识别 → 排队 → API → 发送成功 → 成对写记忆 → 下一条，回复顺序和记忆配对不会乱。
- **多显示器选区**：每块屏幕一个置顶遮罩，支持任意屏幕取点/拉框。
- **OCR 倍率兜底**：默认 2 倍；如果当前倍率没有命中触发词，会自动换另一个倍率再试一次，降低小字号漏识别概率。
- **配置迁移**：首次运行时会自动把旧的 `chatbot.json` 迁移为 `settings.json`。
- **日志**：UI 日志 + 同目录 `chatbot.log`，打包后没有控制台也能排查。

---

## 系统要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10 x64，build 17763（1809）或更高 |
| OCR 语言 | 系统需已安装中文 OCR 语言包（中文版 Windows 通常自带） |
| 运行时 | 不需要安装任何东西；直接运行 exe |
| 目录 | 建议放在可写目录（如 `D:\Tools\GeneralChatbot`），不要放 `Program Files`；`settings.json`、`memory.json`、日志写在 exe 旁边 |
| 构建环境 | Python 3.11 x64 + `requirements.txt` 中的 winrt 包 |

程序启动时会检查：

1. Windows build 是否 ≥ 17763；
2. `Windows.Media.Ocr` 是否有中文（`zh-*`）识别语言。

缺少中文 OCR 语言包时会弹窗说明并退出，不会静默失败。

检查本机 OCR 语言（PowerShell，不需要管理员权限）：

```powershell
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag }
```

正常应输出类似：

```
zh-Hans-CN
```

如果系统是英文版且没有中文语言包，需要先在 Windows 设置里添加中文语言及 OCR 可选功能；这属于系统功能，不是本程序的 Python 依赖。

---

## 从源码运行

```bat
python -m pip install -r requirements.txt
python main.py
```

首次运行会读取同目录的 `settings.json`；如果只有旧的 `chatbot.json`，会自动迁移并生成 `settings.json`。

---

## 使用流程

1. **设置模型**：填写 API Base、API Key、Model。可以点“测试连接（可选）”，测试使用当前填写但尚未保存的值。
2. **选择输入框位置**：主窗口隐藏后，在聊天软件输入框上点击一次。
3. **选择识别区域**：在消息区域按住左键拖拽框选，松开完成；Esc 取消。
4. **消息与识别设置**：
   - 触发关键词，例如 `@EZ118`；
   - OCR 语言，默认 `zh-Hans-CN`；
   - 识别放大倍数，默认 2；区域很大或字体清晰时可以改成 1。
5. **编辑系统提示词**（可选）：多行文本，保存后写入 `settings.json`。
6. **预览识别区域**（推荐）：确认 OCR 能识别出目标消息，并且触发词命中。
7. **开始识别/回复**：程序每隔约 1.2 秒截图一次，命中触发词的文本进入队列，由单线程依次请求 API、发送回复、写入记忆。
8. 再点一次按钮停止；停止时会丢弃尚未处理的排队消息，已经生成但尚未发送的回复也不会发送。

运行发送时程序会移动鼠标、点击输入框、全选、粘贴、回车，**请不要同时操作鼠标键盘**。

---

## 配置文件

### settings.json

与 exe（源码运行时为 `main.py`）同目录，便携保存，不写注册表。

```json
{
  "api_base": "https://api.deepseek.com",
  "api_key": "sk-...",
  "model": "deepseek-flash",
  "input_pos": [1421, 948],
  "capture_region": [1393, 858, 468, 53],
  "trigger": "@EZ118",
  "system_prompt": "多行系统提示词……",
  "ocr_language": "zh-Hans-CN",
  "ocr_scale": 2
}
```

说明：

- 首次运行且目录下没有 `settings.json` / `chatbot.json` 时，程序会自动创建 `settings.json`，其中 `system_prompt` 写入默认初始化内容。
- `system_prompt` 支持多行，换行以 JSON 字符串转义保存；实际值以该字段为准。
- `api_key` 是明文保存的，请注意不要分享 `settings.json`。
- 旧的 `chatbot.json` 会被自动读取并写为 `settings.json`；旧文件可以自行删除。
- `dist_pyinstaller` / `dist_nuitka` 里的 `settings.json`、`memory.json` 是构建时复制的**独立副本**；运行 dist 里的 exe 修改的是副本，不会改到源码目录下的文件。需要共用时请手动复制。

### memory.json

消息记忆，结构兼容旧版本：

```json
[
  {"role": "system", "content": "【用户注入】..."},
  {"role": "user", "content": "群友消息"},
  {"role": "assistant", "content": "助手回复"}
]
```

- 一轮问答通过一次加锁同时写入 `user` + `assistant`，不会出现半截配对；
- 只有发送成功才写入记忆；
- 请求时保留全部 `system` 注入 + 历史摘要 + 最近 20 组完整问答；
- “压缩记忆”只在停止状态可用，压缩后保留 system 注入内容，只替换对话部分；
- 记忆文件采用临时文件 + 原子替换方式写入。

---

## OCR 说明

- 使用 `Windows.Media.Ocr`，不联网、不上传截图。
- 默认 `ocr_scale = 2`。放大在 GDI 层完成，不依赖 Pillow/numpy。
- 正式识别时：
  1. 先用设置的倍率 OCR；
  2. 如果整屏都没有命中触发词，自动换另一个倍率（1↔2）再试一次；
  3. 只有第一遍有命中时才不执行第二遍，避免同一条消息重复入队。
- Windows OCR 会在汉字之间插入空格，程序会去掉汉字/中文标点/`@` 之间的空格，并忽略全角半角差异后再匹配触发词。
- OCR 仍可能认错字。建议使用“预览识别区域”确认；如果小字识别不稳定，把倍数设为 2 或 3。

---

## 回复与记忆顺序

```
识别线程：截图 → OCR → 触发词 → 去重 → 消息队列
工作线程：取消息 → 带记忆快照请求 API → 发送到输入框
          → 发送成功 → 成对写入 memory.json → 取下一条
```

- 单工作线程保证回复严格按消息到达顺序发出；
- API 失败、发送失败、停止时丢弃的回复都不写记忆；
- 每轮发送成功后立即原子保存记忆；
- 上下文裁剪只按完整问答对切，不会从中间截断。

---

## 打包

两个脚本都默认生成**单文件** exe，并自动安装 `requirements.txt`：

### PyInstaller（推荐先评估）

```bat
build_pyinstaller.bat
```

输出：

```
dist_pyinstaller\GeneralChatbot.exe
```

- 构建时间约 1 分钟；
- 不需要 C 编译器；
- `ONEFILE_FLAG` 改成空值可生成目录版。
- 构建脚本会把同目录的 `settings.json` / `memory.json` 复制到输出目录（目录版会复制到 exe 所在子目录），方便直接运行。

### Nuitka

```bat
build_nuitka.bat
```

输出：

```
dist_nuitka\GeneralChatbot.exe
```

- 构建时间通常 2–5 分钟；
- 需要 MSVC Build Tools 或 MinGW64；脚本带 `--assume-yes-for-downloads`，必要时 Nuitka 会下载 MinGW64；
- 使用 `--mode=onefile` 和 `--enable-plugin=tk-inter`；
- 改成 `--mode=standalone` 可生成目录版。

两个脚本都只收集 `winrt` 相关模块，不再需要 OCR 模型/onnxruntime/opencv 的打包参数。

本机实测（Python 3.11.9 x64、PyInstaller 6.22.2、Nuitka 4.2）：

| 工具 | 单文件体积 | 说明 |
|---|---|---|
| PyInstaller | 12.8 MB | 构建约 20 秒，自带 winrt hook，成功率高 |
| Nuitka | 9.7 MB | 构建约 1–3 分钟，需要 C 编译器；必须带 `--include-package-data=winrt`，否则运行时会缺 `_table.pywinrt` |

两个产物都已通过 `--self-test` 的真实 OCR 自检。

### 打包后自检

exe 支持一个隐藏的自检参数，会抓取当前识别区域并真正执行一次 OCR，然后弹出结果并写入同目录 `self-test.log`：

```bat
GeneralChatbot.exe --self-test
```

在 Windows 10 1809 实机/虚拟机上建议先跑一次这个命令，确认 OCR 引擎和语言包可用。

---

## 常见问题

**Q：启动提示缺少中文 OCR 语言包？**  
A：本机 Windows 没有 `zh-*` OCR 语言。请在 Windows 设置 → 时间和语言 → 语言中添加中文（简体），并安装 OCR 可选功能。程序只支持已经具备中文 OCR 的系统。

**Q：在 Windows 10 1809 上能用吗？**  
A：代码只使用 `Windows.Media.Ocr`（Win10 10240 起存在）和 pywinrt 官方最低支持的 1809 API；构建后建议在 1809 实机/虚拟机做一次冒烟测试。若 winrt 4.x 在 1809 出现兼容问题，可把 `requirements.txt` 换成旧版 `winsdk==1.0.0b10` 并相应调整导入（属于备选方案，默认不启用）。

**Q：能识别到字，但没有触发回复？**  
A：先点“预览识别区域”，看命中行数是否为 0。常见原因是触发词字符被 OCR 认错、区域框选不完整、触发词前后有特殊空格。可以尝试把识别倍数改成 2/3，或扩大识别区域。

**Q：发送失败 / 没有粘贴？**  
A：检查输入框位置是否仍然有效；目标聊天程序是否以管理员身份运行（如果是，本程序也需要以管理员身份运行，否则 Windows UIPI 会拦截输入）；发送时不要占用鼠标键盘；其他程序是否锁住了剪贴板。错误会写到运行日志和 `chatbot.log`。

**Q：多显示器支持吗？**  
A：支持。选择时每块屏幕都会出现遮罩，可在任意屏幕取点/拉框；预览窗会尝试放在识别区域旁边并保持置顶。

**Q：会把本程序的窗口截进去吗？**  
A：选择区域时主窗口会隐藏；预览时也会先隐藏主窗口再截图。但其他程序窗口如果挡在识别区域上，仍然会被截到，使用前请把聊天窗口放在最前。

**Q：为什么 exe 第一次启动稍慢？**  
A：单文件模式需要把内置的 Python/Tk/winrt 解压到临时目录。对启动速度敏感时可以改成目录版（见打包脚本注释）。

---

## 项目结构

```
main.py                     入口、系统版本检查、OCR 环境检查
chatbot/
  paths.py                  可写文件路径
  constants.py              轮询间隔、超时、上下文长度等常量
  prompts.py                默认系统提示词和提示词模板
  settings.py               settings.json 读写/校验/迁移
  memory.py                 记忆存储、上下文裁剪、压缩
  api.py                    urllib 实现的 OpenAI 兼容客户端
  ocr.py                    Windows.Media.Ocr 封装
  textutil.py               OCR 文本整理、触发词匹配
  imageutil.py              BGRA → PPM
  controller.py             识别/API/发送的单线程流水线
  logging_setup.py          文件日志
  win32/                    DPI、显示器、GDI 截屏、SendInput、剪贴板
  ui/                       主窗口、对话框、屏幕选择器
build_pyinstaller.bat
build_nuitka.bat
requirements.txt
settings.json
memory.json
```

---

## 已知限制

- 只支持 Windows 10 1809+ x64，不支持 32 位系统。
- 基于屏幕文字识别，不读取聊天软件内部数据；窗口被遮挡时识别不到。
- 触发判断以 OCR 的“行”为单位。如果一条消息换行后触发词和正文被分到两行，只会使用包含触发词的那一行。
- OCR 对极小字号、特殊字体、花哨背景可能出错；已提供预览、倍率兜底和空格/全角归一化，但不能保证 100%。
- 发送通过模拟鼠标键盘完成，目标程序必须可被当前权限级别操作；管理员程序需要本程序也以管理员身份运行。
- API Key 以明文保存在 `settings.json`。
