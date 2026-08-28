# LocalMeetingCopilot

LocalMeetingCopilot is a local-first desktop meeting copilot for Chinese professionals in German/English meetings. The current MVP runs on macOS for development with mock, microphone, or WAV input, and includes a Windows live mode for microphone + WASAPI loopback capture.

Read this guide in:

- English: start below.
- 中文: jump to [中文操作指南](#中文操作指南).
- Browser guide: open [docs/guide.html](docs/guide.html) for a bilingual English/Chinese version.

## Quick Start

```bash
cd /Users/yuanxiaoyu/projects/LocalMeetingCopilot
source .venv/bin/activate
python run.py --check
python run.py --model-check --profile de
python run.py --mock
```

For local microphone capture on macOS:

```bash
python run.py --mic
```

macOS may ask for microphone permission on the first run. If you need a specific input device, run `python run.py --check`, then set:

```bash
export LMC_MIC_DEVICE_INDEX=0
python run.py --mic
```

For macOS two-track experiments, use a virtual or app-provided input device for remote audio. First list devices:

```bash
python run.py --check
```

If `macOS remote input candidates` shows a device like `BlackHole 2ch`, `Background Music`, `Microsoft Teams Audio`, or `Zoom Audio`, start:

```bash
export LMC_MIC_DEVICE_INDEX=0
export LMC_REMOTE_DEVICE_INDEX=2
python run.py --mac-live --profile de
```

If no remote input candidate appears, install a virtual audio device and route meeting audio into it:

```bash
brew install blackhole-2ch
```

Then open macOS Audio MIDI Setup and create a Multi-Output Device that includes your speaker/headphones plus `BlackHole 2ch`. Set your meeting app or system output to that Multi-Output Device, then set `LMC_REMOTE_DEVICE_INDEX` to the `BlackHole 2ch` input index from `python run.py --check`.

For an audio file:

```bash
python run.py --wav /absolute/path/to/meeting.wav
```

The first WAV run may download a faster-whisper model into `models/`.

## Model Preflight

Check local ASR and Ollama models before a real meeting:

```bash
python run.py --model-check --profile de --preset fast --style meeting
```

The command checks Python packages, the faster-whisper cache under `models/`, the Ollama CLI, and the configured Ollama model. It does not download anything automatically; if something is missing, it exits non-zero and prints the exact fix command, such as `ollama pull qwen2.5:3b-instruct`.

## Diagnostics Bundle

When a Windows or macOS machine behaves differently from yours, run:

```bash
python run.py --doctor --profile de --preset fast --style meeting
```

This writes a shareable folder under `logs/diagnostics/diagnostic_YYYYMMDD_HHMMSS/` with `report.md`, `system.json`, `audio_devices.json`, `ollama.json`, `models.json`, `config.json`, `git.txt`, and `python_packages.txt`. The bundle records environment metadata, device names, selected audio indexes, Ollama health, model preflight status, Git status, and recent log file names only. It does not record audio or transcript contents.

## Support Bundle

For remote debugging, ask the tester to run one command:

```bash
python run.py --support-bundle --profile de --preset fast --style meeting
```

This creates `logs/support/support_YYYYMMDD_HHMMSS.zip` with captured `--check`, `--model-check`, and doctor outputs. It does not listen to the microphone by default. If audio/VAD calibration is needed, explicitly include it:

```bash
python run.py --support-bundle --profile de --support-include-audio-test --audio-test-seconds 8
```

## Audio Test And Crash Logs

Before joining a real call, run a short audio/VAD calibration:

```bash
python run.py --audio-test --profile de --audio-test-seconds 12
```

The test does not start Whisper or Ollama. It prints live RMS/peak level, VAD state, received chunk count, speech starts, and completed VAD cuts for the mic plus the platform remote track. Use `--no-mic-track` or `--no-remote-track` to isolate one side.

If the app exits unexpectedly, a crash report is written to:

```text
logs/crash/crash_YYYYMMDD_HHMMSS_xxxxxx.txt
```

The crash log contains Python/platform metadata and a traceback so the failure can be debugged without guessing.

## Dashboard Controls

The dashboard control panel now exposes the most useful runtime switches:

- Profile: `de`, `en`, or `de-en`.
- Preset: `fast`, `balanced`, or `accurate`.
- Tune buttons: quick `fast` / `balanced` / `accurate` switches for live latency comparison.
- Style: `literal`, `meeting`, or `natural` Chinese translation.
- Mic and Remote input device selectors.
- Track toggles for local mic and remote audio.
- Storage toggles for report export, privacy mode, and debug WAV chunks.
- Auto summary on End.
- VAD sensitivity slider for more aggressive or more conservative sentence cuts.
- Latency diagnostics showing ASR, LLM, and total time per translated sentence.
- Live audio meters for Mic and Remote, including VAD speech/idle state.
- Performance timeline summary for the latest final subtitle.
- Latency Window with rolling ASR/LLM/Queue/Total avg, p95, max, and target bars for the current tuning window.
- Speaker correction: select a transcript row, rename `Remote Participant`, and apply it to future matching speech.
- Runtime settings are saved to `settings.json` and restored on the next launch.

Audio device and ASR model changes should be made before pressing Start. Text style, storage settings, and speaker aliases can be changed anytime.

## ASR Language And Latency

The Whisper model is a single multilingual model, so unsupported languages cannot be deleted as separate language packs. LocalMeetingCopilot instead enforces an application-level language gate:

- `--profile de`: pure German channel. ASR is forced to German for speed and fewer hallucinations.
- `--profile en`: pure English channel. ASR is forced to English.
- `--profile de-en`: mixed German/English channel. ASR auto-detects only between German and English, then falls back to German if detection fails.
- Each profile injects a small meeting vocabulary prompt and hotwords list for common business/project terms.
- If the retry still reports an unsupported language, that sentence is dropped instead of being translated.
- Realtime VAD is tuned for lower latency with a shorter silence cutoff.
- Partial subtitles show temporary ASR text while someone is still speaking; the final sentence is translated after the VAD cut.
- Chinese translation streams into the overlay while Ollama is still generating, so the UI no longer waits for the full response.
- Ending a meeting automatically shows a local summary preview, then replaces it with the Ollama-refined summary when ready.
- German clause fragments are held briefly and merged when possible, especially around `weil`, `dass`, `wenn`, and `obwohl`.

For mostly German meetings, use:

```bash
python run.py --mac-live --profile de
```

For mixed German/English meetings:

```bash
python run.py --mac-live --profile de-en
```

You can also set a default profile through the environment:

```bash
export LMC_MEETING_PROFILE=de
```

If Ollama requests hang or app shutdown feels too slow, lower the local request timeout:

```bash
export LMC_OLLAMA_TIMEOUT_SECONDS=20
```

Useful command-line combinations:

```bash
python run.py --mac-live --profile de --preset fast --style meeting
python run.py --mac-live --profile de --preset accurate --style literal
python run.py --mac-live --profile de --privacy
python run.py --mac-live --profile de --debug-audio
python run.py --mac-live --profile de --no-remote-track
```

Preset meaning:

- `fast`: base Whisper, high VAD sensitivity, shorter context, streaming-first translation.
- `balanced`: small Whisper, medium VAD sensitivity, slightly slower but more accurate.
- `accurate`: medium Whisper, lower VAD sensitivity, wider beam, best for WAV/offline or strong machines.

Translation style meaning:

- `literal`: precise, detail-preserving Chinese.
- `meeting`: concise meeting-note Chinese.
- `natural`: smoother spoken Chinese.

Performance knobs:

```bash
export LMC_WARMUP=1
export LMC_PARTIAL_SKIP_WHEN_ASR_BUSY=1
export LMC_OLLAMA_TIMEOUT_SECONDS=20
export LMC_SHUTDOWN_WAIT_MS=8000
export LMC_TRANSLATION_CACHE=1
export LMC_TRANSLATION_CACHE_PERSIST=1
export LMC_PERFORMANCE_LOGGING=1
```

Warmup loads Whisper and pings Ollama shortly after startup. Common filler phrases such as `ja`, `genau`, `okay`, and `mhm` use local translations instead of waiting for Ollama. Short sentences automatically use smaller Ollama output limits. Repeated final-sentence translations are cached; disk cache is stored at `logs/cache/translation_cache.jsonl` only when privacy mode is off. Performance timeline records are stored at `logs/performance/performance_YYYYMMDD.jsonl` only when privacy mode is off; they include timing metadata and character counts, not transcript text. Shutdown waits briefly for background translation before exiting.

Custom vocabulary lives in:

```text
profiles/custom_terms.txt
profiles/terms.yaml
```

Add company names, people, project names, acronyms, and plain ASR terms to `profiles/custom_terms.txt`, one per line. For precise translation terminology, use `profiles/terms.yaml`:

```yaml
- source: Kundentabelle
  variants: ["Kunden Tabelle", "customer table"]
  zh: 客户表
  category: data
  priority: high
```

The `.txt` terms still help ASR prompts and hotwords. The structured YAML glossary is matched per sentence, and only the most relevant top terms are injected into the translation prompt.

## Benchmark Harness

Put open benchmark clips under `benchmarks/audio/`, then copy and edit `benchmarks/manifest.example.json` into `benchmarks/manifest.local.json`.

```bash
python scripts/benchmark_pipeline.py --manifest benchmarks/manifest.local.json --dry-run
python scripts/benchmark_pipeline.py --manifest benchmarks/manifest.local.json --skip-llm
python scripts/benchmark_pipeline.py --manifest benchmarks/manifest.local.json
```

The harness writes `results.json`, `results.csv`, and `report.md` under `logs/benchmarks/YYYYMMDD-HHMMSS/`. See `benchmarks/datasets.md` for recommended open German/English sources such as Common Voice, FLEURS, LibriSpeech, and MLS.

## Optional Silero VAD

The default VAD mode is `auto`: LocalMeetingCopilot tries Silero VAD when `silero-vad` is installed and falls back to the built-in energy VAD otherwise.

```bash
python -m pip install -r requirements-vad.txt
export LMC_VAD_MODE=auto
python run.py --mac-live --profile de
```

The startup status shows the real backend as `VAD: silero` or `VAD: energy`.

## MVP Scope

- PySide6 floating overlay with live original text and Chinese translation.
- Dashboard with transcript history, search, meeting controls, and report export.
- Ollama translation using `qwen2.5:3b-instruct`.
- Single-lane translation queue so Ollama responses remain ordered.
- Auto summary on End with instant local preview and Ollama refinement.
- Transcript filters for all speakers, [Me], remote speakers, and task-like entries.
- Dashboard controls for profile, preset, style, devices, tracks, privacy, and debug audio.
- Quick tuning buttons for `fast`, `balanced`, and `accurate`.
- Dashboard VAD sensitivity control.
- Saved runtime settings through local `settings.json`.
- Speaker correction and future speaker alias memory in the dashboard.
- Latency diagnostics for ASR, LLM, and total sentence time.
- Rolling latency distribution for ASR, LLM, queue, and total response time.
- Custom vocabulary injection through `profiles/custom_terms.txt`.
- Common ASR hallucination phrase filtering.
- Partial subtitles during active speech, followed by final translated subtitles.
- Streaming Chinese translation updates while Ollama is generating.
- Short-sentence and German clause merge buffers for more natural translations.
- Mock meeting mode for local UI and translation testing.
- Local microphone capture with Silero/energy VAD sentence segmentation.
- macOS experimental live mode with local mic as `[Me]` and a virtual/app remote input as remote audio.
- Windows live mode with local mic as `[Me]` and WASAPI loopback as remote audio.
- First-pass Teams/Zoom active speaker detection through colored speaker borders and OCR.
- WAV transcription through `faster-whisper`.
- Markdown and JSON meeting report export into `logs/`.

## Windows Notes

Recommended first setup on Windows 11:

```powershell
cd C:\path\to\LocalMeetingCopilot
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py --check
```

Or run the smoke script:

```powershell
.\scripts\windows_smoke.ps1
```

If PowerShell execution policy blocks local scripts:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows_smoke.ps1
```

Start the real meeting mode:

```powershell
.\.venv\Scripts\python.exe run.py --live
```

The batch shortcut does the same setup and starts live mode:

```cmd
scripts\run_windows.bat
```

If `run.py --check` shows several microphones or loopback devices, choose explicit indexes:

```powershell
$env:LMC_MIC_DEVICE_INDEX="0"
$env:LMC_LOOPBACK_DEVICE_INDEX="4"
.\.venv\Scripts\python.exe run.py --live --profile de
```

On macOS, `python run.py --live` intentionally reports that Windows WASAPI loopback is Windows-only. Use `python run.py --mac-live` for the local Mac experiment path.

## Windows Validation Path

1. Install Python 3.11 x64, Ollama, and the same Python requirements.
2. Run `python run.py --check` and confirm Ollama plus input devices are visible.
3. Run `python run.py --model-check --profile de` and follow any printed fix commands.
4. If anything looks wrong, run `python run.py --support-bundle --profile de` and share the generated zip.
5. Run `python run.py --mock` to verify UI and translation first.
6. Run `python run.py --live` in a real Teams/Zoom call.
7. Confirm `[Me]` maps to the local microphone and remote audio maps to loopback.
8. Confirm active speaker OCR. If it fails, the transcript should still fall back to `[Remote Participant]`.

## Privacy

The MVP does not save raw audio by default. Reports contain only transcript text and translations. Use `--privacy` or the dashboard Privacy toggle to preview reports without writing Markdown/JSON files. `python run.py --doctor` stores environment metadata but no audio or transcript contents. Use `--debug-audio` only while diagnosing ASR issues; it writes completed speech chunks into `logs/debug_audio/`.

# 中文操作指南

LocalMeetingCopilot 是一个本地优先的桌面会议助手，主要服务于需要参加德语/英语会议的中文用户。当前版本可以在 macOS 上用 mock、麦克风、WAV 文件或 macOS 双轨实验模式运行；在 Windows 上支持本地麦克风加 WASAPI loopback 的真实会议模式。

## 快速开始

```bash
cd /Users/yuanxiaoyu/projects/LocalMeetingCopilot
source .venv/bin/activate
python run.py --check
python run.py --model-check --profile de
python run.py --mock
```

在 macOS 上只测试本地麦克风：

```bash
python run.py --mic
```

第一次运行时，macOS 可能会要求麦克风权限。如果你需要指定输入设备，先运行：

```bash
python run.py --check
```

然后设置设备 index：

```bash
export LMC_MIC_DEVICE_INDEX=0
python run.py --mic
```

## 模型预检

进入真实会议前，先检查本地 ASR 和 Ollama 模型：

```bash
python run.py --model-check --profile de --preset fast --style meeting
```

这个命令会检查 Python package、`models/` 下的 faster-whisper 缓存、Ollama CLI，以及当前配置的 Ollama 模型。它不会自动下载任何东西；如果缺模型，会返回非 0，并打印明确修复命令，例如 `ollama pull qwen2.5:3b-instruct`。

## 诊断包

如果你的朋友在 Windows 或 macOS 上遇到和你本机不一样的问题，可以让她运行：

```bash
python run.py --doctor --profile de --preset fast --style meeting
```

命令会在 `logs/diagnostics/diagnostic_YYYYMMDD_HHMMSS/` 下生成一个可分享的诊断文件夹，包含 `report.md`、`system.json`、`audio_devices.json`、`ollama.json`、`models.json`、`config.json`、`git.txt` 和 `python_packages.txt`。诊断包只记录环境元信息、设备名称、当前音频 index、Ollama 状态、模型预检状态、Git 状态和最近日志文件名，不录音，也不会读取逐字稿内容。

## Support Bundle

远程排查时，可以让测试者只跑一个命令：

```bash
python run.py --support-bundle --profile de --preset fast --style meeting
```

它会生成 `logs/support/support_YYYYMMDD_HHMMSS.zip`，里面包含 `--check`、`--model-check` 和 doctor 输出。默认不会监听麦克风。如果需要同时做音频/VAD 校准，需要显式开启：

```bash
python run.py --support-bundle --profile de --support-include-audio-test --audio-test-seconds 8
```

## 音频测试与闪退日志

进入真实会议前，可以先跑一个短音频/VAD 校准：

```bash
python run.py --audio-test --profile de --audio-test-seconds 12
```

这个测试不会启动 Whisper 或 Ollama，只会在终端显示麦克风和当前平台远端轨道的实时 RMS/peak 音量、VAD 状态、收到的 chunk 数、speech start 次数和完成切句次数。可以用 `--no-mic-track` 或 `--no-remote-track` 单独排查其中一边。

如果程序意外退出，会把闪退报告写到：

```text
logs/crash/crash_YYYYMMDD_HHMMSS_xxxxxx.txt
```

闪退日志包含 Python/系统元信息和 traceback，后续可以直接根据堆栈定位问题，不用盲猜。

## macOS 双轨实验模式

macOS 不能像 Windows WASAPI loopback 那样直接稳定抓系统回放，所以当前 macOS 双轨实验模式使用“本地麦克风 + 远端输入设备”。远端输入设备可以是 `Microsoft Teams Audio`、`Zoom Audio`、`BlackHole 2ch` 或 `Background Music`。

先查看设备：

```bash
python run.py --check
```

如果输出里出现类似下面的内容：

```text
remote[2]: Microsoft Teams Audio
```

就可以这样启动德语会议模式：

```bash
export LMC_MIC_DEVICE_INDEX=0
export LMC_REMOTE_DEVICE_INDEX=2
python run.py --mac-live --profile de --preset fast --style meeting
```

如果没有远端输入设备，可以安装 BlackHole：

```bash
brew install blackhole-2ch
```

然后打开 macOS 的 Audio MIDI Setup，创建一个 Multi-Output Device，把你的耳机/扬声器和 `BlackHole 2ch` 都加进去。将会议软件或系统输出切到这个 Multi-Output Device，再把 `LMC_REMOTE_DEVICE_INDEX` 设置为 `BlackHole 2ch` 的输入 index。

## WAV 文件转写

```bash
python run.py --wav /absolute/path/to/meeting.wav
```

第一次运行 WAV 转写时，`faster-whisper` 可能会把模型下载到 `models/`。

## Dashboard 控制面板

Dashboard 现在可以直接配置常用运行参数：

- Profile：`de` 纯德语、`en` 纯英语、`de-en` 德英混合。
- Preset：`fast`、`balanced`、`accurate` 三档速度/准确率。
- Tune 快捷按钮：快速切换 `fast` / `balanced` / `accurate`，方便直接比较延迟。
- Style：`literal` 精准直译、`meeting` 会议纪要风、`natural` 自然中文。
- Mic 和 Remote 输入设备选择。
- 本地麦克风轨道和远端音频轨道开关。
- 报告保存、隐私模式、debug WAV 开关。
- End 后自动总结开关。
- VAD sensitivity 滑条，可以调更灵敏或更保守的断句。
- 每句话的 ASR、LLM、总延迟显示。
- Mic 和 Remote 实时音量条，并显示 VAD 当前是 speech 还是 idle。
- 最新完整字幕的 performance timeline 摘要。
- Latency Window 会显示当前调参窗口内 ASR、LLM、Queue、Total 的平均、p95、最大值和目标进度条。
- 说话人修正：选中逐字稿行，把 `Remote Participant` 改成真实姓名，后续相同说话人会自动沿用。
- 运行时设置会保存到 `settings.json`，下次启动自动恢复。

建议在点击 Start 前选择音频设备和 ASR 模型档位。翻译风格、隐私模式、报告保存开关和说话人别名可以在运行中调整。

## 语言频道与延迟

Whisper 是一个整体的多语言模型，不能像“语言包”一样删除阿拉伯语、法语等能力。LocalMeetingCopilot 当前采用应用层语言闸门：

- `--profile de`：纯德语频道，ASR 强制德语，速度更快，也更不容易幻听成其他语言。
- `--profile en`：纯英语频道，ASR 强制英语。
- `--profile de-en`：德英混合频道，只在德语/英语之间自动检测，检测失败时 fallback 到德语。
- 每个 profile 都会注入会议常见词表和 hotwords。
- 如果 ASR 最终仍识别成不支持的语言，这句话会被丢弃，不进入翻译队列。
- 实时 VAD 已调低静音切句时间，尽量减少“说完后等字幕”的体感延迟。
- 说话中会显示 partial 临时字幕；完整句切好以后再进入精修翻译。
- Ollama 生成中文时会流式更新到悬浮窗，不再等整段响应完成才显示。
- 会议结束后会先显示本地规则 summary，随后用 Ollama 精修版替换。
- 德语从句片段会短暂等待并尝试合并，重点处理 `weil`、`dass`、`wenn`、`obwohl` 等结构。

德语会议推荐：

```bash
python run.py --mac-live --profile de --preset fast --style meeting
```

德英混合会议：

```bash
python run.py --mac-live --profile de-en --preset fast --style meeting
```

也可以设置默认 profile：

```bash
export LMC_MEETING_PROFILE=de
```

如果 Ollama 请求卡住，或者退出时等待太久，可以调低本地请求超时：

```bash
export LMC_OLLAMA_TIMEOUT_SECONDS=20
```

常用命令组合：

```bash
python run.py --mac-live --profile de --preset fast --style meeting
python run.py --mac-live --profile de --preset accurate --style literal
python run.py --mac-live --profile de --privacy
python run.py --mac-live --profile de --debug-audio
python run.py --mac-live --profile de --no-remote-track
```

Preset 含义：

- `fast`：base Whisper，高 VAD 灵敏度、较短上下文、优先流式翻译，最适合实时字幕。
- `balanced`：small Whisper，中等 VAD 灵敏度，稍慢但更准。
- `accurate`：medium Whisper，较保守断句和更宽 beam，更适合 WAV/offline 或性能较强的机器。

翻译风格：

- `literal`：尽量精准保留细节。
- `meeting`：简洁会议纪要风。
- `natural`：更自然的口语中文。

性能开关：

```bash
export LMC_WARMUP=1
export LMC_PARTIAL_SKIP_WHEN_ASR_BUSY=1
export LMC_OLLAMA_TIMEOUT_SECONDS=20
export LMC_SHUTDOWN_WAIT_MS=8000
export LMC_TRANSLATION_CACHE=1
export LMC_TRANSLATION_CACHE_PERSIST=1
export LMC_PERFORMANCE_LOGGING=1
```

Warmup 会在启动后提前加载 Whisper 并唤醒 Ollama。`ja`、`genau`、`okay`、`mhm` 这类常见语气词会走本地翻译，不再等待 Ollama。短句会自动使用更小的 Ollama 输出上限。重复的完整句翻译会缓存；隐私模式关闭时才会把磁盘缓存写到 `logs/cache/translation_cache.jsonl`。Performance timeline 会写到 `logs/performance/performance_YYYYMMDD.jsonl`，只包含耗时元信息和字符数，不包含逐字稿正文；隐私模式开启时不会写入。退出时会短暂等待后台翻译收尾。

## 自定义词库

自定义词库文件：

```text
profiles/custom_terms.txt
profiles/terms.yaml
```

公司名、人名、项目名、缩写、普通 ASR 术语可以一行一个写进 `profiles/custom_terms.txt`。需要精确中文翻译的术语写进 `profiles/terms.yaml`：

```yaml
- source: Kundentabelle
  variants: ["Kunden Tabelle", "customer table"]
  zh: 客户表
  category: data
  priority: high
```

`.txt` 词库继续用于 ASR prompt 和 hotwords。结构化 YAML 词库会按每句话动态匹配，只把最相关的 top terms 注入翻译 prompt。

## Benchmark Harness

把公开 benchmark 音频放到 `benchmarks/audio/`，然后复制并修改 `benchmarks/manifest.example.json` 为 `benchmarks/manifest.local.json`。

```bash
python scripts/benchmark_pipeline.py --manifest benchmarks/manifest.local.json --dry-run
python scripts/benchmark_pipeline.py --manifest benchmarks/manifest.local.json --skip-llm
python scripts/benchmark_pipeline.py --manifest benchmarks/manifest.local.json
```

脚本会把 `results.json`、`results.csv` 和 `report.md` 输出到 `logs/benchmarks/YYYYMMDD-HHMMSS/`。推荐数据源见 `benchmarks/datasets.md`，包括 Common Voice、FLEURS、LibriSpeech 和 MLS。

## 可选 Silero VAD

默认 VAD 模式是 `auto`：如果本机安装了 `silero-vad`，会优先使用 Silero；如果没有安装，会自动回退到内置 energy VAD。

```bash
python -m pip install -r requirements-vad.txt
export LMC_VAD_MODE=auto
python run.py --mac-live --profile de
```

启动状态里会显示真实后端，例如 `VAD: silero` 或 `VAD: energy`。

## 当前功能范围

- PySide6 悬浮字幕条，显示原文和中文翻译。
- Dashboard 逐字稿历史、搜索、控制、总结、导出。
- Ollama 本地翻译，默认模型 `qwen2.5:3b-instruct`。
- 单通道翻译队列，保证 Ollama 输出顺序。
- End 后自动总结：先出本地预览，再用 Ollama 精修。
- `[Me]`、Remote、Tasks 等过滤。
- Profile、Preset、Style、设备、轨道、隐私、debug 音频控制。
- `fast`、`balanced`、`accurate` 快捷调参按钮。
- Dashboard VAD 灵敏度控制。
- 通过本地 `settings.json` 保存运行时设置。
- Dashboard 里修正说话人，并记住后续同名发言。
- ASR/LLM/总耗时延迟诊断。
- ASR、LLM、queue、总响应耗时的 rolling latency 分布。
- 自定义词库注入。
- 常见 ASR 幻听短语过滤。
- 说话中的 partial 临时字幕，完整句结束后再显示精修翻译。
- Ollama 生成中文时流式更新字幕。
- 短句和德语从句合并缓冲，让德语碎句翻译更自然。
- macOS 本地实验模式。
- Windows 本地 mic + WASAPI loopback 真实会议模式。
- Teams/Zoom 说话人 OCR 初版识别和缓存。
- WAV 文件转写。
- Markdown 和 JSON 报告导出。

## Windows 使用说明

Windows 11 首次设置：

```powershell
cd C:\path\to\LocalMeetingCopilot
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py --check
```

也可以运行冒烟脚本：

```powershell
.\scripts\windows_smoke.ps1
```

如果 PowerShell 执行策略拦截：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows_smoke.ps1
```

真实会议模式：

```powershell
.\.venv\Scripts\python.exe run.py --live --profile de
```

批处理快捷启动：

```cmd
scripts\run_windows.bat --profile de
```

如果 `run.py --check` 显示多个麦克风或 loopback 设备，可以指定 index：

```powershell
$env:LMC_MIC_DEVICE_INDEX="0"
$env:LMC_LOOPBACK_DEVICE_INDEX="4"
.\.venv\Scripts\python.exe run.py --live --profile de
```

macOS 上运行 `python run.py --live` 会提示 Windows WASAPI loopback 仅支持 Windows。macOS 请使用：

```bash
python run.py --mac-live --profile de
```

## Windows 验证路径

1. 安装 Python 3.11 x64、Ollama 和 Python requirements。
2. 运行 `python run.py --check`，确认 Ollama、麦克风、loopback 设备可见。
3. 运行 `python run.py --model-check --profile de`，按输出里的 fix command 修复缺失模型。
4. 如果环境不对，运行 `python run.py --support-bundle --profile de`，把生成的 zip 发回来。
5. 先运行 `python run.py --mock` 验证 UI 和翻译。
6. 在真实 Teams/Zoom 会议中运行 `python run.py --live --profile de`。
7. 确认 `[Me]` 对应本地麦克风，远端发言对应 loopback。
8. 确认 Teams/Zoom 说话人 OCR。如果失败，逐字稿仍会 fallback 到 `Remote Participant`。

## 隐私

默认不保存原始音频。报告只包含逐字稿和翻译。使用 `--privacy` 或 Dashboard 里的 Privacy 开关，可以只预览报告、不写 Markdown/JSON 到磁盘。`python run.py --doctor` 只保存环境元信息，不录音，也不读取逐字稿内容。只有开启 `--debug-audio` 时，才会把切好的语音片段写入 `logs/debug_audio/`，用于排查 ASR 问题。
