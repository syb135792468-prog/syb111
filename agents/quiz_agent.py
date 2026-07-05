"""
agents/quiz_agent.py - 软件杯A3 练习题生成智能体（Phase 1 重构版）
✅ 15知识点 × 10题 = 150题规则题库，含难度分级
✅ LLM 模式默认启用，规则模式仅作兜底
✅ 完整接入 difficulty / include_explanation / custom_prompt
✅ 填空题多答案支持，选项强迷惑性
✅ question_hash 去重机制
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List, ClassVar
import random
import hashlib
import json as _json
import time
import re
from pathlib import Path

from agents.base_agent import BaseAgent
from graph.state import ResourceItem
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.constants import (
    QUIZ_RAG_TOP_K, RESOURCE_PROGRESS_COMPLETE,
    LLM_CIRCUIT_BREAKER_THRESHOLD, LLM_CIRCUIT_BREAKER_COOLDOWN_SEC,
    QUESTION_HASH_TRUNCATE_LENGTH, QUIZ_TYPE_CHOICE, QUIZ_TYPE_FILL, QUIZ_TYPE_CODE,
    DEFAULT_TOPIC, RESOURCE_STATUS_COMPLETED, DIFFICULTY_MEDIUM, DIFFICULTY_AUTO,
)
from utils.agent_helpers import match_knowledge_point, get_profile_from_context


class QuizAgent(BaseAgent):
    """练习题生成智能体：规则+LLM双模式，支持选择/填空/编程三种题型"""

    TYPE_CHOICE: ClassVar[str] = "choice"
    TYPE_FILL: ClassVar[str] = "fill"
    TYPE_CODE: ClassVar[str] = "code"
    ALL_TYPES: ClassVar[List[str]] = [TYPE_CHOICE, TYPE_FILL, TYPE_CODE]

    FAILURE_EMPTY: ClassVar[str] = "llm_empty"
    FAILURE_JSON: ClassVar[str] = "llm_json_invalid"
    FAILURE_FIELD: ClassVar[str] = "llm_missing_field"
    FAILURE_TYPE: ClassVar[str] = "llm_type_mismatch"
    FAILURE_RELEVANCE: ClassVar[str] = "llm_kp_mismatch"
    FAILURE_RULE: ClassVar[str] = "rule_fallback_failed"
    FAILURE_API: ClassVar[str] = "llm_api_error"

    # ================================================================
    # 题库加载（从 JSON 文件读取）
    # ================================================================
    def _load_question_bank(self) -> Dict[str, List[Dict[str, Any]]]:
        """从 data/question_bank.json 加载题库"""
        bank_path = Path(__file__).resolve().parent.parent / "data" / "question_bank.json"
        try:
            with open(bank_path, "r", encoding="utf-8") as f:
                bank = _json.load(f)
            total = sum(len(v) for v in bank.values())
            self.logger.info(f"📚 题库加载成功：{len(bank)} 个知识点，{total} 道题")
            return bank
        except Exception as e:
            self.logger.error(f"❌ 题库加载失败：{e}")
            return {}

    # ================================================================
    # 初始化
    # ================================================================
    def __init__(
        self,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
        use_llm: bool = True,  # MODIFIED: 默认启用 LLM 模式
        quiz_type: Optional[str] = None,
    ) -> None:
        super().__init__(
            agent_name="quiz",
            scene_name="quiz_generation",
            enable_rag=True,
            user_id=user_id,
            task_id=task_id,
        )
        self.use_llm = use_llm
        self.quiz_type = quiz_type
        self.question_bank = self._load_question_bank()
        # LLM 熔断器：连续失败 ≥3 次则禁用 LLM 60 秒
        self._llm_fail_count = 0
        self._llm_disabled_until = 0.0
        self._LLM_FAIL_THRESHOLD = LLM_CIRCUIT_BREAKER_THRESHOLD
        self._LLM_COOLDOWN_SEC = LLM_CIRCUIT_BREAKER_COOLDOWN_SEC
        mode = "LLM" if use_llm else "规则"
        self.logger.info(f"📝 练习题Agent初始化：模式={mode}，题型={quiz_type or '随机'}")

    # ================================================================
    # 核心接口
    # ================================================================
    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
        quiz_type: Optional[str] = None,
        difficulty: str = DIFFICULTY_MEDIUM,
        include_explanation: bool = True,
        custom_prompt: str = "",
        force_knowledge_point: Optional[str] = None,  # 强制使用指定知识点
    ) -> Dict[str, Any]:
        """生成一道练习题"""
        # 优先使用强制指定的知识点，避免多题生成时知识点漂移
        if force_knowledge_point:
            target_kp = force_knowledge_point
            self.logger.info(f"🔒 强制知识点: {target_kp}")
        else:
            target_kp = self._get_target_knowledge_point(user_input, context)
        target_type = quiz_type or self.quiz_type or random.choice(self.ALL_TYPES)

        # 自适应难度：difficulty="auto" 时根据用户能力动态选择
        if difficulty == DIFFICULTY_AUTO:
            difficulty = await self._resolve_adaptive_difficulty(context, target_kp)
            self.logger.info(f"🎯 自适应难度选择: {difficulty}")

        self.logger.info(f"🎯 知识点={target_kp}，题型={target_type}，难度={difficulty}")

        # 根据模式生成（检查熔断器）
        use_llm_now = self.use_llm and time.time() >= self._llm_disabled_until
        if use_llm_now:
            try:
                raw_quiz = await self._generate_via_llm(
                    target_kp, target_type, difficulty, custom_prompt
                )
            except ValueError as exc:
                # LLM 结果无效时优先降级规则模式，避免反复重试把整条生成链路打死
                failure_code = self._classify_llm_failure(exc)
                self.logger.warning(
                    f"[{failure_code}] LLM 结果校验失败: kp={target_kp}, type={target_type}, detail={exc}; 降级规则模式"
                )
                self._llm_fail_count += 1
                self._check_circuit_breaker()
                raw_quiz = self._generate_via_rule(target_kp, target_type, difficulty)
            except Exception as exc:
                # LLM API 异常（网络/超时等）→ 降级规则模式
                self.logger.warning(
                    f"[{self.FAILURE_API}] LLM API 异常: kp={target_kp}, type={target_type}, detail={exc}; 降级规则模式"
                )
                self._llm_fail_count += 1
                self._check_circuit_breaker()
                raw_quiz = self._generate_via_rule(target_kp, target_type, difficulty)
        else:
            if self.use_llm and time.time() < self._llm_disabled_until:
                self.logger.info(f"⚡ LLM 熔断中，直接走规则模式")
            raw_quiz = self._generate_via_rule(target_kp, target_type, difficulty)

        actual_type = raw_quiz.get("type", target_type)
        resource = self._create_resource_item(
            raw_quiz, target_kp, actual_type, include_explanation
        )
        new_resources = self._append_resource(context, resource)

        self.logger.info(f"✅ 生成完成：{resource.title}（{actual_type}/{difficulty}）")
        return self._build_result(new_resources)

    # ================================================================
    # 规则模式
    # ================================================================
    def _generate_via_rule(self, kp: str, qtype: str, difficulty: str = DIFFICULTY_MEDIUM) -> Dict[str, Any]:
        """规则模式：优先命中目标知识点；必要时放宽到标准知识点和同知识点其他题型。"""
        bank_kp = self._resolve_rule_bank_kp(kp)
        quiz_list = self.question_bank.get(bank_kp, [])
        if not quiz_list:
            self.logger.error(f"[{self.FAILURE_RULE}] 题库无 {kp}（解析后: {bank_kp}），无法生成")
            raise ValueError(f"知识点 {kp} 没有可用题目")

        # 按题型筛选
        type_filtered = [q for q in quiz_list if q["type"] == qtype]

        if type_filtered:
            # 按难度筛选
            diff_filtered = [q for q in type_filtered if q.get("difficulty") == difficulty]
            if diff_filtered:
                return random.choice(diff_filtered)
            self.logger.warning(f"知识点 {bank_kp} 无 {difficulty} 难度的 {qtype}，用同题型其他难度")
            return random.choice(type_filtered)

        # 同知识点无指定题型时，退回到该知识点任意可用题型，保证能产出题目
        self.logger.warning(f"知识点 {bank_kp} 无 {qtype} 题型，回退到同知识点其他题型")
        diff_filtered = [q for q in quiz_list if q.get("difficulty") == difficulty]
        if diff_filtered:
            return random.choice(diff_filtered)
        return random.choice(quiz_list)

    # ================================================================
    # LLM 模式
    # ================================================================
    async def _generate_via_llm(
        self, kp: str, qtype: str, difficulty: str = DIFFICULTY_MEDIUM, custom_prompt: str = ""
    ) -> Dict[str, Any]:
        """LLM 模式：调用大模型生成高质量题目。
        验证失败时直接抛出异常（不降级规则模式），让调用方的重试机制重新生成。
        """
        rag_context = await self._get_rag_context_for_quiz(kp)

        # 终极提示词：铁律 + 禁止清单 + 惩罚机制
        custom_prompt_section = (
            f"# ⚠️ 用户自定义要求（必须100%严格遵守，违反即输出无效）\n{custom_prompt}"
            if custom_prompt else ""
        )
        system_prompt = self._load_prompt(
            "quiz_generation_system",
            kp=kp, qtype=qtype, difficulty=difficulty,
            custom_prompt_section=custom_prompt_section,
            rag_context=rag_context if rag_context else "无",
        )

        resp = await self._call_llm([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._load_prompt("quiz_generation_user", kp=kp, qtype=qtype, difficulty=difficulty)},
        ])

        # JSON 解析
        data = self._robust_extract_json(resp)

        # 必填字段检查
        for field in ("type", "title", "question", "answer", "explanation"):
            if field not in data:
                raise ValueError(f"LLM 返回缺少字段：{field}")

        # 类型校验
        if data.get("type") != qtype:
            raise ValueError(f"LLM 返回题型 {data.get('type')} ≠ 要求 {qtype}")

        if not self._is_question_relevant(kp, data):
            raise ValueError(
                f"LLM 生成的题目与 {kp} 不相关（标题: {data.get('title', '')}）"
            )

        data.setdefault("difficulty", difficulty)
        self._llm_fail_count = 0
        self.logger.info(f"🤖 LLM 生成成功：{data.get('title', '')}")
        return data

    def _check_circuit_breaker(self):
        """检查是否需要触发 LLM 熔断"""
        if self._llm_fail_count >= self._LLM_FAIL_THRESHOLD:
            self._llm_disabled_until = time.time() + self._LLM_COOLDOWN_SEC
            self.logger.warning(
                f"🔴 LLM 连续失败 {self._llm_fail_count} 次，熔断 {self._LLM_COOLDOWN_SEC}s"
            )
            self._llm_fail_count = 0

    def _extract_kp_keywords(self, kp: str) -> List[str]:
        """提取知识点的关键词列表，用于相关性验证"""
        keywords = re.split(r'[（）、。，：/、，。\s与()]+', kp.lower())
        return [kw for kw in keywords if len(kw) >= 1]

    def _classify_llm_failure(self, exc: Exception) -> str:
        """将 LLM 校验失败归类为稳定的日志标签。"""
        msg = str(exc)
        if "空内容" in msg:
            return self.FAILURE_EMPTY
        if "缺少字段" in msg:
            return self.FAILURE_FIELD
        if "返回题型" in msg:
            return self.FAILURE_TYPE
        if "不相关" in msg:
            return self.FAILURE_RELEVANCE
        if "json" in msg.lower() or "expecting value" in msg.lower():
            return self.FAILURE_JSON
        return "llm_validation_failed"

    def _resolve_rule_bank_kp(self, kp: str) -> str:
        """将输入知识点映射到题库中的可用知识点。"""
        if kp in self.question_bank:
            return kp

        matched_kp = match_knowledge_point(kp)
        if matched_kp and matched_kp in self.question_bank:
            self.logger.info(f"规则题库知识点映射：{kp} -> {matched_kp}")
            return matched_kp

        kp_keywords = [kw for kw in self._extract_kp_keywords(kp) if len(kw) >= 2]
        best_kp = kp
        best_score = 0
        for candidate in self.question_bank.keys():
            candidate_text = candidate.lower()
            score = sum(1 for kw in kp_keywords if kw in candidate_text)
            if score > best_score:
                best_score = score
                best_kp = candidate

        if best_score > 0:
            self.logger.info(f"规则题库关键词映射：{kp} -> {best_kp}")
            return best_kp

        # 所有匹配方式均失败，随机选择一个题库知识点兜底
        fallback_kp = random.choice(list(self.question_bank.keys()))
        self.logger.warning(f"知识点 {kp} 无法映射到题库，随机回退到: {fallback_kp}")
        return fallback_kp

    def _is_question_relevant(self, kp: str, data: Dict[str, Any]) -> bool:
        """更宽松但仍可控的知识点相关性校验。"""
        question_text = " ".join([
            str(data.get("title", "")),
            str(data.get("question", "")),
            str(data.get("explanation", "")),
        ]).lower()
        kp_lower = kp.lower()

        # 第1层：完整知识点名
        if kp_lower in question_text:
            return True

        # 第2层：知识点核心中文名
        core_name = re.sub(r'[（(].*?[）)]', '', kp).strip().lower()
        if len(core_name) >= 2 and core_name in question_text:
            return True

        # 第3层：标准知识点匹配，允许题面不直接复述术语
        matched_kp = match_knowledge_point(question_text)
        if matched_kp == kp:
            return True

        # 第4层：关键词比例，放宽为 >= 1/3 且至少命中 1 个
        meaningful_kws = [kw for kw in self._extract_kp_keywords(kp) if len(kw) >= 2]
        if meaningful_kws:
            matched_count = sum(1 for kw in meaningful_kws if kw in question_text)
            if matched_count >= 1 and (matched_count / len(meaningful_kws)) >= 0.34:
                return True

        # 第5层：结构兜底 — Prompt 中已注入知识点，LLM 生成了有效结构即放行
        # 避免因关键词匹配失败导致有效题目被误杀
        if data.get("answer") and data.get("question") and data.get("explanation"):
            self.logger.warning(f"⚠️ 知识点验证未命中，但题目结构有效，放行: kp={kp}, title={data.get('title', '')}")
            return True

        return False

    async def _get_rag_context_for_quiz(self, kp: str) -> str:
        """获取 RAG 上下文，过滤掉与目标知识点无关的片段（防止 RAG 污染）"""
        raw_context = await self._get_rag_context(kp, top_k=QUIZ_RAG_TOP_K)
        if not raw_context:
            return ""

        kp_keywords = self._extract_kp_keywords(kp)
        filtered_parts = []
        for part in raw_context.split("\n\n"):
            part_lower = part.lower()
            if any(kw in part_lower for kw in kp_keywords):
                filtered_parts.append(part)

        if not filtered_parts:
            self.logger.warning(f"RAG 片段均与 {kp} 无关，丢弃全部参考资料")
            return ""

        self.logger.info(f"RAG 过滤: {len(raw_context.split(chr(10)+chr(10)))} 条 → {len(filtered_parts)} 条与 {kp} 相关")
        return "\n\n".join(filtered_parts)

    def _robust_extract_json(self, text: str) -> Dict[str, Any]:
        """增强版 JSON 提取：处理 Markdown 代码块、转义字符等"""
        if not text or not text.strip():
            raise ValueError("LLM 返回空内容")
        # 移除 Markdown 代码块标记
        text = re.sub(r'```(?:json)?\s*', '', text)
        text = re.sub(r'```\s*$', '', text.strip())
        # 尝试直接解析
        try:
            return _json.loads(text.strip())
        except _json.JSONDecodeError:
            pass
        # 提取 { ... } 块（非贪婪匹配，防止多 JSON 对象时过度捕获）
        match = re.search(r'\{[\s\S]*?\}', text)
        if match:
            try:
                return _json.loads(match.group())
            except _json.JSONDecodeError:
                pass
        # 使用基类方法兜底
        return self._extract_json(text)

    # ================================================================
    # 工具方法
    # ================================================================
    def _get_target_knowledge_point(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> str:
        """优先使用统一路由提取的纯主题，兜底用用户输入"""
        if context and context.get("topic"):
            return context["topic"]
        return user_input.strip() or DEFAULT_TOPIC

    async def _resolve_adaptive_difficulty(self, context: Optional[Dict[str, Any]], topic: str) -> str:
        """根据用户历史表现自适应选择难度"""
        try:
            from models.database import AsyncSessionLocal
            from ai.adaptive_difficulty import AdaptiveDifficultyEngine

            user_id = None
            if context:
                user_id = context.get("user_id")
            if not user_id:
                # 从 agent 自身获取
                user_id = getattr(self, "user_id", None)
            if not user_id:
                return DIFFICULTY_MEDIUM

            # A/B 实验：检查是否使用固定难度
            try:
                from ai.experiment_engine import experiment_engine
                async with AsyncSessionLocal() as exp_db:
                    diff_config = await experiment_engine.get_variant_config(
                        int(user_id), "difficulty_adaptation", exp_db
                    )
                if diff_config and diff_config.get("difficulty_mode") == "fixed":
                    fixed = diff_config.get("fixed_level", DIFFICULTY_MEDIUM)
                    self.logger.info(f"🧪 实验覆盖：使用固定难度 {fixed}")
                    return fixed
            except Exception:
                pass

            async with AsyncSessionLocal() as db:
                engine = AdaptiveDifficultyEngine(db)
                return await engine.select_difficulty_for_topic(int(user_id), topic)
        except Exception as e:
            self.logger.warning(f"⚠️ 自适应难度计算失败，使用默认 medium: {e}")
            return DIFFICULTY_MEDIUM

    def _create_resource_item(
        self,
        quiz_data: Dict[str, Any],
        kp: str,
        qtype: str,
        include_explanation: bool = True,  # MODIFIED: 新增参数
    ) -> ResourceItem:
        """将题目数据转为 ResourceItem"""
        # MODIFIED: 根据 include_explanation 控制内容中是否包含解析
        parts = [
            f"# {quiz_data['title']}",
            f"## 题目 ({qtype})",
            quiz_data['question']
        ]

        # 选择题添加选项
        if 'options' in quiz_data and quiz_data['options']:
            parts.append("\n".join(quiz_data['options']))

        # 答案（始终包含，供 /generate-answer 使用）
        parts.extend(["\n## 答案", quiz_data['answer']])

        # 解析（根据开关决定是否在 content 中包含）
        if include_explanation:
            parts.extend(["\n## 解析", quiz_data.get('explanation', '')])

        full_content = "\n".join(parts)

        # MODIFIED: extra_metadata 始终保留完整解析
        return ResourceItem(
            resource_type="quiz",
            title=quiz_data['title'],
            content=full_content,
            knowledge_points=[kp],
            status=RESOURCE_STATUS_COMPLETED,
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            is_reusable=True,
            extra_metadata={
                "quiz_type": qtype,
                "answer": quiz_data['answer'],
                "explanation": quiz_data.get('explanation', ''),
                "difficulty": quiz_data.get('difficulty', DIFFICULTY_MEDIUM),
                "knowledge_point": kp,  # 记录知识点，防止漂移
                "question_hash": self._generate_hash(quiz_data),
            }
        )

    def _generate_hash(self, quiz_data: Dict[str, Any]) -> str:
        """生成题目唯一哈希，用于去重"""
        hash_str = f"{quiz_data.get('type','')}{quiz_data.get('question','')}{quiz_data.get('answer','')}"
        return hashlib.md5(hash_str.encode('utf-8')).hexdigest()[:QUESTION_HASH_TRUNCATE_LENGTH]
