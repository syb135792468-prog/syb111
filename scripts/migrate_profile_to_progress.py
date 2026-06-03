"""
数据迁移脚本：将 user_profiles 中已有的 mastered_points 和 weak_points 同步到 learning_progress 表
运行方式：python -m scripts.migrate_profile_to_progress
"""
import asyncio
import sys
import os

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal
from models.profile import UserProfile
from models.progress import LearningProgress
from utils.knowledge_base import normalize_to_backend


async def migrate():
    print("开始数据迁移：user_profiles -> learning_progress ...")

    async with AsyncSessionLocal() as db:
        # 获取所有有画像的用户
        result = await db.execute(
            select(UserProfile).where(
                UserProfile.is_active == True,
            )
        )
        profiles = result.scalars().all()

        total_synced = 0

        for profile in profiles:
            user_id = profile.user_id
            mastered_points = profile.mastered_points or []
            weak_points = profile.weak_points or []

            # 同步已掌握的知识点
            for point in mastered_points:
                std = normalize_to_backend(point)
                if not std:
                    print(f"  ⚠️ 无法标准化知识点: {point}，跳过")
                    continue

                # 检查是否已存在
                existing = await db.execute(
                    select(LearningProgress).where(
                        LearningProgress.user_id == user_id,
                        LearningProgress.topic == std,
                        LearningProgress.is_active == True,
                    )
                )
                record = existing.scalar_one_or_none()

                if record is None:
                    record = LearningProgress(user_id=user_id, topic=std)
                    db.add(record)
                record.update_progress(status="completed", score=100.0, duration=0, overwrite_duration=True)
                total_synced += 1
                print(f"  ✅ 用户{user_id}: {std} -> completed (100)")

            # 同步薄弱知识点（仅当没有已有记录时）
            for point in weak_points:
                std = normalize_to_backend(point)
                if not std:
                    print(f"  ⚠️ 无法标准化知识点: {point}，跳过")
                    continue

                existing = await db.execute(
                    select(LearningProgress).where(
                        LearningProgress.user_id == user_id,
                        LearningProgress.topic == std,
                        LearningProgress.is_active == True,
                    )
                )
                record = existing.scalar_one_or_none()

                if record is None:
                    record = LearningProgress(user_id=user_id, topic=std)
                    db.add(record)
                    record.update_progress(status="in_progress", score=20.0, duration=0)
                    total_synced += 1
                    print(f"  ✅ 用户{user_id}: {std} -> in_progress (20)")

        await db.commit()
        print(f"\n迁移完成！共同步了 {total_synced} 条学习进度记录")


if __name__ == "__main__":
    asyncio.run(migrate())
