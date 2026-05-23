"""
agents/video_agent.py - 软件杯A3 视频生成智能体
功能：生成带浏览器原生语音配音的HTML教学动画，无需第三方API
规范：统一继承BaseAgent，适配LangGraph工作流，工程化标准实现
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List

from agents.base_agent import BaseAgent
from graph.state import ResourceItem
from config.constants import VIDEO_MAX_TOKENS, RESOURCE_PROGRESS_COMPLETE
from utils.agent_helpers import match_knowledge_point, get_profile_from_context


class VideoAgent(BaseAgent):
    """
    视频资源生成智能体
    生成HTML格式的时序教学动画，集成Web Speech API实现自动语音讲解
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
    ) -> Dict[str, Any]:
        """
        Agent 核心执行入口
        :param user_input: 用户输入文本
        :param context: 上下文状态
        :return: 标准工作流返回结果
        """
        try:
            # 1. 统一提取目标知识点
            target_kp = self._get_target_kp(user_input, context)
            self.logger.info(f"🎬 开始生成教学视频，知识点：{target_kp}")

            # 2. 调用大模型生成HTML动画
            html_code = await self._generate_html_with_voice(target_kp)

            # 3. 统一封装资源对象
            resource = self._build_resource(html_code, target_kp)

            # 4. 构建新资源列表（不可变更新）
            new_resources = self._append_resource(context, resource)

            self.logger.info(f"✅ 教学视频生成完成：{resource.title}")
            return self._build_result(new_resources)

        except Exception as e:
            self.logger.error(f"❌ 视频生成失败：{str(e)}", exc_info=True)
            # 异常兜底，保证工作流不中断
            return self._build_result(context.get("resource_list", []))

    async def _generate_html_with_voice(self, topic: str) -> str:
        """
        调用大模型生成带语音的HTML教学动画
        :param topic: 教学知识点
        :return: 纯HTML代码
        """
        prompt = f"""
# 角色：Python教学动画工程师
# 任务：为【{topic}】生成可独立运行的HTML教学动画（带自动语音讲解）

## 严格要求：
1. 纯HTML+CSS+原生JS实现，禁止引入任何外部资源/CDN
2. 自动时序播放，分步骤展示知识点，代码高亮、流程清晰
3. 集成浏览器原生 Web Speech API，动画与语音讲解严格同步
4. 教学风格简洁、居中布局、移动端适配
5. 页面加载后自动播放，无需手动触发
6. 仅返回纯HTML代码，无任何解释、无Markdown、无多余内容

## 语音配置：
- 语言：zh-CN
- 每一步动画自动朗读对应讲解文案
"""
        messages = [{"role": "user", "content": prompt}]
        response = await self._call_llm(messages, max_tokens=VIDEO_MAX_TOKENS)
        return response.strip()

    @staticmethod
    def _get_target_kp(user_input: str, context: Optional[Dict] = None) -> str:
        """
        统一规则：从用户输入/用户画像中提取目标知识点
        """
        input_text = user_input.lower()

        # 优先匹配标准知识点
        matched = match_knowledge_point(input_text)
        if matched:
            return matched

        # 兜底：使用用户画像薄弱知识点
        if context:
            profile = get_profile_from_context(context)
            weak_points = profile.get("weak_points", [])
            if weak_points:
                return weak_points[0]

        # 最终兜底：直接使用用户输入
        return user_input

    def _build_resource(self, html_content: str, kp: str) -> ResourceItem:
        """
        统一封装 ResourceItem 标准资源对象
        """
        return ResourceItem(
            resource_type="video",
            title=f"{kp} - 语音教学动画",
            content=html_content,
            knowledge_points=[kp],
            status="completed",
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            is_reusable=True,
            extra_metadata={
                "video_format": "html_animation",
                "has_voice": True,
                "voice_source": "browser_web_speech",
                "auto_play": True
            }
        )

    # _build_result 已继承自 BaseAgent