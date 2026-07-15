"""
utils/visual_explainer.py - 图解生成器
功能：生成概念流程图、代码可视化、知识点关系图
支持：Mermaid语法输出，可直接在浏览器中渲染
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
import re


class VisualExplainer:
    """图解生成器：将概念和代码转换为可视化图表"""

    def __init__(self):
        self.node_id_counter = 0

    def generate_concept_map(self, topic: str, related_topics: List[str]) -> str:
        """
        生成概念关系图
        
        Args:
            topic: 中心概念
            related_topics: 相关概念列表
        
        Returns:
            Mermaid语法字符串
        """
        nodes = []
        edges = []
        
        # 中心节点
        center_id = self._get_node_id("center")
        nodes.append(f"{center_id}[{self._escape_mermaid(topic)}]")
        
        # 相关节点
        for i, rel_topic in enumerate(related_topics):
            node_id = self._get_node_id(f"topic_{i}")
            nodes.append(f"{node_id}({self._escape_mermaid(rel_topic)})")
            edges.append(f"{center_id} --> {node_id}")
        
        return f"""```mermaid
graph LR
    {"\n    ".join(nodes)}
    {"\n    ".join(edges)}
```"""

    def generate_flowchart(self, steps: List[str]) -> str:
        """
        生成流程图
        
        Args:
            steps: 步骤列表
        
        Returns:
            Mermaid语法字符串
        """
        nodes = []
        edges = []
        
        prev_id = None
        for i, step in enumerate(steps):
            node_id = self._get_node_id(f"step_{i}")
            nodes.append(f"{node_id}[{self._escape_mermaid(step)}]")
            
            if prev_id:
                edges.append(f"{prev_id} --> {node_id}")
            prev_id = node_id
        
        return f"""```mermaid
flowchart TD
    {"\n    ".join(nodes)}
    {"\n    ".join(edges)}
```"""

    def generate_code_flow(self, code: str) -> str:
        """
        生成代码执行流程图
        
        Args:
            code: Python代码
        
        Returns:
            Mermaid语法字符串
        """
        lines = code.strip().split('\n')
        nodes = []
        edges = []
        
        # 解析代码结构
        parsed = self._parse_code_structure(code)
        
        for i, item in enumerate(parsed):
            node_id = self._get_node_id(f"code_{i}")
            if item['type'] == 'function':
                nodes.append(f"{node_id}[[{self._escape_mermaid(item['content'])}]]")
            elif item['type'] == 'condition':
                nodes.append(f"{node_id}{{{self._escape_mermaid(item['content'])}}}")
            elif item['type'] == 'loop':
                nodes.append(f"{node_id}[repeat {self._escape_mermaid(item['content'])}]")
            else:
                nodes.append(f"{node_id}({self._escape_mermaid(item['content'])})")
            
            if i > 0:
                prev_id = self._get_node_id(f"code_{i-1}")
                edges.append(f"{prev_id} --> {node_id}")
        
        return f"""```mermaid
flowchart TD
    {"\n    ".join(nodes)}
    {"\n    ".join(edges)}
```"""

    def generate_variable_tracking(self, code: str) -> str:
        """
        生成变量追踪图
        
        Args:
            code: Python代码
        
        Returns:
            Mermaid语法字符串
        """
        variables = self._extract_variables(code)
        
        if not variables:
            return "```mermaid\nflowchart TD\n    A[无变量]\n```"
        
        nodes = []
        edges = []
        
        # 创建变量节点
        var_nodes = []
        for var_name, values in variables.items():
            var_id = self._get_node_id(f"var_{var_name}")
            value_str = " → ".join(values[-3:])  # 最近3个值
            var_nodes.append(f"{var_id}[{self._escape_mermaid(var_name)}: {self._escape_mermaid(value_str)}]")
        
        # 创建时间线
        timeline_id = self._get_node_id("timeline")
        nodes.append(f"{timeline_id}[执行过程]")
        
        for var_node in var_nodes:
            edges.append(f"{timeline_id} --> {var_node.split('[')[0]}")
        
        nodes.extend(var_nodes)
        
        return f"""```mermaid
graph LR
    {"\n    ".join(nodes)}
    {"\n    ".join(edges)}
```"""

    def generate_class_diagram(self, class_info: Dict[str, Any]) -> str:
        """
        生成类图
        
        Args:
            class_info: 类信息字典
        
        Returns:
            Mermaid语法字符串
        """
        class_name = class_info.get('name', 'Class')
        attributes = class_info.get('attributes', [])
        methods = class_info.get('methods', [])
        
        class_def = f"class {self._escape_mermaid(class_name)} {{"
        
        for attr in attributes:
            class_def += f"\n    {attr}"
        
        if attributes and methods:
            class_def += "\n    ---"
        
        for method in methods:
            class_def += f"\n    {method}"
        
        class_def += "\n}"
        
        return f"""```mermaid
classDiagram
    {class_def}
```"""

    def generate_sequence_diagram(self, interactions: List[Dict[str, str]]) -> str:
        """
        生成时序图
        
        Args:
            interactions: 交互列表
        
        Returns:
            Mermaid语法字符串
        """
        participants = set()
        messages = []
        
        for interaction in interactions:
            from_part = interaction.get('from', '')
            to_part = interaction.get('to', '')
            message = interaction.get('message', '')
            
            participants.add(from_part)
            participants.add(to_part)
            messages.append(f"{from_part}->>{to_part}: {self._escape_mermaid(message)}")
        
        participant_defs = [f"participant {p}" for p in participants]
        
        return f"""```mermaid
sequenceDiagram
    {"\n    ".join(participant_defs)}
    {"\n    ".join(messages)}
```"""

    def _parse_code_structure(self, code: str) -> List[Dict[str, str]]:
        """解析代码结构，提取关键节点"""
        lines = code.strip().split('\n')
        result = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            if stripped.startswith('def '):
                match = re.match(r'def (\w+)\(', stripped)
                func_name = match.group(1) if match else 'function'
                result.append({'type': 'function', 'content': f"定义函数: {func_name}"})
            elif stripped.startswith('class '):
                match = re.match(r'class (\w+)', stripped)
                class_name = match.group(1) if match else 'class'
                result.append({'type': 'function', 'content': f"定义类: {class_name}"})
            elif stripped.startswith('if ') or stripped.startswith('elif ') or stripped.startswith('else'):
                result.append({'type': 'condition', 'content': stripped[:30] + '...' if len(stripped) > 30 else stripped})
            elif stripped.startswith('for ') or stripped.startswith('while '):
                result.append({'type': 'loop', 'content': stripped[:30] + '...' if len(stripped) > 30 else stripped})
            elif '=' in stripped and not stripped.startswith('#'):
                # 变量赋值
                parts = stripped.split('=')
                var_name = parts[0].strip()
                result.append({'type': 'assignment', 'content': f"{var_name} = ..."})
            elif stripped.startswith('return '):
                result.append({'type': 'return', 'content': stripped})
            elif stripped.startswith('#'):
                # 注释作为说明
                result.append({'type': 'comment', 'content': stripped[1:].strip()})
        
        return result

    def _extract_variables(self, code: str) -> Dict[str, List[str]]:
        """提取变量及其值的变化"""
        variables = {}
        lines = code.strip().split('\n')
        
        for line in lines:
            stripped = line.strip()
            if '=' in stripped and not stripped.startswith('#'):
                # 简单赋值
                parts = stripped.split('=', 1)
                var_name = parts[0].strip()
                # 跳过关键字
                if var_name in ['def', 'class', 'if', 'elif', 'else', 'for', 'while', 'return', 'import', 'from']:
                    continue
                value = parts[1].strip()
                if var_name not in variables:
                    variables[var_name] = []
                variables[var_name].append(value)
        
        return variables

    def _get_node_id(self, prefix: str) -> str:
        """生成唯一节点ID"""
        self.node_id_counter += 1
        return f"{prefix}_{self.node_id_counter}"

    @staticmethod
    def _escape_mermaid(text: str) -> str:
        """转义Mermaid特殊字符"""
        return text.replace('"', '\\"').replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')


# 全局实例
visual_explainer = VisualExplainer()


def generate_concept_diagram(topic: str, related_topics: List[str]) -> str:
    """便捷函数：生成概念关系图"""
    return visual_explainer.generate_concept_map(topic, related_topics)


def generate_process_flowchart(steps: List[str]) -> str:
    """便捷函数：生成流程图"""
    return visual_explainer.generate_flowchart(steps)


def generate_code_visualization(code: str) -> str:
    """便捷函数：生成代码可视化图"""
    return visual_explainer.generate_code_flow(code)


def generate_variable_tracking_diagram(code: str) -> str:
    """便捷函数：生成变量追踪图"""
    return visual_explainer.generate_variable_tracking(code)