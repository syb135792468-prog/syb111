# ===== 第一行必须是 from __future__ =====
from __future__ import annotations

# ===== 紧接着设置环境变量，绕过 AppLocker =====
import os

os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["OTEL_SDK_DISABLED"] = "true"
# ==============================================

"""
RAG检索工具模块（软件杯A3赛题防幻觉核心 v5.0 最终修复版）
- ✅ 强制余弦距离，修正相似度计算
- ✅ 固定Embedding调用，确保构建和查询完全一致
- ✅ 禁用遥测，绕开Windows策略拦截
- ✅ 全局配置统一，完善日志记录
"""
from pathlib import Path
from typing import List, Dict, Optional, Any
import asyncio
import uuid
import hashlib

import chromadb
from chromadb.api.models.Collection import Collection

# 全局配置统一
from config.settings import settings
from config.model_config import VECTOR_DB_CONFIG
from utils.logger import get_logger
from config.constants import DEFAULT_DISTANCE_THRESHOLD, RAG_QUERY_MULTIPLIER, RAG_DISTANCE_PRECISION, RAG_SIMILARITY_DIVISOR

logger = get_logger(__name__, task_id="rag_core")


# ------------------------------
# 1. Embedding获取（固定复用 llm_client）
# ------------------------------
async def get_embeddings(texts: List[str], domain: str = "para") -> List[List[float]]:
    """获取文本向量（固定配置，确保构建和查询完全一致）"""
    try:
        from utils.llm_client import call_embedding
        embeddings = await call_embedding(texts, domain=domain)
        if embeddings:
            logger.info(f"✅ Embedding 调用成功，向量维度: {len(embeddings[0])}")
        return embeddings
    except Exception as e:
        logger.error(f"获取Embedding失败: {str(e)}", exc_info=True)
        raise


# ------------------------------
# 2. 修复版向量库管理器
# ------------------------------
class VectorDBManager:
    def __init__(self):
        self.client: Optional[chromadb.PersistentClient] = None
        self.collection: Optional[Collection] = None
        self._init_client()

    def _init_client(self) -> None:
        """初始化ChromaDB，强制余弦距离"""
        try:
            persist_dir = Path(settings.VECTOR_DB_PATH)
            persist_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"向量库持久化目录: {persist_dir.resolve()}")

            # 初始化客户端，禁用遥测
            self.client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=chromadb.Settings(anonymized_telemetry=False)
            )

            collection_name = VECTOR_DB_CONFIG.collection_name

            # 🔴 关键：尝试获取集合，如果不存在则创建（强制余弦距离）
            try:
                self.collection = self.client.get_collection(name=collection_name)
                # 检查是否是余弦距离，如果不是则删除重建
                if self.collection.metadata and self.collection.metadata.get("hnsw:space") != "cosine":
                    logger.warning("检测到旧集合使用错误的距离度量，正在删除重建...")
                    self.client.delete_collection(collection_name)
                    raise Exception("需要重建")
                doc_count = self.collection.count()
                logger.info(f"已加载向量集合: {collection_name}，当前文档数: {doc_count}")
            except Exception:
                # 🔴 强制创建余弦距离的集合
                self.collection = self.client.create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine", "description": "软件杯A3赛题Python课程知识库"}
                )
                logger.info(f"已创建新的向量集合（余弦距离）: {collection_name}")

        except Exception as e:
            logger.error(f"初始化向量库失败: {str(e)}", exc_info=True)
            raise

    async def _run_sync(self, func, *args, **kwargs) -> Any:
        """同步方法转异步"""
        return await asyncio.to_thread(func, *args, **kwargs)

    # ------------------------------
    # 核心业务方法
    # ------------------------------
    async def add_documents(
            self,
            documents: List[str],
            metadatas: Optional[List[Dict[str, Any]]] = None,
            ids: Optional[List[str]] = None,
            skip_duplicates: bool = True
    ) -> int:
        """批量添加文档"""
        if not documents:
            return 0

        try:
            if ids is None:
                ids = [str(uuid.uuid4()) for _ in documents]
            if metadatas is None:
                metadatas = [{} for _ in documents]

            # 去重逻辑
            if skip_duplicates:
                doc_hashes = [hashlib.md5(doc.encode("utf-8")).hexdigest() for doc in documents]
                existing_docs = await self._run_sync(
                    self.collection.get,
                    include=["metadatas"]
                )
                existing_hashes = set()
                if existing_docs["metadatas"]:
                    existing_hashes = {meta.get("doc_hash") for meta in existing_docs["metadatas"] if meta}

                filtered_docs, filtered_metas, filtered_ids = [], [], []
                for doc, meta, doc_id, doc_hash in zip(documents, metadatas, ids, doc_hashes):
                    if doc_hash not in existing_hashes:
                        filtered_docs.append(doc)
                        meta["doc_hash"] = doc_hash
                        filtered_metas.append(meta)
                        filtered_ids.append(doc_id)

                if len(filtered_docs) < len(documents):
                    logger.info(f"检测到 {len(documents) - len(filtered_docs)} 条重复文档，已跳过")
                if not filtered_docs:
                    logger.warning("所有文档均为重复，跳过添加")
                    return 0
                documents, metadatas, ids = filtered_docs, filtered_metas, filtered_ids

            # 获取Embedding
            embeddings = await get_embeddings(documents)

            # 添加到集合
            def _add():
                self.collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )

            await self._run_sync(_add)

            logger.info(f"✅ 成功添加 {len(documents)} 条文档到向量库")
            return len(documents)

        except Exception as e:
            logger.error(f"添加文档失败: {str(e)}", exc_info=True)
            raise

    async def query(
            self,
            query_text: str,
            top_k: Optional[int] = None,
            distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD  # 🔴 距离阈值，余弦距离值域0~2，越小越严格
    ) -> List[Dict[str, Any]]:
        """检索相关文档（修复版，正确的余弦距离过滤）"""
        if top_k is None:
            top_k = VECTOR_DB_CONFIG.top_k

        if not query_text or not query_text.strip():
            return []

        try:
            # 🔴 查询时用 domain="query"，构建时用 domain="para"
            query_embedding = await get_embeddings([query_text.strip()], domain="query")

            def _query():
                return self.collection.query(
                    query_embeddings=query_embedding,
                    n_results=top_k * RAG_QUERY_MULTIPLIER,
                    include=["documents", "metadatas", "distances"]
                )

            result = await self._run_sync(_query)

            relevant_docs = []
            if not result["documents"] or not result["documents"][0]:
                logger.warning(f"未检索到相关文档: {query_text[:50]}...")
                return relevant_docs

            for doc, meta, distance in zip(
                    result["documents"][0],
                    result["metadatas"][0],
                    result["distances"][0]
            ):
                # 🔴 只返回距离小于阈值的文档（距离越小，相似度越高）
                if distance <= distance_threshold:
                    relevant_docs.append({
                        "content": doc,
                        "metadata": meta or {},
                        "distance": round(float(distance), RAG_DISTANCE_PRECISION),
                        "similarity": round(1 - distance / RAG_SIMILARITY_DIVISOR, RAG_DISTANCE_PRECISION)  # 🔴 余弦距离正确转相似度
                    })

            # 按相似度降序排列
            relevant_docs.sort(key=lambda x: x["similarity"], reverse=True)
            return relevant_docs[:top_k]

        except Exception as e:
            logger.error(f"RAG检索失败: {str(e)}", exc_info=True)
            return []

    async def count(self) -> int:
        """获取文档总数"""
        return await self._run_sync(self.collection.count)

    async def clear_collection(self) -> None:
        """清空集合"""
        logger.warning("正在清空向量库集合...")
        await self._run_sync(self.collection.delete, where={})
        logger.info("✅ 向量库集合已清空")


# ------------------------------
# 3. 全局单例 + 快捷函数
# ------------------------------
_db_manager: Optional[VectorDBManager] = None


def get_db_manager() -> VectorDBManager:
    global _db_manager
    if _db_manager is None:
        _db_manager = VectorDBManager()
    return _db_manager


async def retrieve_relevant_documents(
        query: str,
        top_k: Optional[int] = None,
        distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD
) -> List[Dict[str, Any]]:
    manager = get_db_manager()
    return await manager.query(query, top_k=top_k, distance_threshold=distance_threshold)


async def add_documents_to_vector_db(
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
) -> int:
    manager = get_db_manager()
    return await manager.add_documents(documents, metadatas=metadatas, ids=ids)


# ------------------------------
# 4. 自测
# ------------------------------
if __name__ == "__main__":
    async def _test_rag():
        print("=" * 60)
        print("🔍 RAG检索工具模块自测 v5.0")
        print("=" * 60)
        manager = get_db_manager()

        try:
            count = await manager.count()
            print(f"当前文档数：{count}")

            if count == 0:
                test_docs = [
                    "Python的列表是一种有序的可变容器。",
                    "Python的元组是一种有序的不可变容器。",
                    "列表和元组的主要区别在于可变性。"
                ]
                added = await manager.add_documents(test_docs)
                print(f"添加 {added} 条测试文档")

            docs = await retrieve_relevant_documents("列表和元组区别", top_k=2)
            if docs:
                for i, doc in enumerate(docs, 1):
                    print(f"[{i}] 相似度: {doc['similarity']} | 距离: {doc['distance']} | {doc['content'][:80]}...")
            else:
                print("未检索到文档（请先构建向量库）")

            print("=" * 60)
            print("✅ RAG检索工具模块自测通过！")
        except Exception as e:
            print(f"❌ 自测失败: {e}")


    asyncio.run(_test_rag())