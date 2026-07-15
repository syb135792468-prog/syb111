"""
agents/video_agent.py - 软件杯A3 视频生成智能体
功能：生成带浏览器原生语音配音的HTML教学动画，GSAP驱动
规范：统一继承BaseAgent，适配LangGraph工作流，工程化标准实现

架构：模板驱动（骨架固定，数据填充）
  阶段1：LLM 生成结构化教学脚本（JSON）
  阶段2：脚本数据注入固定 HTML 模板（零 LLM 调用）
  降级：脚本阶段失败时，回退到 LLM 直接生成 HTML
"""
from __future__ import annotations

import asyncio
import base64
from html import escape
import json
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from agents.base_agent import BaseAgent
from agents.video_schema import parse_script, AnimationScript, ValidationResult
from graph.state import ResourceItem
from config.constants import (
    VIDEO_MAX_TOKENS, VIDEO_MIN_HTML_LINES, VIDEO_MAX_RETRIES,
    VIDEO_DEFAULT_VOICE_RATE, VIDEO_DEFAULT_VOICE_LANG,
    VIDEO_DEFAULT_STYLE, VIDEO_DEFAULT_DURATION,
    VIDEO_GSAP_CDN_URL,
    VIDEO_MIN_CODE_LINES, VIDEO_MIN_SPEAK_CALLS,
    RESOURCE_PROGRESS_COMPLETE, DEFAULT_TOPIC, RESOURCE_STATUS_COMPLETED,
    VIDEO_TTS_MAX_CONCURRENCY, VIDEO_OUTPUT_DIR,
)
from utils.agent_helpers import match_knowledge_point, get_profile_from_context
from utils.video_cache import (
    get_cached_video, save_cached_video,
    _compute_cache_key, _AUDIO_CACHE_DIR, _ensure_audio_cache_dir,
)
from utils.tts_api import tts_client
from config.model_config import TTS_CONFIG

# 脚本生成参数
SCRIPT_MIN_STEPS = 5
SCRIPT_MAX_STEPS = 8
SCRIPT_MAX_TOKENS = 8000
SCRIPT_MAX_RETRIES = 1

# 静态资源路径
_ASSETS_DIR = Path(__file__).parent.parent / "assets" / "animation"
_TEMPLATE_PATH = _ASSETS_DIR / "player_template.html"

# 线程安全的模板缓存锁
_TEMPLATE_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def _get_template() -> str:
    """读取 HTML 模板，使用 lru_cache 实现线程安全缓存"""
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def _load_asset_file(filename: str, default: str = "") -> str:
    """从 assets/animation 目录加载文件，失败时返回默认值"""
    file_path = _ASSETS_DIR / filename
    try:
        return file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default


def _load_helper_functions_js() -> str:
    """加载辅助函数 JS（从外部文件）"""
    content = _load_asset_file("helper_functions.js")
    if content:
        return f"<script>\n{content}\n</script>"
    # 降级：返回内置精简版本
    return _FALLBACK_HELPER_JS


def _load_control_logic_js() -> str:
    """加载播放控制逻辑 JS（从外部文件）"""
    content = _load_asset_file("control_logic.js")
    if content:
        return f"<script>\n{content}\n</script>"
    return _FALLBACK_CONTROL_JS


def _load_compatibility_warning_html() -> str:
    """加载浏览器兼容性提示 HTML（从外部文件）"""
    return _load_asset_file("compatibility_warning.html", _FALLBACK_COMPAT_WARNING)


def _load_design_css() -> str:
    """从 assets/animation/design_system.css 加载设计系统，失败时返回空"""
    css_file = _ASSETS_DIR / "design_system.css"
    try:
        return f"<style>\n{css_file.read_text(encoding='utf-8')}\n</style>"
    except FileNotFoundError:
        return ""


# ============================================================
# 降级兜底版本（外部文件加载失败时使用）
# ============================================================
_FALLBACK_HELPER_JS = """<script>
function highlightSyntax(code) {
  var escaped = code.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  escaped = escaped.replace(/(#.*)$/gm, '<span class="cmt">$1</span>');
  escaped = escaped.replace(/(\"\"\"[\\s\\S]*?\"\"\"|'''[\\s\\S]*?'''|"(?:[^"\\\\]|\\\\.)*"|'(?:[^'\\\\]|\\\\.)*')/g, '<span class="str">$1</span>');
  escaped = escaped.replace(/\\b(def|class|if|elif|else|for|while|return|import|from|try|except|finally|with|as|yield|lambda|pass|break|continue|raise|and|or|not|in|is|True|False|None|self|print)\\b/g, function(m) {
    if (m === 'self') return '<span class="self">' + m + '</span>';
    return '<span class="kw">' + m + '</span>';
  });
  escaped = escaped.replace(/\\b(\\d+\\.?\\d*)\\b/g, '<span class="num">$1</span>');
  return escaped;
}
function renderCode(code, highlights) {
  var lines = code.split('\\n');
  var html = '';
  for (var i = 0; i < lines.length; i++) {
    var hl = highlights && highlights.indexOf(i + 1) >= 0 ? ' highlight' : '';
    html += '<div class="code-line' + hl + '"><span class="line-num">' + (i+1) + '</span>' + highlightSyntax(lines[i]) + '</div>';
  }
  document.getElementById('codeDisplay').innerHTML = html;
}
function speak(text, callback) {
  if (!('speechSynthesis' in window)) { if (callback) setTimeout(callback, 2000); return; }
  window.speechSynthesis.cancel();
  var u = new SpeechSynthesisUtterance(text);
  u.lang = 'zh-CN';
  u.rate = window.speechRate || 1.0;
  if (callback) u.onend = callback;
  window.speechSynthesis.speak(u);
  var bar = document.getElementById('subtitleBar');
  if (bar) { bar.textContent = text; bar.style.display = 'block'; }
}
function updateProgress(percent) { document.getElementById('progressFill').style.width = percent + '%'; }
</script>"""

_FALLBACK_CONTROL_JS = """<script>
document.getElementById('startButton').addEventListener('click', () => {
  if (typeof startAnimation === 'function') startAnimation();
  else { document.getElementById('startScreen').style.display = 'none'; document.getElementById('playerScreen').style.display = 'block'; }
});
document.getElementById('playPauseButton').addEventListener('click', () => {
  if (window.isPlaying) { if (typeof pauseAnimation === 'function') pauseAnimation(); document.getElementById('playPauseButton').textContent = '▶'; }
  else { if (typeof resumeAnimation === 'function') resumeAnimation(); document.getElementById('playPauseButton').textContent = '⏸'; }
  window.isPlaying = !window.isPlaying;
});
document.getElementById('restartButton').addEventListener('click', () => {
  if (typeof restartAnimation === 'function') restartAnimation();
  else { window.speechSynthesis.cancel(); window.isPlaying = false; document.getElementById('progressFill').style.width = '0%'; document.getElementById('playerScreen').style.display = 'none'; document.getElementById('startScreen').style.display = 'flex'; }
});
document.getElementById('progressBar').addEventListener('click', (e) => {
  const rect = e.currentTarget.getBoundingClientRect();
  const percent = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
  document.getElementById('progressFill').style.width = percent + '%';
  if (typeof seekTo === 'function') seekTo(percent);
});
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.code === 'Space') { e.preventDefault(); document.getElementById('playPauseButton').click(); }
  if (e.code === 'KeyR') { e.preventDefault(); document.getElementById('restartButton').click(); }
});
</script>"""

_FALLBACK_COMPAT_WARNING = """<div id="noVoiceWarning" style="display:none;position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#ff6b6b;color:white;padding:12px 24px;border-radius:8px;z-index:9999;font-size:16px;">⚠️ 您的浏览器不支持语音合成，将使用纯文字模式</div><script>if (!('speechSynthesis' in window)) { document.getElementById('noVoiceWarning').style.display = 'block'; setTimeout(() => { document.getElementById('noVoiceWarning').style.display = 'none'; }, 5000); }</script>"""

class VideoAgent(BaseAgent):
    """
    视频资源生成智能体
    生成HTML格式的教学动画，LLM用GSAP自由编写动画代码

    架构：
    - LLM用GSAP编写完整动画代码（自由发挥，效果丰富）
    - 后处理注入GSAP CDN（保证加载）+ 播放控制逻辑（保证交互）
    """

    def __init__(
        self,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            agent_name="video",
            scene_name="video_html_generation",
            enable_rag=False,
            user_id=user_id,
            task_id=task_id,
        )

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, str, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        target_kp = self._get_target_kp(user_input, context)
        video_config = self._build_video_config((context or {}).get("config", {}))

        # 检查缓存（跳过自定义prompt的情况）
        custom_prompt = video_config.get("custom_prompt", "")
        if not custom_prompt:
            cached_html = get_cached_video(target_kp, video_config)
            if cached_html:
                self.logger.info(f"[缓存命中] 使用缓存的教学视频：{target_kp}")
                resource = self._build_resource(cached_html, target_kp, video_config)
                new_resources = self._append_resource(context, resource)
                return self._build_result(new_resources)

        try:
            self.logger.info(f"开始生成教学视频，知识点：{target_kp}")
            self.logger.info(f"视频配置: {video_config}")

            html_code = await self._generate_with_retry(target_kp, video_config, progress_callback)
            if not html_code or len(html_code.strip()) < 50:
                self.logger.error(f"LLM返回的HTML过短或为空，长度: {len(html_code) if html_code else 0}")
                raise ValueError("LLM返回的HTML内容无效")

            self.logger.info(f"LLM返回HTML长度: {len(html_code)} 字符")
            # 模板路径已包含完整CSS/JS/控制逻辑，跳过后处理
            if "animationData" not in html_code:
                html_code = self._enhance_animation(html_code, video_config)
            html_code = self._validate_html(html_code)

            # 质量评分（模板路径跳过，评分只对降级路径有意义）
            if "animationData" not in html_code:
                quality = self._score_html_quality(html_code, target_kp)
                self.logger.info(f"质量评分: {quality['total']}/100 {quality['breakdown']}")

            # 保存到缓存（跳过自定义prompt的情况）
            if not custom_prompt:
                save_cached_video(target_kp, video_config, html_code)
                self.logger.info(f"[缓存保存] 教学视频已缓存：{target_kp}")

            resource = self._build_resource(html_code, target_kp, video_config)
            new_resources = self._append_resource(context, resource)

            self.logger.info(f"教学视频生成完成：{resource.title}")
            return self._build_result(new_resources)

        except Exception as e:
            self.logger.error(f"视频生成失败：{type(e).__name__}: {str(e)}", exc_info=True)
            fallback_html = self._get_fallback_html(target_kp, str(e))
            resource = self._build_resource(fallback_html, target_kp, video_config)
            new_resources = self._append_resource(context, resource)
            self.logger.info(f"已返回兜底页面：{resource.title}")
            return self._build_result(new_resources)

    @staticmethod
    def _build_video_config(config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "duration": config.get("duration", VIDEO_DEFAULT_DURATION),
            "style": config.get("style", VIDEO_DEFAULT_STYLE),
            "voice_rate": config.get("voice_rate", VIDEO_DEFAULT_VOICE_RATE),
            "voice_lang": config.get("voice_lang", VIDEO_DEFAULT_VOICE_LANG),
            "custom_prompt": config.get("customPrompt", ""),
            "voice_id": config.get("voice_id") or TTS_CONFIG.default_voice_id,
        }

    # ================================================================
    # 三阶段流水线：脚本 → HTML → 后处理
    # ================================================================

    async def _generate_script(self, topic: str, video_config: Dict[str, Any]) -> Optional[AnimationScript]:
        """阶段1：生成结构化教学脚本（JSON）"""
        self.logger.info(f"[阶段1] 生成教学脚本：{topic}")

        duration = video_config["duration"]
        # 按目标时长计算每步旁白字数上限
        # 语音语速 ~4.5字/秒（1.15x），每步动画开销 ~0.6秒
        animation_overhead = 0.6
        voice_speed = 4.5
        total_voice_time = duration - (SCRIPT_MAX_STEPS * animation_overhead)
        per_step_voice_time = total_voice_time / SCRIPT_MAX_STEPS
        max_chars = max(20, int(per_step_voice_time * voice_speed))

        system_prompt = self._load_prompt("video_script_system",
            duration=duration,
            style=video_config["style"],
            min_steps=SCRIPT_MIN_STEPS,
            max_steps=SCRIPT_MAX_STEPS,
            max_chars=max_chars,
        )
        user_prompt = self._load_prompt("video_script_user",
            topic=topic,
            duration=duration,
            style=video_config["style"],
            min_steps=SCRIPT_MIN_STEPS,
            max_steps=SCRIPT_MAX_STEPS,
        )

        last_errors = []
        for attempt in range(SCRIPT_MAX_RETRIES + 1):
            # 重试时只保留「系统提示 + 最新错误反馈 + 用户原始需求」，不叠加历史失败回复
            if attempt == 0:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            else:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": (
                        f"上次生成失败，错误如下：\n{chr(10).join(last_errors)}\n\n"
                        f"请修正后重新输出。原始需求：\n{user_prompt}"
                    )},
                ]

            try:
                response = await self._call_llm(messages, max_tokens=SCRIPT_MAX_TOKENS, response_format={"type": "json_object"})
                raw_text = response.strip()

                # 提取 JSON（LLM 可能包裹在 ```json ``` 中）
                json_match = re.search(r"```json\s*\n(.*?)```", raw_text, re.DOTALL)
                if json_match:
                    raw_text = json_match.group(1).strip()
                elif not raw_text.startswith("{"):
                    # 尝试找到第一个 {
                    brace_pos = raw_text.find("{")
                    if brace_pos > 0:
                        raw_text = raw_text[brace_pos:]

                script, validation = parse_script(raw_text, topic)

                if script:
                    self.logger.info(
                        f"[阶段1] 脚本生成成功（第{attempt + 1}次）："
                        f"{len(script.steps)}步, 主题={script.meta.topic}"
                    )
                    if validation.warnings:
                        self.logger.info(f"[阶段1] 警告：{validation.warnings}")
                    return script

                last_errors = validation.errors
                self.logger.warning(
                    f"[阶段1] 第{attempt + 1}次脚本校验失败：{validation.errors}"
                )

            except Exception as e:
                self.logger.warning(f"[阶段1] 第{attempt + 1}次异常：{e}")
                last_errors = [str(e)]

        self.logger.error(f"[阶段1] 脚本生成失败，错误：{last_errors}")
        return None

    @staticmethod
    def _render_from_script(script: AnimationScript, video_config: Dict[str, Any]) -> str:
        """阶段2：脚本数据注入固定模板（零 LLM 调用，100% 稳定）"""
        template = _get_template()

        # 构建步骤 JSON（字段名与模板 JS 严格对应）
        steps_json = []
        for step in script.steps:
            steps_json.append({
                "title": step.title,
                "narration": step.narration,
                "code_content": step.code_snippet,
                "highlight_lines": step.highlight_lines,
                "variable_panel": step.variable_panel,
                "code_animation": step.code_animation,
                "bubble_animation": step.bubble_animation,
                # flowchart 风格字段（chart_type != code_walkthrough 时由 template JS 使用）
                "nodes": step.nodes,
                "edges": step.edges,
                # TTS 音频字段（后端注入，无音频时为 None/空，前端走 Web Speech 降级）
                "audio_url": step.audio_url,
                "audio_base64": step.audio_base64,
                "word_timestamps": step.word_timestamps,
                "audio_duration_ms": step.audio_duration_ms,
            })

        # 学习目标 HTML
        goals = script.meta.learning_goal.split("；") if script.meta.learning_goal else []
        goals = [g.strip() for g in goals if g.strip()][:4]
        if len(goals) < 2:
            goals = [f"理解{script.meta.topic}的核心概念", "掌握基本用法", "能够独立编写代码"]
        goals_html = "\n".join(f"                <li>{escape(g)}</li>" for g in goals)

        # 总结要点
        key_points = script.summary.key_points or [f"掌握了{script.meta.topic}的核心用法"]
        key_points_html = "\n".join(f"                <li>{escape(p)}</li>" for p in key_points)

        # 步骤圆点
        dots_html = "\n".join('                <div class="step-dot"></div>' for _ in script.steps)

        # 代码文件名
        code_filename = script.meta.topic.replace(" ", "_") + ".py"

        # 替换占位符（逐个替换，顺序无关）
        html = template
        html = html.replace("__TOPIC__", script.meta.topic)
        # JS 字符串上下文用 json.dumps 转义，防止引号/特殊字符破坏语法
        html = html.replace("__TOPIC_JSON__", json.dumps(script.meta.topic, ensure_ascii=False))
        html = html.replace("__CHART_TYPE_JSON__", json.dumps(script.meta.chart_type, ensure_ascii=False))
        html = html.replace("__SUBTITLE__", script.meta.topic)
        html = html.replace("__LEARNING_GOALS__", goals_html)
        html = html.replace("__DURATION__", str(script.meta.duration))
        html = html.replace("__TOTAL_STEPS__", str(len(script.steps)))
        html = html.replace("__STEP_DOTS__", dots_html)
        html = html.replace("__STEPS_JSON__", json.dumps(steps_json, ensure_ascii=False))
        html = html.replace("__KEY_POINTS_JSON__", json.dumps(key_points, ensure_ascii=False))
        html = html.replace("__KEY_POINTS__", key_points_html)
        html = html.replace("__ENDING_TEXT__", script.summary.ending_text or "恭喜你掌握了本节内容！")
        html = html.replace("__ENDING_TEXT_JSON__", json.dumps(script.summary.ending_text or "恭喜你掌握了本节内容！", ensure_ascii=False))
        html = html.replace("__VOICE_RATE__", str(video_config.get("voice_rate", 1.0)))
        html = html.replace("__CODE_FILENAME__", code_filename)
        html = html.replace("__CODE_FILENAME_JSON__", json.dumps(code_filename, ensure_ascii=False))

        return html

    async def _generate_with_retry(
        self,
        topic: str,
        video_config: Dict[str, Any],
        progress_callback: Optional[Callable[[int, str, str], Awaitable[None]]] = None,
    ) -> str:
        """脚本 -> TTS音频 -> 模板注入，失败时降级到 LLM 直接生成"""

        async def _report(percent: int, stage: str, message: str) -> None:
            if progress_callback is not None:
                try:
                    await progress_callback(percent, stage, message)
                except Exception:
                    pass

        # --- 阶段1：生成脚本 ---
        await _report(5, "script", "生成视频脚本")
        script = await self._generate_script(topic, video_config)

        if script:
            # --- 阶段1.5：批量生成 TTS 音频（失败则降级 Web Speech）---
            if tts_client.is_enabled():
                await _report(15, "audio", "合成语音")
                try:
                    cache_key = _compute_cache_key(topic, video_config)
                    await self._generate_audio_batch(script, video_config["voice_id"], cache_key, progress_callback)
                    self.logger.info(f"[TTS] 音频生成成功，{len(script.steps)}段")
                except Exception as e:
                    self.logger.warning(f"[TTS] 音频生成失败，降级到 Web Speech：{e}")
                    await _report(60, "render", "音频降级，准备渲染")
            else:
                self.logger.info("[TTS] 未启用，使用 Web Speech 配音")
                await _report(60, "render", "准备渲染视频")

            # --- 阶段2：注入固定模板（零 LLM 调用） ---
            await _report(75, "render", "渲染视频")
            try:
                html = self._render_from_script(script, video_config)
                if html and len(html.strip()) > 200:
                    self.logger.info(f"[模板] 脚本->模板注入成功，{len(html)}字符")
                    await _report(100, "done", "完成")
                    return html
                self.logger.warning("[模板] 生成结果过短，降级到直接生成")
            except Exception as e:
                self.logger.warning(f"[模板] 注入异常，降级到直接生成：{e}")
        else:
            self.logger.warning("[阶段1] 脚本生成失败，降级到直接 HTML 生成")

        # --- 降级：LLM 直接生成 HTML ---
        await _report(80, "render", "降级直接生成")
        html = await self._generate_html_direct(topic, video_config)
        await _report(100, "done", "完成")
        return html

    async def _generate_audio_batch(
        self,
        script: AnimationScript,
        voice_id: str,
        cache_key: str,
        progress_callback: Optional[Callable[[int, str, str], Awaitable[None]]] = None,
    ) -> None:
        """
        阶段1.5：批量生成 TTS 音频并回填到 script.steps

        - 第 0 段：base64 内嵌（写入 step.audio_base64，加 data URI 前缀）
        - 其余段：mp3 文件 + URL（写入 step.audio_url）
        - 同时回填 word_timestamps + audio_duration_ms

        失败时抛异常，调用方负责降级到 Web Speech
        """
        _ensure_audio_cache_dir()
        semaphore = asyncio.Semaphore(VIDEO_TTS_MAX_CONCURRENCY)
        total = len(script.steps)

        async def synthesize_one(idx: int, text: str):
            async with semaphore:
                return idx, await tts_client.synthesize(text, voice_id=voice_id)

        tasks = [synthesize_one(i, step.narration) for i, step in enumerate(script.steps)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 任一段失败则抛出，整体降级
        for result in results:
            if isinstance(result, Exception):
                raise result

        # 回填到 script.steps + 按段报告进度（15% -> 75%，区间 60%）
        for idx, tts_result in results:
            step = script.steps[idx]
            step.audio_duration_ms = tts_result.duration_ms
            step.word_timestamps = tts_result.word_timestamps
            if idx == 0:
                # 第一段：base64 内嵌（加 data URI 前缀方便前端直接用）
                step.audio_base64 = f"data:audio/mp3;base64,{tts_result.audio_b64}"
            else:
                # 其余段：写文件 + URL
                audio_file = _AUDIO_CACHE_DIR / f"{cache_key}_{idx}.mp3"
                audio_file.write_bytes(base64.b64decode(tts_result.audio_b64))
                step.audio_url = f"/{VIDEO_OUTPUT_DIR}/cache/audio/{cache_key}_{idx}.mp3"

            if progress_callback is not None and total > 0:
                percent = 15 + int(60 * (idx + 1) / total)
                try:
                    await progress_callback(percent, "audio", f"合成语音 {idx + 1}/{total}")
                except Exception:
                    pass

    async def _generate_html_direct(self, topic: str, video_config: Dict[str, Any]) -> str:
        """降级方案：直接生成 HTML（绕过脚本阶段）"""
        last_html = ""
        for attempt in range(VIDEO_MAX_RETRIES + 1):
            html = await self._generate_html_with_voice(topic, video_config)
            line_count = html.count("\n") + 1
            code_line_count = max(
                html.count('id="codeLine'),
                html.count('class="code-line'),
                html.count('class="code_line'),
            )
            speak_count = html.count("speak(")

            if (line_count >= VIDEO_MIN_HTML_LINES
                    and code_line_count >= VIDEO_MIN_CODE_LINES
                    and speak_count >= VIDEO_MIN_SPEAK_CALLS):
                self.logger.info(
                    f"[降级] HTML质量达标（第{attempt + 1}次）：{line_count}行, "
                    f"{code_line_count}个代码行, {speak_count}段讲解"
                )
                return html

            last_html = html
            issues = []
            if line_count < VIDEO_MIN_HTML_LINES:
                issues.append(f"行数{line_count}<{VIDEO_MIN_HTML_LINES}")
            if code_line_count < VIDEO_MIN_CODE_LINES:
                issues.append(f"代码行{code_line_count}<{VIDEO_MIN_CODE_LINES}")
            if speak_count < VIDEO_MIN_SPEAK_CALLS:
                issues.append(f"讲解段{speak_count}<{VIDEO_MIN_SPEAK_CALLS}")
            self.logger.warning(
                f"[降级] 第{attempt + 1}次内容不足：{', '.join(issues)}，"
                f"{'重试中...' if attempt < VIDEO_MAX_RETRIES else '使用最后结果'}"
            )

        return last_html

    @staticmethod
    def _extract_html(response: str) -> str:
        """从 LLM 响应中提取 HTML 代码"""
        html = response.strip()

        # 提取 ```html ... ``` 代码块
        code_block = re.search(r"```html\s*\n(.*?)```", html, re.DOTALL)
        if code_block:
            html = code_block.group(1).strip()
        else:
            # 找到 <!DOCTYPE html> 或 <html 的位置
            doctype_pos = html.lower().find("<!doctype html")
            if doctype_pos < 0:
                doctype_pos = html.lower().find("<html")
            if doctype_pos > 0:
                html = html[doctype_pos:]
            # 去掉末尾可能残留的 ```
            if html.endswith("```"):
                html = html[:-3]

        return html.strip()

    async def _generate_html_with_voice(self, topic: str, video_config: Dict[str, Any]) -> str:
        prompt = self._load_prompt(
            "video_html_generation_user",
            topic=topic,
            duration=video_config["duration"],
            style=video_config["style"],
            voice_rate=video_config["voice_rate"],
            voice_lang=video_config["voice_lang"],
        )

        custom = video_config.get("custom_prompt", "")
        if custom:
            prompt += f"\n\n## 用户额外要求：\n{custom}"

        messages = [{"role": "user", "content": prompt}]
        response = await self._call_llm(messages, max_tokens=VIDEO_MAX_TOKENS)
        return self._extract_html(response)

    def _enhance_animation(self, html_code: str, video_config: Dict[str, Any]) -> str:
        """后处理：注入设计系统 + GSAP CDN + 辅助函数 + 播放控制逻辑"""

        # 1. 注入CSS设计系统变量（如果LLM没有包含）
        if "--bg-primary" not in html_code:
            self.logger.info("CSS设计系统缺失，自动注入")
            css_tag = _load_design_css()
            if css_tag:
                html_code = self._inject_before_head_close(html_code, css_tag)

        # 2. 注入GSAP CDN（LLM用GSAP写动画，必须保证CDN加载）
        if "gsap" not in html_code.lower():
            self.logger.info("GSAP缺失，自动注入CDN")
            html_code = self._inject_before_head_close(
                html_code,
                f'<script src="{VIDEO_GSAP_CDN_URL}"></script>'
            )

        # 3. 注入辅助函数（如果LLM没有包含 renderCode 等）
        if "function renderCode" not in html_code and "renderCode" not in html_code:
            self.logger.info("辅助函数缺失，自动注入")
            html_code = self._inject_before_body_close(html_code, _load_helper_functions_js())

        # 4. 注入播放控制逻辑（仅在LLM未定义控制函数时注入，避免重复绑定）
        has_control = ("function startAnimation" in html_code
                       or "startAnimation =" in html_code
                       or "startAnimation=" in html_code)
        if not has_control:
            self.logger.info("控制函数缺失，注入播放控制逻辑")
            html_code = self._inject_before_body_close(html_code, _load_control_logic_js())

        # 5. 注入浏览器兼容性提示
        if "noVoiceWarning" not in html_code:
            html_code = self._inject_before_body_close(html_code, _load_compatibility_warning_html())

        # 6. 确保关键DOM元素存在
        required_ids = ["startScreen", "startButton", "playerScreen", "mainTitle",
                        "speechBubble", "codeDisplay", "controls", "progressFill",
                        "stepCounter", "memoryPanel", "stepDots", "learningGoals"]
        missing_ids = [eid for eid in required_ids if f'id="{eid}"' not in html_code]
        if missing_ids:
            self.logger.warning(f"HTML缺少关键元素: {missing_ids}")

        return html_code

    @staticmethod
    def _inject_before_body_close(html_code: str, script_tag: str) -> str:
        match = re.search(r'</body\s*>', html_code, re.IGNORECASE)
        if match:
            pos = match.start()
            return html_code[:pos] + "\n" + script_tag + "\n" + html_code[pos:]
        return html_code + "\n" + script_tag

    @staticmethod
    def _inject_before_head_close(html_code: str, tag: str) -> str:
        match = re.search(r'</head\s*>', html_code, re.IGNORECASE)
        if match:
            pos = match.start()
            return html_code[:pos] + "\n" + tag + "\n" + html_code[pos:]
        match2 = re.search(r'<head[^>]*>', html_code, re.IGNORECASE)
        if match2:
            pos = match2.end()
            return html_code[:pos] + "\n" + tag + html_code[pos:]
        return tag + "\n" + html_code

    @staticmethod
    def _validate_html(html_code: str) -> str:
        checks = [
            ("<html", "缺少<html>标签"),
            ("<body", "缺少<body>标签"),
            ("<script", "缺少<script>标签"),
        ]
        html_lower = html_code.lower()
        for tag, msg in checks:
            if tag not in html_lower:
                raise ValueError(f"生成的HTML无效：{msg}")

        if "gsap" not in html_lower:
            raise ValueError("生成的HTML无效：未使用GSAP动画库")

        return html_code

    @staticmethod
    def _score_html_quality(html_code: str, topic: str = "") -> Dict[str, Any]:
        """质量评分：对生成的HTML进行多维度打分（0-100）"""
        scores = {}
        html_lower = html_code.lower()

        # 1. 代码行数（20分）
        code_lines = max(
            html_code.count('id="codeLine'),
            html_code.count('class="code-line'),
            html_code.count('class="code_line'),
        )
        scores["code_lines"] = min(20, code_lines * 3)

        # 2. 讲解段数（20分）
        speak_count = html_code.count("speak(")
        scores["speak_calls"] = min(20, speak_count * 4)

        # 3. DOM完整性（15分）
        required_ids = ["startScreen", "playerScreen", "codeDisplay", "speechBubble",
                        "controls", "memoryPanel", "stepDots", "stepCounter"]
        present = sum(1 for eid in required_ids if f'id="{eid}"' in html_code)
        scores["dom_completeness"] = round(present / len(required_ids) * 15)

        # 4. 动画多样性（15分）
        gsap_calls = len(re.findall(r'gsap\.(to|from|fromTo|timeline)\(', html_code))
        scores["animation_richness"] = min(15, gsap_calls)

        # 5. 设计系统（10分）
        design_vars = ["--bg-primary", "--accent-blue", "--text-primary"]
        design_score = sum(5 for v in design_vars if v in html_code)
        scores["design_system"] = min(10, design_score)

        # 6. HTML结构（10分）
        struct_score = 0
        if "<html" in html_lower: struct_score += 3
        if "<head" in html_lower: struct_score += 2
        if "<body" in html_lower: struct_score += 3
        if "gsap" in html_lower: struct_score += 2
        scores["html_structure"] = struct_score

        # 7. 主题相关性（10分）
        if topic:
            topic_chars = set(topic.replace(" ", "").lower())
            if topic_chars:
                match = sum(1 for c in topic_chars if c in html_lower)
                scores["topic_relevance"] = round(match / len(topic_chars) * 10)
            else:
                scores["topic_relevance"] = 5
        else:
            scores["topic_relevance"] = 5

        total = sum(scores.values())
        return {"total": total, "breakdown": scores}

    @staticmethod
    def _get_target_kp(user_input: str, context: Optional[Dict] = None) -> str:
        if context and context.get("topic"):
            return context["topic"]
        return user_input.strip() or DEFAULT_TOPIC

    @staticmethod
    def _get_fallback_html(topic: str, error_msg: str) -> str:
        """终极兜底页面，保证接口永远有返回，绝不白屏"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=1920, height=1080">
  <title>{topic} - 教学动画</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: linear-gradient(135deg, #0f0f23 0%, #16213e 50%, #0f0f23 100%);
      color: #e2e8f0;
      height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .box {{
      padding: 48px;
      border-radius: 20px;
      background: rgba(255, 255, 255, 0.05);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      text-align: center;
      max-width: 500px;
    }}
    h1 {{
      font-size: 2rem;
      background: linear-gradient(135deg, #60a5fa, #a78bfa);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 16px;
    }}
    p {{ color: #94a3b8; line-height: 1.6; }}
    .hint {{ font-size: 12px; color: #64748b; margin-top: 24px; }}
  </style>
</head>
<body>
  <div class="box">
    <h1>{topic}</h1>
    <p>动画生成暂时遇到问题，请稍后重试。</p>
    <p class="hint">Error: {escape(error_msg[:100])}</p>
  </div>
</body>
</html>"""

    def _build_resource(self, html_content: str, kp: str, video_config: Dict[str, Any]) -> ResourceItem:
        return ResourceItem(
            resource_type="video",
            title=f"{kp} - 语音教学动画",
            content=html_content,
            knowledge_points=[kp],
            status=RESOURCE_STATUS_COMPLETED,
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            is_reusable=True,
            extra_metadata={
                "video_format": "html_animation",
                "has_voice": True,
                "voice_source": tts_client.get_provider_name(),
                "voice_id": video_config.get("voice_id"),
                "auto_play": True,
                "duration": video_config.get("duration"),
                "style": video_config.get("style"),
            }
        )
