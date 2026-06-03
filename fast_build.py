import asyncio
import sys
from pathlib import Path

# 🔴 修改1：正确设置项目根目录路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.model_config import PYTHON_KB_PATH
from config.constants import FAST_BUILD_CHUNK_SIZE, FAST_BUILD_API_INTERVAL_SEC
from utils.rag_utils import get_db_manager


async def main():
    m = get_db_manager()

    # 🔴 修改2：强制清空旧库（因为旧库完全无效，必须彻底重建）
    print("⚠️  正在清空旧的无效向量库...")
    try:
        await m.clear_collection()
        print("✅ 旧库已清空")
    except Exception as e:
        print(f"⚠️  清空旧库时出错（可能是空库），继续: {e}")

    # 读取并切分文件
    files = sorted(PYTHON_KB_PATH.glob("*.md")) + sorted(PYTHON_KB_PATH.glob("*.txt"))
    chunks = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        for i in range(0, len(text), FAST_BUILD_CHUNK_SIZE):
            chunk = text[i:i + FAST_BUILD_CHUNK_SIZE].strip()
            if chunk:
                chunks.append((chunk, f.name))

    total = len(chunks)
    est_minutes = total * 0.6 / 60
    print(f"\n📦 共切分 {total} 个片段，开始逐条入库（QPS=2，预计 {est_minutes:.1f} 分钟）...")

    success = 0
    for idx, (doc, source) in enumerate(chunks):
        try:
            await m.add_documents([doc], metadatas=[{"source": source}], skip_duplicates=False)
            success += 1
        except Exception as e:
            print(f"\n⚠️  第 {idx + 1} 条入库失败: {e}")

        # 🔴 修改3：显式控制请求频率（每条间隔0.6秒，避免API限流）
        if idx < total - 1:
            await asyncio.sleep(FAST_BUILD_API_INTERVAL_SEC)

        # 显示进度
        pct = (idx + 1) / total * 100
        print(f"⏳ 进度: {pct:.1f}% ({idx + 1}/{total})", end="\r")

    final = await m.count()
    print(f"\n\n✅ 构建完成！成功入库 {success}/{total} 条，总文档数: {final}")


if __name__ == "__main__":
    asyncio.run(main())