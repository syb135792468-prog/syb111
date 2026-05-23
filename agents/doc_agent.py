"""
agents/doc_agent.py - 软件杯A3 讲解文档生成智能体
规则+LLM双模式 | RAG防幻觉 | 输出Markdown格式文档
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List, ClassVar
import random

from agents.base_agent import BaseAgent
from graph.state import ResourceItem
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.constants import DEFAULT_RAG_TOP_K, RESOURCE_PROGRESS_COMPLETE
from utils.agent_helpers import match_knowledge_point, get_profile_from_context


class DocAgent(BaseAgent):
    """讲解文档生成智能体：生成结构化的Python知识点学习文档"""

    DEMO_DOC_BANK: ClassVar[Dict[str, str]] = {
        "变量与数据类型": """# Python 变量与数据类型

## 什么是变量
变量是用来存储数据的容器。在Python中，创建变量不需要声明类型。

```python
name = "张三"       # 字符串类型
age = 20            # 整数类型
height = 1.75       # 浮点类型
is_student = True   # 布尔类型
```

## 数据类型

| 类型 | 示例 | 说明 |
|------|------|------|
| int | `42` | 整数 |
| float | `3.14` | 浮点数 |
| str | `"hello"` | 字符串 |
| bool | `True` | 布尔值 |
| list | `[1,2,3]` | 列表 |
| dict | `{"a":1}` | 字典 |

## 类型转换
```python
x = "10"
y = int(x)      # 字符串转整数
z = float(x)    # 字符串转浮点数
s = str(100)    # 整数转字符串
```

## 注意事项
- 变量名只能包含字母、数字和下划线
- 变量名不能以数字开头
- 变量名不能是Python关键字（如 `if`、`for`、`class`）
""",

        "循环（for/while）": """# Python 循环

## for 循环
用于遍历序列（列表、字符串、range等）。

```python
# 遍历列表
fruits = ["苹果", "香蕉", "橙子"]
for fruit in fruits:
    print(fruit)

# 使用 range()
for i in range(5):      # 0, 1, 2, 3, 4
    print(i)

for i in range(1, 6):   # 1, 2, 3, 4, 5
    print(i)
```

## while 循环
条件为True时持续执行。

```python
count = 0
while count < 5:
    print(count)
    count += 1
```

## 循环控制
- `break`：跳出整个循环
- `continue`：跳过本次迭代
- `else`：循环正常结束后执行

```python
for i in range(10):
    if i == 3:
        continue    # 跳过3
    if i == 7:
        break       # 到7停止
    print(i)
```

## 常见错误
1. **死循环**：while条件永远为True
2. **修改遍历中的列表**：应遍历副本 `list[:]`
""",

        "函数定义与调用": """# Python 函数

## 定义函数
```python
def greet(name):
    # 问候函数
    return f"你好，{name}！"

result = greet("张三")
print(result)  # 你好，张三！
```

## 参数类型
```python
# 位置参数
def add(a, b):
    return a + b

# 默认参数
def greet(name, greeting="你好"):
    return f"{greeting}，{name}！"

# 可变参数
def sum_all(*args):
    return sum(args)

# 关键字参数
def print_info(**kwargs):
    for key, value in kwargs.items():
        print(f"{key}: {value}")
```

## 返回值
```python
# 返回单个值
def square(x):
    return x ** 2

# 返回多个值（元组）
def min_max(numbers):
    return min(numbers), max(numbers)

lo, hi = min_max([3, 1, 4, 1, 5])
```

## 作用域
- 函数内定义的变量是**局部变量**
- 函数外定义的变量是**全局变量**
- 使用 `global` 关键字在函数内修改全局变量
""",

        "列表与元组": """# Python 列表与元组

## 列表（list）— 可变序列
```python
fruits = ["苹果", "香蕉", "橙子"]

# 访问元素
print(fruits[0])     # 苹果
print(fruits[-1])    # 橙子

# 修改
fruits.append("葡萄")    # 末尾添加
fruits.insert(1, "芒果") # 指定位置插入
fruits.remove("香蕉")    # 删除指定元素
popped = fruits.pop()    # 弹出末尾元素
```

## 列表推导式
```python
squares = [x**2 for x in range(10)]
evens = [x for x in range(20) if x % 2 == 0]
```

## 元组（tuple）— 不可变序列
```python
point = (3, 4)
x, y = point    # 解包

# 元组不可修改
# point[0] = 5  # TypeError!
```

## 何时用哪个？
- 需要修改 → 用 **list**
- 数据不应被修改 → 用 **tuple**（更安全、更快）
""",
    }

    def __init__(
        self,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
        use_llm: bool = False,
    ) -> None:
        super().__init__(
            agent_name="doc",
            scene_name="document_generation",
            enable_rag=True,
            user_id=user_id,
            task_id=task_id,
        )
        self.use_llm = use_llm

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        target_kp = self._get_target_knowledge_point(user_input, context)
        self.logger.info(f"目标知识点：{target_kp}")

        if self.use_llm:
            content = await self._llm_generate(target_kp)
        else:
            content = self._rule_generate(target_kp)

        resource = ResourceItem(
            resource_type="doc",
            title=f"{target_kp} 学习文档",
            content=content,
            knowledge_points=[target_kp],
            status="completed",
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            is_reusable=True,
            extra_metadata={"rag_used": self.enable_rag},
        )

        new_resources = self._append_resource(context, resource)
        self.logger.info(f"文档生成完成：{resource.title}")
        return self._build_result(new_resources)

    def _rule_generate(self, kp: str) -> str:
        content = self.DEMO_DOC_BANK.get(kp)
        if not content:
            kp = random.choice(list(self.DEMO_DOC_BANK.keys()))
            content = self.DEMO_DOC_BANK[kp]
        return content

    async def _llm_generate(self, kp: str) -> str:
        rag_context = await self._get_rag_context(kp, top_k=DEFAULT_RAG_TOP_K)

        system_prompt = f"""你是专业的Python教学文档编写专家。
请为知识点"{kp}"生成一份结构化的学习文档。

要求：
- 使用Markdown格式
- 包含：标题、概念说明、代码示例、注意事项
- 语言通俗易懂，适合初学者
- 代码示例必须正确可运行

参考教材内容：
{rag_context if rag_context else '无参考资料'}"""

        try:
            resp = await self._call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请生成关于 {kp} 的学习文档"},
            ])
            if not resp.strip():
                raise ValueError("LLM返回空内容")
            return resp
        except Exception as e:
            self.logger.warning(f"LLM文档生成失败，降级规则模式: {e}")
            return self._rule_generate(kp)

    def _get_target_knowledge_point(
        self, user_input: str, context: Optional[Dict[str, Any]] = None,
    ) -> str:
        text = user_input.lower()
        matched = match_knowledge_point(text)
        if matched:
            return matched
        if context:
            profile = get_profile_from_context(context)
            weak = profile.get("weak_points", [])
            if weak:
                return random.choice(weak)
        return random.choice(PYTHON_KNOWLEDGE_POINTS)
