"""
知识库构建脚本（软件杯A3赛题显式里程碑 v2.2 全局最终版）
- ✅ 全局配置统一：100% 从 config 读取全部参数
- ✅ 接口完全对齐：使用 utils/rag_utils 的懒加载单例 + 已有异步方法
- ✅ 去重逻辑复用：直接使用 rag_utils 的 add_documents 去重，返回实际添加数
- ✅ 切分优化：在句子/段落边界处断开，保持语义完整
- ✅ 工程化完善：命令行参数、进度显示、异常保护、空库提示
- ✅ 运行方式：python scripts/build_kb.py [--clear] [--chunk-size 500] [--no-dup-check]
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
import sys
import asyncio
import argparse

# 将项目根目录加入 sys.path，确保可以导入项目内模块
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import settings
from config.model_config import VECTOR_DB_CONFIG, PYTHON_KB_PATH
from utils.logger import get_logger
from utils.rag_utils import get_db_manager  # 🔴 修复1：使用懒加载单例，避免模块导入时初始化

logger = get_logger(__name__, task_id="build_kb")


def load_and_split_documents(
        kb_dir: Path,
        chunk_size: int = None,
        chunk_overlap: int = None
) -> List[Dict[str, Any]]:
    """
    读取知识库目录下的所有 .md/.txt 文件，并切分为语义较完整的 chunk
    - 支持 .md 和 .txt 两种格式
    - 在句子/段落边界处断开，避免语义割裂
    - 保留文件元数据（相对路径、知识点、文件名）
    """
    # 使用默认配置（如果未提供）
    chunk_size = chunk_size or VECTOR_DB_CONFIG.chunk_size
    chunk_overlap = chunk_overlap or VECTOR_DB_CONFIG.chunk_overlap

    if not kb_dir.exists():
        logger.error(f"知识库目录不存在: {kb_dir.resolve()}")
        raise FileNotFoundError(f"知识库目录不存在: {kb_dir.resolve()}")

    # 收集所有 .md 和 .txt 文件（按文件名排序，保证顺序稳定）
    doc_files = []
    for ext in (".md", ".txt"):
        doc_files.extend(kb_dir.rglob(f"*{ext}"))
    doc_files = sorted(doc_files)  # 排序保证每次构建顺序一致

    if not doc_files:
        logger.warning("未找到任何 .md 或 .txt 文件，构建中止")
        print("\n💡 提示：请在 data/knowledge_base/python_basics/ 目录下放置教材文件")
        print("   示例文件可参考之前提供的 01_变量与数据类型.md")
        return []

    all_chunks = []
    for doc_file in doc_files:
        doc_file = Path(doc_file).resolve()  # ✅ 就加这一行
        try:
            content = doc_file.read_text(encoding="utf-8")
            if not content.strip():
                logger.warning(f"文件为空，跳过: {doc_file.name}")
                continue

            # 提取知识点名称（文件名去掉序号前缀，如 01_变量与数据类型.md → 变量与数据类型）
            topic = doc_file.stem.split("_", 1)[-1] if "_" in doc_file.stem else doc_file.stem

            # 🔴 优化：语义切分（在句子/段落边界处断开，优先级从高到低）
            chunks = []
            start = 0
            text_len = len(content)
            # 断句分隔符优先级：段落结束 → 中文句号+换行 → 中文句号 → 英文句号+换行 → 英文句号 → 换行 → 空格
            separators = ["\n\n", "。\n", "。", ".\n", ".", "\n", " "]

            while start < text_len:
                end = start + chunk_size
                if end < text_len:
                    # 在 chunk 范围内寻找最靠后的断句位置
                    for sep in separators:
                        pos = content.rfind(sep, start, end)
                        if pos > start:
                            end = pos + len(sep)
                            break
                # 提取并清理 chunk
                chunk_text = content[start:end].strip()
                if chunk_text:
                    chunks.append({
                        "content": chunk_text,
                        "metadata": {
                            "source": str(doc_file.relative_to(project_root)),
                            "topic": topic,
                            "file_name": doc_file.name,
                            "file_ext": doc_file.suffix
                        }
                    })
                # 滑动窗口（重叠部分）
                start = end - chunk_overlap

            all_chunks.extend(chunks)
            logger.info(f"  已处理: {doc_file.name} → {len(chunks)} 个片段")
        except Exception as e:
            logger.error(f"处理文件失败 {doc_file.name}: {e}", exc_info=True)

    logger.info(f"总计生成 {len(all_chunks)} 个文本片段")
    return all_chunks


async def build_knowledge_base(
        clear_existing: bool,
        chunk_size: int,
        chunk_overlap: int,
        skip_duplicates: bool
) -> None:
    """
    构建知识库主流程：
    1. 清空旧库（可选）
    2. 读取并切分教材
    3. 批量向量化并存入向量库（自动去重）
    4. 验证构建结果
    """
    print("=" * 60)
    print("📚 软件杯A3 知识库构建脚本 v2.2")
    print("=" * 60)

    try:
        # 1. 获取向量库管理器（懒加载，首次调用才初始化）
        manager = get_db_manager()

        # 2. 清空旧库（如果指定）
        if clear_existing:
            print("\n⚠️  正在清空已有向量库...")
            await manager.clear_collection()
            print("✅ 已清空向量库")

        # 3. 读取并切分教材
        print(f"\n📂 知识库目录: {PYTHON_KB_PATH.resolve()}")
        chunks = load_and_split_documents(PYTHON_KB_PATH, chunk_size, chunk_overlap)
        if not chunks:
            print("\n❌ 未找到有效教材文件，构建中止")
            return

        # 4. 批量向量化并存入向量库（🔴 修复2：复用rag_utils的add_documents，自动去重）
        print(f"\n🚀 开始向量化（共 {len(chunks)} 个片段）...")
        documents = [c["content"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        # 🔴 修复3：使用add_documents的返回值（去重后的实际添加数）
        added_count = await manager.add_documents(
            documents=documents,
            metadatas=metadatas,
            skip_duplicates=skip_duplicates
        )

        # 5. 验证构建结果（🔴 修复4：使用rag_utils的count()异步方法，不需要自己写_run_sync）
        final_count = await manager.count()

        # 6. 输出最终结果
        print("\n" + "=" * 60)
        print(f"✅ 知识库构建成功！")
        print(f"   原始片段数: {len(chunks)}")
        print(f"   去重后新增: {added_count}")
        print(f"   集合总文档数: {final_count}")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 知识库构建失败: {str(e)}")
        logger.error(f"知识库构建失败: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Python 课程知识库构建脚本")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="清空已有向量库后重新构建"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=VECTOR_DB_CONFIG.chunk_size,
        help=f"切分块大小（默认: {VECTOR_DB_CONFIG.chunk_size}）"
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=VECTOR_DB_CONFIG.chunk_overlap,
        help=f"切分块重叠大小（默认: {VECTOR_DB_CONFIG.chunk_overlap}）"
    )
    parser.add_argument(
        "--no-dup-check",
        action="store_false",
        dest="skip_duplicates",
        help="禁用基于内容的去重检查（默认启用）"
    )
    args = parser.parse_args()

    # 确保知识库目录存在
    PYTHON_KB_PATH.mkdir(parents=True, exist_ok=True)

    # 运行构建流程
    asyncio.run(build_knowledge_base(
        clear_existing=args.clear,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        skip_duplicates=args.skip_duplicates
    ))