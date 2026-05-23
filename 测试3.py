import asyncio
from utils.rag_utils import retrieve_relevant_documents


async def main():
    print("🔍 测试查询：列表和元组有什么区别？")
    docs = await retrieve_relevant_documents(
        "列表和元组有什么区别",
        top_k=3,
        distance_threshold=1.0  # 宽松阈值，确保能出结果
    )

    print(f"\n✅ 检索到 {len(docs)} 条文档：")
    for i, d in enumerate(docs):
        print(f"\n【结果 {i + 1} | 相似度: {d['similarity']} | 距离: {d['distance']}】")
        print(f"  来源: {d['metadata'].get('source', '未知')}")
        print(f"  内容: {d['content'][:300]}")


if __name__ == "__main__":
    asyncio.run(main())