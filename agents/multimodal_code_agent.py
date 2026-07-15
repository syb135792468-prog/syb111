"""
agents/multimodal_code_agent.py - 多模态代码分析智能体
- Step 1: 火山方舟视觉理解模型（doubao-seed-2.1-turbo）识别图片中的代码（多模态）
- Step 2: DeepSeek 分析代码（解释+诊断+出题）
- 降级策略：视觉模型不可用时，用 EasyOCR 文本
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, AsyncIterator

from agents.base_agent import BaseAgent
from agents.code_agent import CodeAgent
from utils.logger import get_logger

logger = get_logger(__name__, task_id="multimodal_code")


class MultimodalCodeAgent(BaseAgent):
    """
    多模态代码分析智能体

    流程：
    1. 使用视觉理解模型识别图片中的代码（provider 由 VISION_PROVIDER 配置：ark 火山方舟 / xf 讯飞图片理解）
    2. 使用 DeepSeek 分析代码（解释+诊断+出题）
    3. 返回结构化分析结果
    """

    def __init__(self):
        super().__init__(
            agent_name="multimodal_code",
            scene_name="multimodal_code_analysis",
            enable_rag=False,
        )
        # 延迟导入，避免循环依赖
        self._vision_api = None
        self._fallback_vision_api = None
        self._ocr_engine = None

    @property
    def _primary_provider(self) -> str:
        from config.settings import settings
        return (settings.VISION_PROVIDER or "xf").lower()

    @property
    def _fallback_provider(self) -> str:
        return "ark" if self._primary_provider == "xf" else "xf"

    @staticmethod
    def _provider_label(provider: str) -> str:
        return "讯飞图片理解" if provider == "xf" else "火山方舟"

    @staticmethod
    def _load_vision_api(provider: str):
        if provider == "xf":
            from utils.xfyun_vision_api import xf_vision_api
            return xf_vision_api
        from utils.ark_vision_api import mimo_omni_api
        return mimo_omni_api

    @property
    def vision_api(self):
        """主视觉模型 API（由 VISION_PROVIDER 决定）"""
        if self._vision_api is None:
            self._vision_api = self._load_vision_api(self._primary_provider)
            logger.info(f"🔧 视觉模型主 provider = {self._primary_provider}（{self._provider_label(self._primary_provider)}）")
        return self._vision_api

    @property
    def fallback_vision_api(self):
        """降级视觉模型 API（主 provider 之外的另一个）"""
        if self._fallback_vision_api is None:
            self._fallback_vision_api = self._load_vision_api(self._fallback_provider)
            logger.info(f"🔧 视觉模型降级 provider = {self._fallback_provider}（{self._provider_label(self._fallback_provider)}）")
        return self._fallback_vision_api

    @property
    def ocr_engine(self):
        """延迟加载 OCR 引擎"""
        if self._ocr_engine is None:
            from utils.ocr import extract_text_sync
            self._ocr_engine = extract_text_sync
        return self._ocr_engine

    async def _try_vision_provider(
        self,
        api,
        image_path: Path,
        provider: str,
    ) -> tuple[str, Optional[str], list[str]]:
        """
        尝试单个视觉 provider 识别代码

        返回: (code_text, warning, errors)
            - warning=None 且 code_text 非空: 识别成功且语法通过
            - warning 非 None 且 code_text 非空: 有内容但语法不通过
            - code_text 为空: 调用异常或返回过短
        """
        label = self._provider_label(provider)
        errors: list[str] = []
        try:
            logger.info(f"🔍 尝试{label}识别代码: {image_path.name}")
            raw_text = await api.chat_completion(
                image_path=image_path,
                prompt="请识别这张图片中的Python代码，只返回代码内容本身，不要用```python```包裹，不要任何解释、注释说明或前后缀文字。严格保持原始的缩进、空格和换行。",
                system_prompt="你是代码识别专家。任务：准确识别图片中的Python代码，只输出纯代码文本。禁止输出markdown代码块标记、解释文字、思考过程。必须保留原始缩进和空格（Python对缩进敏感）。",
                temperature=0.1,
                max_tokens=4096,
            )
            code_text = CodeAgent._clean_code_block(raw_text) if raw_text else ""
            warning = self._validate_recognition(code_text, label)
            if warning is None:
                logger.info(f"✅ {label}识别成功: {len(code_text)} 字符（语法通过）")
            elif code_text:
                logger.warning(f"⚠️ {label}识别到内容但语法不通过: {warning}")
            else:
                msg = f"{label}返回内容过短（{len(raw_text.strip()) if raw_text else 0} 字符）"
                logger.warning(f"⚠️ {msg}")
                errors.append(msg)
            return code_text, warning, errors
        except Exception as e:
            msg = f"{label}调用失败: {type(e).__name__}: {e}"
            logger.warning(f"⚠️ {msg}")
            errors.append(msg)
            return "", None, errors

    async def recognize_code_from_image(self, image_path: str | Path) -> tuple[str, list[str], Optional[str]]:
        """
        Step 1: 从图片中识别代码

        三级降级链：
        1. 主视觉 provider（VISION_PROVIDER，默认讯飞图片理解）
        2. 降级视觉 provider（另一个，默认火山方舟）—— 仅当主失败或语法不通过时触发
        3. EasyOCR —— 仅当两个视觉 provider 都拿不到内容时触发

        返回: (code_text, errors, syntax_warning)
            - syntax_warning: None 表示语法正常；非 None 表示识别结果语法不通过，需在第二步分析时标注
        """
        image_path = Path(image_path)
        all_errors: list[str] = []

        # ---- 第 1 级：主视觉 provider ----
        code, warning, errs = await self._try_vision_provider(
            self.vision_api, image_path, self._primary_provider
        )
        all_errors.extend(errs)
        if code and warning is None:
            return code, all_errors, None

        # ---- 第 2 级：降级视觉 provider ----
        # 触发条件：主 provider 异常、返回空、或语法不通过
        fb_code, fb_warning, fb_errs = await self._try_vision_provider(
            self.fallback_vision_api, image_path, self._fallback_provider
        )
        all_errors.extend(fb_errs)
        if fb_code and fb_warning is None:
            return fb_code, all_errors, None

        # 两个视觉 provider 都没拿到语法通过的结果：
        # - 如果主有内容（带警告），优先用主（信主 provider）
        # - 如果主没内容但降级有，用降级
        # - 都没内容，继续降级 OCR
        if not code and fb_code:
            code, warning = fb_code, fb_warning
        if code:
            return code, all_errors, warning

        # ---- 第 3 级：EasyOCR ----
        try:
            logger.info(f"🔍 降级使用 EasyOCR 识别: {image_path.name}")
            import asyncio
            raw_text = await asyncio.to_thread(self.ocr_engine, str(image_path))
            code_text = CodeAgent._clean_code_block(raw_text) if raw_text else ""
            warning = self._validate_recognition(code_text, "EasyOCR")
            if code_text and warning is None:
                logger.info(f"✅ OCR 识别成功: {len(code_text)} 字符（语法通过）")
                return code_text, all_errors, None
            elif code_text:
                logger.warning(f"⚠️ OCR 识别到内容但语法不通过: {warning}")
                return code_text, all_errors, warning
            else:
                msg = f"OCR 识别结果过短（{len(raw_text.strip()) if raw_text else 0} 字符）"
                logger.warning(f"⚠️ {msg}")
                all_errors.append(msg)
                return "", all_errors, None
        except Exception as e:
            msg = f"OCR 识别失败: {type(e).__name__}: {e}"
            logger.error(f"❌ {msg}")
            all_errors.append(msg)
            return "", all_errors, None

    @staticmethod
    def _validate_recognition(code_text: str, source: str) -> Optional[str]:
        """
        校验识别结果：长度阈值 + Python 语法编译
        返回 None 表示通过；返回字符串表示警告原因
        """
        if not code_text or len(code_text.strip()) < 15:
            return f"{source}识别结果过短（{len(code_text.strip()) if code_text else 0} 字符）"
        # 必须含至少一个 Python 代码特征，否则大概率不是代码
        if not any(kw in code_text for kw in ("def ", "print", "=", ":", "import", "for ", "if ")):
            return f"{source}识别结果未包含任何 Python 代码特征"
        # 语法编译校验
        try:
            compile(code_text, "<recognition>", "exec")
            return None
        except SyntaxError as e:
            return f"语法错误（第{e.lineno}行: {e.msg}）— 识别可能有误，缩进或符号可能错位"

    async def analyze_code(self, code_text: str, recognition_warning: Optional[str] = None) -> Dict[str, Any]:
        """
        Step 2: 使用 DeepSeek 分析代码

        返回：解释 + 问题诊断 + 练习题
        recognition_warning: 若非 None，说明识别结果语法不通过，在 prompt 中标注让 LLM 谨慎分析
        """
        if not code_text or len(code_text.strip()) < 5:
            return {
                "explanation": "未能识别到有效的代码内容",
                "problems": [],
                "exercises": [],
                "knowledge_points": [],
            }

        # 加载 Prompt 模板
        system_prompt = self._load_prompt(
            "multimodal_code_analysis_system",
            code_text=code_text,
        )

        # 若识别阶段检测到语法问题，追加提示让 LLM 谨慎分析（识别可能有误，而非代码本身有问题）
        if recognition_warning:
            system_prompt += (
                "\n\n## 识别质量警告\n"
                f"代码识别阶段检测到：{recognition_warning}\n"
                "这意味着识别出的代码可能与原图不一致（缩进错位、符号混淆等），"
                "而非用户代码本身的错误。诊断时优先考虑识别误差而非代码缺陷，"
                "不要把识别引入的语法错误归咎于用户。若无法确定是识别误差还是真实错误，请在解释中如实说明。"
            )

        # 调用 DeepSeek 分析
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请分析这段代码，按照要求的JSON格式输出结果。"},
        ]

        try:
            response = await self._call_llm(
                messages=messages,
                temperature=0.3,
                max_tokens=4096,
            )

            # 提取 JSON
            result = self._extract_json(response)

            # 确保必要字段存在
            result.setdefault("explanation", "")
            result.setdefault("problems", [])
            result.setdefault("exercises", [])
            result.setdefault("knowledge_points", [])

            logger.info(
                f"✅ 代码分析完成 | 问题数={len(result['problems'])} | "
                f"练习题数={len(result['exercises'])}"
            )
            return result

        except Exception as e:
            logger.error(f"❌ 代码分析失败: {e}")
            return {
                "explanation": f"代码分析失败: {str(e)}",
                "problems": [],
                "exercises": [],
                "knowledge_points": [],
            }

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        完整的多模态代码分析流程

        Args:
            user_input: 图片路径（URL 或本地路径）
            context: 上下文（可选）

        Returns:
            包含 code_text, explanation, problems, exercises 的字典
        """
        context = context or {}
        image_path = user_input

        # Step 1: 识别代码
        logger.info(f"📸 开始多模态代码分析: {image_path}")
        code_text, _errors, recognition_warning = await self.recognize_code_from_image(image_path)

        if not code_text:
            return {
                "code_text": "",
                "explanation": "未能从图片中识别到代码内容",
                "problems": [],
                "exercises": [],
                "knowledge_points": [],
                "current_step": "completed",
            }

        # Step 2: 分析代码（透传识别警告）
        analysis = await self.analyze_code(code_text, recognition_warning)

        return {
            "code_text": code_text,
            "explanation": analysis.get("explanation", ""),
            "problems": analysis.get("problems", []),
            "exercises": analysis.get("exercises", []),
            "knowledge_points": analysis.get("knowledge_points", []),
            "recognition_warning": recognition_warning,
            "current_step": "completed",
        }

    async def process_stream(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        流式处理：分步返回分析结果

        Yields:
            - code_recognition: 识别出的代码
            - analysis: 解释+诊断
            - exercises: 练习题
        """
        context = context or {}
        image_path = user_input

        # Step 1: 识别代码
        logger.info(f"📸 开始流式多模态代码分析: {image_path}")
        code_text, recognition_errors, recognition_warning = await self.recognize_code_from_image(image_path)

        yield {
            "event": "code_recognition",
            "data": {"code_text": code_text, "recognition_warning": recognition_warning},
        }

        if not code_text:
            error_detail = "；".join(recognition_errors) if recognition_errors else "未知原因"
            yield {
                "event": "analysis",
                "data": {
                    "explanation": f"未能从图片中识别到代码内容。识别引擎报错：{error_detail}",
                    "problems": [],
                    "knowledge_points": [],
                },
            }
            yield {
                "event": "exercises",
                "data": {"exercises": []},
            }
            yield {"event": "end", "data": {}}
            return

        # Step 2: 分析代码（透传识别警告）
        analysis = await self.analyze_code(code_text, recognition_warning)

        yield {
            "event": "analysis",
            "data": {
                "explanation": analysis.get("explanation", ""),
                "problems": analysis.get("problems", []),
                "knowledge_points": analysis.get("knowledge_points", []),
            },
        }

        yield {
            "event": "exercises",
            "data": {"exercises": analysis.get("exercises", [])},
        }

        yield {"event": "end", "data": {}}


# ============================================================
# 模块级单例
# ============================================================
_multimodal_code_agent: Optional[MultimodalCodeAgent] = None


def get_multimodal_code_agent() -> MultimodalCodeAgent:
    """获取多模态代码分析 Agent 单例"""
    global _multimodal_code_agent
    if _multimodal_code_agent is None:
        _multimodal_code_agent = MultimodalCodeAgent()
    return _multimodal_code_agent
