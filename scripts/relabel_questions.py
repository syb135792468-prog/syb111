"""
scripts/relabel_questions.py - LLM 重标历史题目知识点映射

策略：
1. 遍历所有 quiz/daily_challenge/daily_extra 类型的 resource
2. 把整个 content 发给 LLM，让它分题并标注 1-3 个知识点 code + 权重
3. 写入 question_knowledge_map 表
4. 幂等：已标注的 (resource_id, question_index) 跳过
5. 断点续传：每个 resource 标注完立即 commit
6. 人工抽样校验：打印每题映射结果

使用：
    python -m scripts.relabel_questions              # 重标所有未标注的
    python -m scripts.relabel_questions --dry-run    # 只打印不写库
    python -m scripts.relabel_questions --resource-id 133  # 只重标指定 resource
    python -m scripts.relabel_questions --force       # 强制重标（先删旧记录）
"""
from __future__ import annotations
import asyncio
import argparse
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal, init_db, engine
from models.resource import Resource
from models.knowledge_graph import KnowledgeNode, QuestionKnowledgeMap
from utils.llm_client import get_async_llm_client
from utils.logger import get_logger

logger = get_logger(__name__, task_id="relabel")


# ==================== 常量 ====================

QUIZ_RESOURCE_TYPES = ("quiz", "daily_challenge", "daily_extra")
MAX_NODES_PER_QUESTION = 3
LLM_MAX_TOKENS = 2000
LLM_TEMPERATURE = 0.1  # 低温度保证标注稳定


# ==================== Prompt 构建 ====================

def build_system_prompt(node_list: list[dict]) -> str:
    """构建系统 prompt，含 65 个知识点列表"""
    nodes_text = "\n".join(
        f"- {n['code']}: {n['name']}（{n['module']}, 难度{n['difficulty']}）"
        for n in node_list
    )
    return f"""你是Python知识点标注专家。任务：分析题目，从下方知识点列表中选出该题考察的知识点。

## 知识点列表（共 {len(node_list)} 个）
{nodes_text}

## 标注规则
1. 每道题选 1-3 个知识点，优先选最核心的
2. 权重 0-1，所有权重总和必须为 1
3. 如果题目包含多道子题（如"练习题5道"），分别标注每道子题，question_index 从 0 开始
4. 如果只有一道题，question_index = 0
5. 只能使用列表中存在的 code，不要编造

## 返回格式（严格 JSON）
{{
  "questions": [
    {{
      "question_index": 0,
      "question_brief": "题目简述（20字内）",
      "nodes": [
        {{"code": "py_xxx", "weight": 0.6}},
        {{"code": "py_yyy", "weight": 0.4}}
      ]
    }}
  ]
}}"""


def build_user_prompt(resource: Resource) -> str:
    """构建用户 prompt，含题目内容"""
    content = resource.content or ""
    # 截断超长 content，避免 token 爆炸
    if len(content) > 3000:
        content = content[:3000] + "\n\n[内容已截断]"
    return f"""## 资源信息
- 标题：{resource.title}
- 类型：{resource.resource_type}

## 题目内容
{content}

请分析并返回 JSON。"""


# ==================== LLM 调用与解析 ====================

async def label_resource(
    client,
    resource: Resource,
    node_codes: set[str],
    system_prompt: str,
) -> list[dict]:
    """调 LLM 标注一个 resource 的所有题目"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": build_user_prompt(resource)},
    ]

    try:
        raw = await client.call(
            messages,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        logger.error(f"resource {resource.id} LLM 调用失败: {e}")
        # 尝试备用模型
        try:
            raw = await client.call_fallback(
                messages,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                response_format={"type": "json_object"},
            )
        except Exception as e2:
            logger.error(f"resource {resource.id} 备用模型也失败: {e2}")
            return []

    # 解析 JSON
    try:
        # 清理可能的 markdown 代码块包裹
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

        data = json.loads(raw)
        questions = data.get("questions", [])
    except json.JSONDecodeError as e:
        logger.error(f"resource {resource.id} JSON 解析失败: {e}")
        logger.debug(f"原始返回: {raw[:500]}")
        return []

    # 校验并过滤
    valid_questions = []
    for q in questions:
        qidx = q.get("question_index", 0)
        nodes = q.get("nodes", [])
        if not nodes:
            continue

        # 过滤无效 code，归一化权重
        valid_nodes = []
        for n in nodes:
            code = n.get("code", "")
            weight = float(n.get("weight", 0))
            if code in node_codes and weight > 0:
                valid_nodes.append({"code": code, "weight": weight})

        if not valid_nodes:
            continue

        # 权重归一化
        total = sum(n["weight"] for n in valid_nodes)
        if total > 0:
            for n in valid_nodes:
                n["weight"] = round(n["weight"] / total, 3)

        # 最多 3 个节点
        valid_nodes = valid_nodes[:MAX_NODES_PER_QUESTION]

        valid_questions.append({
            "question_index": qidx,
            "question_brief": q.get("question_brief", ""),
            "nodes": valid_nodes,
        })

    return valid_questions


# ==================== 主流程 ====================

async def relabel(
    dry_run: bool = False,
    resource_id_filter: Optional[int] = None,
    force: bool = False,
) -> None:
    logger.info("=" * 60)
    logger.info("LLM 重标历史题目知识点映射")
    logger.info("=" * 60)

    await init_db()

    # 1. 加载知识点列表
    async with AsyncSessionLocal() as session:
        nodes = (
            await session.execute(
                select(KnowledgeNode)
                .where(KnowledgeNode.is_active == 1)
                .order_by(KnowledgeNode.module, KnowledgeNode.level)
            )
        ).scalars().all()
        node_list = [
            {"code": n.code, "name": n.name, "module": n.module, "difficulty": n.difficulty}
            for n in nodes
        ]
        node_codes = {n.code for n in nodes}
    logger.info(f"已加载 {len(node_list)} 个知识点")

    # 2. 查询待标注的 resource
    async with AsyncSessionLocal() as session:
        stmt = select(Resource).where(
            Resource.resource_type.in_(QUIZ_RESOURCE_TYPES),
            Resource.is_active == 1,
        )
        if resource_id_filter:
            stmt = stmt.where(Resource.id == resource_id_filter)
        stmt = stmt.order_by(Resource.id)
        resources = (await session.execute(stmt)).scalars().all()
    logger.info(f"待标注 resource 数: {len(resources)}")

    # 3. 逐个标注
    client = get_async_llm_client()
    system_prompt = build_system_prompt(node_list)

    total_labeled = 0
    total_skipped = 0
    total_failed = 0

    for res in resources:
        # 检查是否已标注（幂等）
        async with AsyncSessionLocal() as session:
            existing = (
                await session.execute(
                    select(QuestionKnowledgeMap).where(
                        QuestionKnowledgeMap.resource_id == res.id
                    )
                )
            ).scalars().all()

            if existing and not force:
                logger.info(f"[跳过] resource {res.id} 已有 {len(existing)} 条映射，--force 可重标")
                total_skipped += 1
                continue

            if existing and force:
                logger.info(f"[强制重标] resource {res.id} 先删旧 {len(existing)} 条")
                await session.execute(
                    delete(QuestionKnowledgeMap).where(
                        QuestionKnowledgeMap.resource_id == res.id
                    )
                )
                await session.commit()

        # 调 LLM 标注
        logger.info(f"[标注] resource {res.id} - {res.title[:40]}")
        questions = await label_resource(client, res, node_codes, system_prompt)

        if not questions:
            logger.warning(f"  ❌ resource {res.id} 标注失败或返回空")
            total_failed += 1
            continue

        # 打印结果供抽样校验
        for q in questions:
            nodes_str = ", ".join(f"{n['code']}({n['weight']})" for n in q["nodes"])
            logger.info(f"  q{q['question_index']} [{q['question_brief']}]: {nodes_str}")

        # 写库
        if not dry_run:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    for q in questions:
                        for n in q["nodes"]:
                            session.add(QuestionKnowledgeMap(
                                resource_id=res.id,
                                question_index=q["question_index"],
                                node_code=n["code"],
                                weight=n["weight"],
                            ))
            logger.info(f"  ✅ 已写入 {len(questions)} 题")

        total_labeled += 1

    logger.info("=" * 60)
    logger.info(f"完成: 标注 {total_labeled}, 跳过 {total_skipped}, 失败 {total_failed}")
    logger.info("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM 重标历史题目知识点")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写库")
    parser.add_argument("--resource-id", type=int, help="只重标指定 resource")
    parser.add_argument("--force", action="store_true", help="强制重标（先删旧记录）")
    args = parser.parse_args()

    asyncio.run(relabel(
        dry_run=args.dry_run,
        resource_id_filter=args.resource_id,
        force=args.force,
    ))
