"""
concept_to_animation.py - Matplotlib备用动画引擎
【定位说明】
- 这是一个独立的演示/备用方案，与主HTML模板路径（video_agent.py）完全独立
- 主框架使用 HTML+GSAP+WebSpeech 生成教学动画（更丰富、更稳定）
- 本模块使用 Matplotlib 生成简单动画（用于演示或无浏览器环境）

【使用场景】
1. 演示/测试：快速验证动画逻辑
2. 备用方案：当HTML路径失败时的降级选项
3. 纯Python环境：无浏览器时的动画生成

【与主框架的关系】
- video_agent.py：主路径，生成HTML教学动画（推荐）
- video_renderer.py：将HTML录制为真实视频文件
- 本模块：备用路径，生成Matplotlib动画（简单）

【注意】
- 本模块不与 video_schema.py 的 AnimationScript 数据结构兼容
- 如需整合，需要额外的适配层
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import re


class ConceptToAnimationEngine:
    """
    概念→动画生成引擎
    核心逻辑（跟 Fogsight 一致）：
    1. 文本语义理解 → 拆解知识点
    2. 可视化逻辑设计 → 生成动画脚本
    3. 动画代码生成 → 渲染可播放动画
    """

    def __init__(self):
        self.animation = None
        self.script = ""
        self.title = ""

    # ============================================================
    # 第1步：文本语义理解（拆解知识点）
    # ============================================================
    def _parse_concept(self, user_input: str) -> Dict[str, Any]:
        """
        拆解用户输入的知识点文本
        （模拟 Fogsight 的 LLM 拆解逻辑）
        """
        user_input = user_input.lower()

        # 识别知识点类型
        concept_type = "unknown"
        if "列表" in user_input or "list" in user_input or "序列" in user_input:
            concept_type = "list_traversal"
        elif "循环" in user_input or "for" in user_input or "while" in user_input:
            concept_type = "for_loop"
        elif "函数" in user_input or "function" in user_input or "def" in user_input:
            concept_type = "function_call"
        elif "变量" in user_input or "variable" in user_input:
            concept_type = "variable"

        # 提取核心关键词
        keywords = re.findall(r"[\u4e00-\u9fa5a-zA-Z]+", user_input)

        return {
            "type": concept_type,
            "keywords": keywords,
            "raw_input": user_input
        }

    # ============================================================
    # 第2步：可视化逻辑设计（生成动画脚本）
    # ============================================================
    def _generate_animation_script(self, parsed: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        根据拆解的知识点，生成动画分镜脚本
        （模拟 Fogsight 的动画分镜生成逻辑）
        """
        concept_type = parsed["type"]
        script = []

        if concept_type == "list_traversal":
            self.title = "Python 列表遍历动画演示"
            script = [
                {"time": 0, "text": "列表遍历开始", "data": [1, 2, 3, 4, 5], "highlight": -1},
                {"time": 1, "text": "第 1 次遍历：元素 = 1", "data": [1, 2, 3, 4, 5], "highlight": 0},
                {"time": 2, "text": "第 2 次遍历：元素 = 2", "data": [1, 2, 3, 4, 5], "highlight": 1},
                {"time": 3, "text": "第 3 次遍历：元素 = 3", "data": [1, 2, 3, 4, 5], "highlight": 2},
                {"time": 4, "text": "第 4 次遍历：元素 = 4", "data": [1, 2, 3, 4, 5], "highlight": 3},
                {"time": 5, "text": "第 5 次遍历：元素 = 5", "data": [1, 2, 3, 4, 5], "highlight": 4},
                {"time": 6, "text": "列表遍历完成！", "data": [1, 2, 3, 4, 5], "highlight": -1},
            ]
        elif concept_type == "for_loop":
            self.title = "Python for 循环执行过程"
            script = [
                {"time": 0, "text": "for 循环开始", "i": 0, "total": 0},
                {"time": 1, "text": "i = 1, 累加和 = 1", "i": 1, "total": 1},
                {"time": 2, "text": "i = 2, 累加和 = 3", "i": 2, "total": 3},
                {"time": 3, "text": "i = 3, 累加和 = 6", "i": 3, "total": 6},
                {"time": 4, "text": "i = 4, 累加和 = 10", "i": 4, "total": 10},
                {"time": 5, "text": "i = 5, 累加和 = 15", "i": 5, "total": 15},
                {"time": 6, "text": "for 循环结束！", "i": 5, "total": 15},
            ]
        elif concept_type == "function_call":
            self.title = "Python 函数调用流程"
            script = [
                {"time": 0, "text": "调用函数 add(3, 5)", "step": 0},
                {"time": 1, "text": "参数传递：a = 3, b = 5", "step": 1},
                {"time": 2, "text": "执行计算：3 + 5", "step": 2},
                {"time": 3, "text": "返回结果：8", "step": 3},
            ]
        else:
            self.title = "Python 知识点动画演示"
            script = [
                {"time": 0, "text": "知识点演示开始", "step": 0},
                {"time": 1, "text": "核心逻辑讲解", "step": 1},
                {"time": 2, "text": "演示完成", "step": 2},
            ]

        self.script = "\n".join([f"【{s['time']}s】{s['text']}" for s in script])
        return script

    # ============================================================
    # 第3步：动画代码生成 + 渲染（输出可播放动画）
    # ============================================================
    def _render_animation(self, script: List[Dict[str, Any]], concept_type: str):
        """
        根据动画脚本，渲染可播放的动画
        （模拟 Fogsight 的代码驱动动画渲染逻辑）
        """
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.set_title(self.title, fontsize=16, fontweight="bold")
        ax.axis("off")

        # 文本显示
        main_text = ax.text(5, 5, "", fontsize=20, ha="center", va="center")
        detail_text = ax.text(5, 2, "", fontsize=14, ha="center", va="center", color="gray")

        # 列表可视化（如果是列表遍历）
        bars = []
        if concept_type == "list_traversal":
            data = script[0]["data"]
            x = np.arange(len(data))
            bars = ax.bar(x + 2, data, width=0.6, color="skyblue")
            ax.set_xlim(0, 10)
            ax.set_ylim(0, max(data) + 2)

        def update(frame):
            current_scene = script[frame]
            main_text.set_text(current_scene["text"])

            # 列表高亮
            if concept_type == "list_traversal" and bars:
                highlight_idx = current_scene.get("highlight", -1)
                for i, bar in enumerate(bars):
                    if i == highlight_idx:
                        bar.set_color("orange")
                    else:
                        bar.set_color("skyblue")

            # 细节显示
            if "i" in current_scene:
                detail_text.set_text(f"当前变量 i = {current_scene.get('i', 0)}")
            elif "step" in current_scene:
                detail_text.set_text(f"执行步骤 {current_scene.get('step', 0)}")
            else:
                detail_text.set_text("")

            return main_text, detail_text, *bars

        # 生成动画
        self.animation = animation.FuncAnimation(
            fig, update, frames=len(script), interval=1200, blit=True, repeat=True
        )

        return self.animation

    # ============================================================
    # 对外接口：一句话生成动画
    # ============================================================
    def generate(self, user_input: str, show: bool = True) -> Dict[str, Any]:
        """
        核心接口：输入知识点文本，输出动画
        （跟 Fogsight.ai 的使用方式完全一致）

        Args:
            user_input: 你想要讲解的内容，比如 "讲解 Python 列表的遍历"
            show: 是否直接弹出播放动画

        Returns:
            包含动画、脚本、标题的字典
        """
        print(f"🎯 正在解析知识点：{user_input}")

        # 第1步：拆解知识点
        parsed = self._parse_concept(user_input)
        print(f"✅ 知识点类型识别：{parsed['type']}")

        # 第2步：生成动画脚本
        script = self._generate_animation_script(parsed)
        print(f"✅ 动画脚本生成完成，共 {len(script)} 帧")

        # 第3步：渲染动画
        animation = self._render_animation(script, parsed["type"])
        print(f"✅ 动画渲染完成！")

        # 直接播放动画
        if show:
            print("🎬 正在播放动画...")
            plt.show()

        return {
            "title": self.title,
            "script": self.script,
            "animation": animation,
            "concept_type": parsed["type"]
        }


# ============================================================
# 测试代码（直接运行这个文件就能看到效果）
# ============================================================
if __name__ == "__main__":
    # 初始化引擎
    engine = ConceptToAnimationEngine()

    # 👇 这里输入你想要讲解的内容，比如：
    # "讲解 Python 列表的遍历"
    # "讲解 for 循环的执行过程"
    # "讲解函数调用的流程"
    user_input = "讲解 Python 的函数"

    # 生成并播放动画
    result = engine.generate(user_input, show=True)

    # 打印生成的脚本
    print("\n" + "="*50)
    print("📜 生成的动画脚本：")
    print(result["script"])
    print("="*50)