"""
utils/code_error_analyzer.py - 代码错误分析器
功能：检测Python代码错误，提供修复建议和学习指导
"""
from __future__ import annotations

import ast
import re
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import astor


class CodeErrorAnalyzer:
    """代码错误分析器：检测语法错误、逻辑错误、风格问题"""

    def __init__(self):
        self.error_patterns = [
            # 常见语法错误
            (r"SyntaxError.*unexpected.*indent", self._analyze_indent_error),
            (r"SyntaxError.*unexpected EOF", self._analyze_eof_error),
            (r"SyntaxError.*invalid syntax", self._analyze_invalid_syntax),
            (r"IndentationError", self._analyze_indent_error),
            
            # 常见运行时错误
            (r"NameError.*name.*is not defined", self._analyze_name_error),
            (r"TypeError.*'(\w+)'.*'(\w+)'", self._analyze_type_error),
            (r"IndexError.*list index out of range", self._analyze_index_error),
            (r"KeyError.*'", self._analyze_key_error),
            (r"ValueError", self._analyze_value_error),
            (r"AttributeError.*'(\w+)'.*object has no attribute", self._analyze_attribute_error),
            (r"ZeroDivisionError", self._analyze_zero_division_error),
            
            # 逻辑错误模式
            (r"for.*in.*range.*:", self._analyze_for_loop_pattern),
            (r"while.*:", self._analyze_while_loop_pattern),
            (r"def.*:", self._analyze_function_pattern),
        ]

    def analyze_code(self, code: str) -> Dict[str, Any]:
        """
        分析代码，返回错误信息和修复建议
        
        Args:
            code: Python代码字符串
            
        Returns:
            {
                'has_errors': bool,
                'errors': List[Dict],
                'suggestions': List[str],
                'fixed_code': Optional[str]
            }
        """
        result = {
            'has_errors': False,
            'errors': [],
            'suggestions': [],
            'fixed_code': None
        }

        # 1. 语法分析
        syntax_errors = self._check_syntax(code)
        if syntax_errors:
            result['has_errors'] = True
            result['errors'].extend(syntax_errors)
            result['suggestions'].extend(self._generate_syntax_suggestions(syntax_errors))

        # 2. 代码静态分析
        static_issues = self._static_analysis(code)
        if static_issues:
            result['has_errors'] = True
            result['errors'].extend(static_issues)
            result['suggestions'].extend(self._generate_static_suggestions(static_issues))

        # 3. 尝试修复代码
        if result['has_errors']:
            result['fixed_code'] = self._attempt_fix(code, result['errors'])

        return result

    def analyze_error_output(self, error_output: str) -> Dict[str, Any]:
        """
        分析错误输出，提取错误类型和修复建议
        
        Args:
            error_output: 错误输出字符串
            
        Returns:
            错误分析结果
        """
        result = {
            'error_type': 'unknown',
            'error_message': error_output,
            'suggestions': [],
            'related_topics': []
        }

        for pattern, handler in self.error_patterns:
            match = re.search(pattern, error_output)
            if match:
                result.update(handler(match, error_output))
                break

        return result

    def _check_syntax(self, code: str) -> List[Dict]:
        """检查语法错误"""
        errors = []
        try:
            ast.parse(code)
        except SyntaxError as e:
            errors.append({
                'type': 'SyntaxError',
                'line': e.lineno,
                'offset': e.offset,
                'message': str(e),
                'text': e.text.strip() if e.text else ''
            })
        except IndentationError as e:
            errors.append({
                'type': 'IndentationError',
                'line': e.lineno,
                'message': str(e),
                'text': e.text.strip() if e.text else ''
            })
        return errors

    def _static_analysis(self, code: str) -> List[Dict]:
        """静态代码分析，检测潜在问题"""
        issues = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return issues

        # 检查未使用的变量
        used_names = set()
        defined_names = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.add(node.id)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined_names.add(node.id)
            elif isinstance(node, ast.FunctionDef):
                defined_names.add(node.name)
            elif isinstance(node, ast.ClassDef):
                defined_names.add(node.name)

        unused = defined_names - used_names
        for name in unused:
            issues.append({
                'type': 'UnusedVariable',
                'message': f"变量 '{name}' 已定义但未使用",
                'suggestion': f"检查是否需要使用变量 '{name}'，或删除未使用的定义"
            })

        # 检查print语句（Python 3兼容性）
        for node in ast.walk(tree):
            if isinstance(node, ast.Print):
                issues.append({
                    'type': 'Python2Syntax',
                    'line': node.lineno,
                    'message': "使用了Python 2的print语句",
                    'suggestion': "请使用 print() 函数代替 print 语句"
                })

        # 检查比较运算符链式使用
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                if len(node.ops) > 1:
                    issues.append({
                        'type': 'ComparisonChain',
                        'line': node.lineno,
                        'message': "复杂的链式比较",
                        'suggestion': "考虑将复杂比较拆分成多个简单比较，提高可读性"
                    })

        return issues

    def _attempt_fix(self, code: str, errors: List[Dict]) -> Optional[str]:
        """尝试自动修复代码"""
        try:
            # 修复常见缩进问题
            lines = code.split('\n')
            fixed_lines = []
            
            for i, line in enumerate(lines):
                # 尝试修复缩进
                if any(e.get('line') == i + 1 and e['type'] in ['IndentationError', 'SyntaxError'] for e in errors):
                    # 检查是否缺少冒号
                    if line.strip() and not line.strip().endswith(':'):
                        if any(keyword in line.strip() for keyword in ['if', 'else', 'elif', 'for', 'while', 'def', 'class']):
                            line = line.rstrip() + ':'
                    # 检查缩进是否正确
                    prev_line = lines[i-1] if i > 0 else ''
                    if prev_line.strip().endswith(':') and not line.startswith(' ') and not line.startswith('\t'):
                        line = '    ' + line
                
                fixed_lines.append(line)
            
            return '\n'.join(fixed_lines)
            
        except Exception:
            return None

    def _generate_syntax_suggestions(self, errors: List[Dict]) -> List[str]:
        """生成语法错误修复建议"""
        suggestions = []
        for error in errors:
            if error['type'] == 'SyntaxError':
                suggestions.append(f"第{error['line']}行有语法错误，请检查：{error.get('text', '')}")
            elif error['type'] == 'IndentationError':
                suggestions.append(f"第{error['line']}行缩进错误，请确保使用一致的缩进（4个空格）")
        return suggestions

    def _generate_static_suggestions(self, issues: List[Dict]) -> List[str]:
        """生成静态分析建议"""
        suggestions = []
        for issue in issues:
            suggestions.append(issue.get('suggestion', issue['message']))
        return suggestions

    # ==================== 错误处理函数 ====================
    
    def _analyze_indent_error(self, match, error_output):
        return {
            'error_type': 'IndentationError',
            'suggestions': [
                "检查代码缩进是否一致（建议使用4个空格）",
                "确保冒号后有正确的缩进",
                "检查是否混用了空格和制表符"
            ],
            'related_topics': ["循环（for/while）", "函数定义与调用", "条件判断（if/elif/else）"]
        }

    def _analyze_eof_error(self, match, error_output):
        return {
            'error_type': 'EOFError',
            'suggestions': [
                "代码可能缺少闭合括号、引号或冒号",
                "检查是否有未闭合的函数调用",
                "检查字符串是否正确闭合"
            ],
            'related_topics': ["函数定义与调用", "字符串操作"]
        }

    def _analyze_invalid_syntax(self, match, error_output):
        return {
            'error_type': 'SyntaxError',
            'suggestions': [
                "检查该行代码的语法是否正确",
                "查看错误位置附近的符号是否正确",
                "确保关键字拼写正确"
            ],
            'related_topics': ["运算符与表达式", "条件判断（if/elif/else）"]
        }

    def _analyze_name_error(self, match, error_output):
        var_name = re.search(r"name '(\w+)' is not defined", error_output)
        var_name = var_name.group(1) if var_name else '变量'
        return {
            'error_type': 'NameError',
            'error_message': f"名称 '{var_name}' 未定义",
            'suggestions': [
                f"确保变量 '{var_name}' 在使用前已定义",
                f"检查 '{var_name}' 的拼写是否正确",
                "确认变量作用域是否正确"
            ],
            'related_topics': ["变量与数据类型", "函数定义与调用"]
        }

    def _analyze_type_error(self, match, error_output):
        types = match.groups() if len(match.groups()) >= 2 else ('', '')
        return {
            'error_type': 'TypeError',
            'error_message': f"类型错误：{types[0]} 与 {types[1]} 不兼容",
            'suggestions': [
                f"检查操作数的类型是否正确",
                f"考虑使用类型转换（如 int(), str()）",
                "确认函数参数类型是否匹配"
            ],
            'related_topics': ["变量与数据类型", "运算符与表达式"]
        }

    def _analyze_index_error(self, match, error_output):
        return {
            'error_type': 'IndexError',
            'suggestions': [
                "检查列表索引是否超出范围",
                "使用 len() 检查列表长度",
                "确认索引从0开始计数"
            ],
            'related_topics': ["列表与元组"]
        }

    def _analyze_key_error(self, match, error_output):
        key_match = re.search(r"KeyError: '(.*?)'", error_output)
        key = key_match.group(1) if key_match else '键'
        return {
            'error_type': 'KeyError',
            'error_message': f"字典中不存在键 '{key}'",
            'suggestions': [
                f"确保键 '{key}' 存在于字典中",
                "使用 dict.get() 方法提供默认值",
                "检查键的拼写是否正确"
            ],
            'related_topics': ["字典与集合"]
        }

    def _analyze_value_error(self, match, error_output):
        return {
            'error_type': 'ValueError',
            'suggestions': [
                "检查函数参数的值是否在有效范围内",
                "确认数据格式是否正确",
                "查看函数文档了解参数要求"
            ],
            'related_topics': ["函数定义与调用", "运算符与表达式"]
        }

    def _analyze_attribute_error(self, match, error_output):
        obj_type = match.group(1) if match.groups() else '对象'
        return {
            'error_type': 'AttributeError',
            'error_message': f"{obj_type} 对象没有该属性",
            'suggestions': [
                f"确认 {obj_type} 类型支持该属性",
                "检查属性名称拼写",
                "查看该类型的可用方法和属性"
            ],
            'related_topics': ["面向对象基础", "类与对象"]
        }

    def _analyze_zero_division_error(self, match, error_output):
        return {
            'error_type': 'ZeroDivisionError',
            'suggestions': [
                "确保除数不为零",
                "在除法前检查除数",
                "考虑使用 try-except 处理"
            ],
            'related_topics': ["运算符与表达式", "异常处理"]
        }

    def _analyze_for_loop_pattern(self, match, error_output):
        return {
            'error_type': 'PatternWarning',
            'suggestions': [
                "确认 for 循环语法正确（需要冒号）",
                "检查循环体缩进",
                "确认迭代对象是否正确"
            ],
            'related_topics': ["循环（for/while）"]
        }

    def _analyze_while_loop_pattern(self, match, error_output):
        return {
            'error_type': 'PatternWarning',
            'suggestions': [
                "确认 while 循环条件正确",
                "确保循环能终止（避免死循环）",
                "检查循环体缩进"
            ],
            'related_topics': ["循环（for/while）"]
        }

    def _analyze_function_pattern(self, match, error_output):
        return {
            'error_type': 'PatternWarning',
            'suggestions': [
                "确认函数定义语法正确",
                "检查函数体缩进",
                "确认返回值使用正确"
            ],
            'related_topics': ["函数定义与调用"]
        }


# 全局实例
code_error_analyzer = CodeErrorAnalyzer()


def analyze_code_with_suggestions(code: str) -> Dict[str, Any]:
    """便捷函数：分析代码并返回错误信息和建议"""
    return code_error_analyzer.analyze_code(code)


def analyze_error_with_suggestions(error_output: str) -> Dict[str, Any]:
    """便捷函数：分析错误输出并返回修复建议"""
    return code_error_analyzer.analyze_error_output(error_output)