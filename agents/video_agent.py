"""
agents/video_agent.py - 软件杯A3 视频生成智能体
功能：生成带浏览器原生语音配音的HTML教学动画，GSAP驱动
规范：统一继承BaseAgent，适配LangGraph工作流，工程化标准实现

架构：LLM用GSAP自由编写动画代码，后处理注入GSAP CDN + 播放控制逻辑
"""
from __future__ import annotations

import re
from typing import Dict, Any, Optional

from agents.base_agent import BaseAgent
from graph.state import ResourceItem
from config.constants import (
    VIDEO_MAX_TOKENS, VIDEO_MIN_HTML_LINES, VIDEO_MAX_RETRIES,
    VIDEO_DEFAULT_VOICE_RATE, VIDEO_DEFAULT_VOICE_LANG,
    VIDEO_DEFAULT_STYLE, VIDEO_DEFAULT_DURATION,
    VIDEO_GSAP_CDN_URL,
    RESOURCE_PROGRESS_COMPLETE, DEFAULT_TOPIC, RESOURCE_STATUS_COMPLETED,
)
from utils.agent_helpers import match_knowledge_point, get_profile_from_context

# ============================================================
# 播放控制逻辑：绑定按钮事件，调用LLM定义的全局函数
# LLM负责实现 startAnimation/pauseAnimation/resumeAnimation/restartAnimation/seekTo
# ============================================================
_CONTROL_LOGIC_JS = """
// --- 开始按钮：调用LLM定义的startAnimation ---
document.getElementById('startButton').addEventListener('click', () => {
  if (typeof startAnimation === 'function') {
    startAnimation();
  } else {
    document.getElementById('startScreen').style.display = 'none';
    document.getElementById('playerScreen').style.display = 'block';
  }
});

// --- 播放/暂停：调用LLM定义的pauseAnimation/resumeAnimation ---
document.getElementById('playPauseButton').addEventListener('click', () => {
  if (window.isPlaying) {
    if (typeof pauseAnimation === 'function') pauseAnimation();
    document.getElementById('playPauseButton').textContent = '▶';
  } else {
    if (typeof resumeAnimation === 'function') resumeAnimation();
    document.getElementById('playPauseButton').textContent = '⏸';
  }
  window.isPlaying = !window.isPlaying;
});

// --- 重播：调用LLM定义的restartAnimation ---
document.getElementById('restartButton').addEventListener('click', () => {
  if (typeof restartAnimation === 'function') {
    restartAnimation();
  } else {
    window.speechSynthesis.cancel();
    window.isPlaying = false;
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('playerScreen').style.display = 'none';
    document.getElementById('startScreen').style.display = 'flex';
  }
});

// --- 进度条点击：调用LLM定义的seekTo ---
document.getElementById('progressBar').addEventListener('click', (e) => {
  const rect = e.currentTarget.getBoundingClientRect();
  const clickX = e.clientX - rect.left;
  const percent = Math.max(0, Math.min(100, (clickX / rect.width) * 100));
  document.getElementById('progressFill').style.width = percent + '%';
  if (typeof seekTo === 'function') seekTo(percent);
});

// --- 键盘快捷键 ---
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  switch (e.code) {
    case 'Space':
      e.preventDefault();
      document.getElementById('playPauseButton').click();
      break;
    case 'KeyR':
      e.preventDefault();
      document.getElementById('restartButton').click();
      break;
  }
});
"""

_COMPATIBILITY_WARNING_HTML = """
<div id="noVoiceWarning" style="display:none;position:fixed;top:20px;left:50%;transform:translateX(-50%);background:#ff6b6b;color:white;padding:12px 24px;border-radius:8px;z-index:9999;font-size:16px;box-shadow:0 4px 12px rgba(0,0,0,0.15);font-family:system-ui,sans-serif;">
  ⚠️ 您的浏览器不支持语音合成，将使用纯文字模式
</div>
<script>
if (!('speechSynthesis' in window)) {
  document.getElementById('noVoiceWarning').style.display = 'block';
  setTimeout(() => { document.getElementById('noVoiceWarning').style.display = 'none'; }, 5000);
}
</script>
"""


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

    async def _call_llm(
        self,
        messages: list,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """视频生成直接用DeepSeek，跳过MiMo（推理模型生成大段HTML太慢，~140s vs DeepSeek ~37s）"""
        temp = temperature if temperature is not None else self.scene_params.get("temperature", 0.7)
        tokens = max_tokens if max_tokens is not None else self.scene_params.get("max_tokens", 16000)
        client = self.llm_client
        if client.fallback_client is None:
            self.logger.warning("DeepSeek不可用，回退到默认LLM调用链")
            return await super()._call_llm(messages, temperature, max_tokens)
        self.logger.info(f"[video] 直接调用DeepSeek: temp={temp}, max_tokens={tokens}")
        return await client._call_with_retry(
            client=client.fallback_client,
            model=client.fallback_model,
            messages=messages,
            temperature=temp,
            max_tokens=tokens,
            provider_name="DeepSeek(视频专用)",
        )

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            target_kp = self._get_target_kp(user_input, context)
            self.logger.info(f"开始生成教学视频，知识点：{target_kp}")

            config = (context or {}).get("config", {})
            video_config = self._build_video_config(config)
            self.logger.info(f"视频配置: {video_config}")

            html_code = await self._generate_with_retry(target_kp, video_config)
            if not html_code or len(html_code.strip()) < 50:
                self.logger.error(f"LLM返回的HTML过短或为空，长度: {len(html_code) if html_code else 0}")
                raise ValueError("LLM返回的HTML内容无效")

            self.logger.info(f"LLM返回HTML长度: {len(html_code)} 字符")
            html_code = self._enhance_animation(html_code, video_config)
            html_code = self._validate_html(html_code)

            resource = self._build_resource(html_code, target_kp, video_config)
            new_resources = self._append_resource(context, resource)

            self.logger.info(f"教学视频生成完成：{resource.title}")
            return self._build_result(new_resources)

        except Exception as e:
            self.logger.error(f"视频生成失败：{type(e).__name__}: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def _build_video_config(config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "duration": config.get("duration", VIDEO_DEFAULT_DURATION),
            "style": config.get("style", VIDEO_DEFAULT_STYLE),
            "voice_rate": config.get("voice_rate", VIDEO_DEFAULT_VOICE_RATE),
            "voice_lang": config.get("voice_lang", VIDEO_DEFAULT_VOICE_LANG),
            "custom_prompt": config.get("customPrompt", ""),
        }

    async def _generate_with_retry(self, topic: str, video_config: Dict[str, Any]) -> str:
        last_html = ""
        for attempt in range(VIDEO_MAX_RETRIES + 1):
            html = await self._generate_html_with_voice(topic, video_config)
            line_count = html.count("\n") + 1

            if line_count >= VIDEO_MIN_HTML_LINES:
                self.logger.info(f"生成的HTML共{line_count}行（第{attempt + 1}次尝试）")
                return html

            last_html = html
            self.logger.warning(
                f"第{attempt + 1}次生成的HTML仅{line_count}行，"
                f"少于{VIDEO_MIN_HTML_LINES}行，{'重试中...' if attempt < VIDEO_MAX_RETRIES else '使用最后结果'}"
            )

        return last_html

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

        html = response.strip()
        if html.startswith("```html"):
            html = html[7:]
        elif html.startswith("```"):
            html = html[3:]
        if html.endswith("```"):
            html = html[:-3]
        return html.strip()

    def _enhance_animation(self, html_code: str, video_config: Dict[str, Any]) -> str:
        """后处理：注入GSAP CDN + 播放控制逻辑 + 兼容性提示"""

        # 1. 注入GSAP CDN（LLM用GSAP写动画，必须保证CDN加载）
        if "gsap" not in html_code.lower():
            self.logger.info("GSAP缺失，自动注入CDN")
            html_code = self._inject_before_head_close(
                html_code,
                f'<script src="{VIDEO_GSAP_CDN_URL}"></script>'
            )

        # 2. 注入播放控制逻辑（绑定按钮事件，调用LLM定义的函数）
        html_code = self._inject_before_body_close(html_code, f"<script>\n{_CONTROL_LOGIC_JS}\n</script>")

        # 3. 注入浏览器兼容性提示
        if "noVoiceWarning" not in html_code:
            html_code = self._inject_before_body_close(html_code, _COMPATIBILITY_WARNING_HTML)

        # 4. 确保关键DOM元素存在
        required_ids = ["startScreen", "startButton", "playerScreen", "mainTitle",
                        "speechBubble", "codeDisplay", "controls", "progressFill"]
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
    def _get_target_kp(user_input: str, context: Optional[Dict] = None) -> str:
        if context and context.get("topic"):
            return context["topic"]
        return user_input.strip() or DEFAULT_TOPIC

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
                "voice_source": "browser_web_speech",
                "auto_play": True,
                "duration": video_config.get("duration"),
                "style": video_config.get("style"),
            }
        )
