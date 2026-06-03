"""
SQL DDL 解析器 — 纯 Python 正则实现，支持 MySQL / PostgreSQL / SQL Server
从 CREATE TABLE 语句中提取表结构、字段、主键、外键、索引、约束、注释
"""

import re
from typing import List, Dict, Any, Optional
from datetime import datetime


# ============================================================
# 公共数据结构
# ============================================================

def _empty_field() -> Dict[str, Any]:
    return {
        "name": "",
        "data_type": "",
        "length": "",
        "nullable": True,
        "default": None,
        "is_auto_increment": False,
        "is_primary_key": False,
        "comment": "",
    }


def _empty_table() -> Dict[str, Any]:
    return {
        "name": "",
        "comment": "",
        "schema": "",
        "database": "",
        "fields": [],
        "primary_keys": [],
        "foreign_keys": [],
        "indexes": [],
        "constraints": [],
    }


# ============================================================
# 顶层入口
# ============================================================

def parse_sql_tables(sql_text: str) -> Dict[str, Any]:
    """
    解析 SQL 文本中的所有 CREATE TABLE 语句。

    Returns:
        {
            "success": True/False,
            "database": "数据库名（如检测到 USE 语句）",
            "tables": [ {...}, ... ],
            "error": "错误信息（仅 success=False 时）",
            "suggestion": "修正建议（仅 success=False 时）",
        }
    """
    if not sql_text or not sql_text.strip():
        return _error_result("输入为空", "请提供有效的 SQL CREATE TABLE 建表语句")

    cleaned = _remove_comments(sql_text)

    # 检测是否存在 CREATE TABLE
    if not re.search(r'CREATE\s+TABLE', cleaned, re.IGNORECASE):
        return _error_result(
            "未找到 CREATE TABLE 语句",
            "请输入包含 CREATE TABLE 的建表语句，例如：\n"
            "CREATE TABLE users (\n  id INT PRIMARY KEY,\n  name VARCHAR(100)\n);"
        )

    # 检测 USE 语句获取数据库名
    database = ""
    use_match = re.search(r'USE\s+[`"\[]?(\w+)[`"\]]?', cleaned, re.IGNORECASE)
    if use_match:
        database = use_match.group(1)

    # 检测 CREATE DATABASE
    db_match = re.search(r'CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\[]?(\w+)[`"\]]?', cleaned, re.IGNORECASE)
    if db_match:
        database = db_match.group(1)

    tables = []
    errors = []

    # 用括号匹配方式提取 CREATE TABLE 块（正确处理嵌套括号）
    # 支持: table / schema.table / [dbo].[table] / `schema`.`table`
    _ID = r'[`"\[]?\w+[`"\]]?'  # 带可选引号/方括号的标识符
    ct_pattern = re.compile(
        rf'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?'
        rf'({_ID}(?:\.{_ID})?)\s*\(',
        re.IGNORECASE,
    )

    for ct_match in ct_pattern.finditer(cleaned):
        table_name_raw = ct_match.group(1)
        body_start = ct_match.end()  # 紧跟在 '(' 之后

        # 用括号计数找到匹配的 ')'
        body, body_end = _extract_balanced_parens(cleaned, body_start - 1)
        if body is None:
            errors.append(f"表 {table_name_raw} 括号不匹配，跳过")
            continue

        # 提取括号后面的部分（ENGINE、COMMENT 等）
        tail = cleaned[body_end + 1:].split(';')[0]

        table_comment_inline = ""
        comment_match = re.search(r"COMMENT\s*=?\s*['\"](.+?)['\"]", tail, re.IGNORECASE)
        if comment_match:
            table_comment_inline = comment_match.group(1)

        table = _empty_table()
        # 处理 schema.table 格式
        if '.' in table_name_raw:
            parts = table_name_raw.split('.', 1)
            table["schema"] = _strip_quotes(parts[0])
            table["name"] = _strip_quotes(parts[1])
        else:
            table["name"] = _strip_quotes(table_name_raw)

        table["database"] = database
        table["comment"] = table_comment_inline

        # 解析表体
        try:
            _parse_table_body(body, table)
        except Exception as e:
            errors.append(f"表 {table['name']} 解析异常: {e}")

        # 尝试从独立的 COMMENT 语句获取表注释（MySQL 风格）
        if not table["comment"]:
            comment_match = re.search(
                rf'ALTER\s+TABLE\s+[`"\[]?{re.escape(table["name"])}[`"\]]?\s+COMMENT\s*=?\s*[\'"](.+?)[\'"]',
                cleaned, re.IGNORECASE
            )
            if comment_match:
                table["comment"] = comment_match.group(1)

        tables.append(table)

    if not tables:
        return _error_result(
            "SQL 解析未提取到任何表结构",
            "请检查 SQL 语法是否正确，确保 CREATE TABLE 语句完整，包含括号和字段定义"
        )

    result = {
        "success": True,
        "database": database,
        "tables": tables,
    }
    if errors:
        result["partial_errors"] = errors
    return result


# ============================================================
# 表体解析
# ============================================================

def _parse_table_body(body: str, table: Dict[str, Any]) -> None:
    """解析 CREATE TABLE 括号内的内容"""
    items = _split_column_items(body)

    for item in items:
        item_stripped = item.strip()
        if not item_stripped:
            continue

        upper = item_stripped.upper().lstrip()

        # 跳过纯约束/索引定义行（已单独处理）
        if upper.startswith(('PRIMARY KEY', 'UNIQUE KEY', 'UNIQUE INDEX',
                             'INDEX', 'KEY', 'CONSTRAINT', 'CHECK',
                             'FOREIGN KEY', 'UNIQUE ')):
            _parse_constraint_line(item_stripped, table)
        else:
            # 普通字段定义
            field = _parse_field_line(item_stripped)
            if field:
                table["fields"].append(field)

    # 标记主键字段 & 收集行级主键
    for pk_name in table["primary_keys"]:
        for f in table["fields"]:
            if f["name"].lower() == pk_name.lower():
                f["is_primary_key"] = True

    # 将行级 PRIMARY KEY 字段补充到 primary_keys 列表
    existing_pks = {pk.lower() for pk in table["primary_keys"]}
    for f in table["fields"]:
        if f["is_primary_key"] and f["name"].lower() not in existing_pks:
            table["primary_keys"].append(f["name"])

    # 提取内联 REFERENCES 外键
    for f in table["fields"]:
        inline_fk = f.pop("_inline_fk", None)
        if inline_fk:
            table["foreign_keys"].append({
                "name": "",
                "local_column": f["name"],
                "reference_table": inline_fk["reference_table"],
                "reference_column": inline_fk["reference_column"],
                "on_delete": inline_fk.get("on_delete", ""),
                "on_update": inline_fk.get("on_update", ""),
                "description": f"{f['name']} → {inline_fk['reference_table']}.{inline_fk['reference_column']}",
            })


def _split_column_items(body: str) -> List[str]:
    """
    按顶层逗号分割字段/约束定义，正确处理括号嵌套和字符串内的逗号。
    """
    items = []
    depth = 0
    current = []
    in_quote = None

    for ch in body:
        if in_quote:
            current.append(ch)
            if ch == in_quote:
                in_quote = None
            continue

        if ch in ("'", '"'):
            in_quote = ch
            current.append(ch)
        elif ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            items.append(''.join(current))
            current = []
        else:
            current.append(ch)

    last = ''.join(current).strip()
    if last:
        items.append(last)

    return items


# ============================================================
# 字段解析
# ============================================================

def _parse_field_line(line: str) -> Optional[Dict[str, Any]]:
    """解析单个字段定义行"""
    line = line.strip().rstrip(',')
    if not line:
        return None

    field = _empty_field()

    # 字段名：反引号、双引号、方括号或裸标识符
    name_match = re.match(r'[`"\[]?(\w+)[`"\]]?\s+(.+)', line, re.DOTALL)
    if not name_match:
        return None

    field["name"] = name_match.group(1)
    rest = name_match.group(2).strip()

    # 如果这行是约束定义而非字段，跳过
    if field["name"].upper() in ('PRIMARY', 'UNIQUE', 'INDEX', 'KEY',
                                  'CONSTRAINT', 'CHECK', 'FOREIGN'):
        return None

    # 数据类型 + 长度
    type_match = re.match(
        r'[`"\[]?(\w+)[`"\]]?'
        r'(?:\s*\(\s*([^)]+)\s*\))?'
        r'\s*(.*)',
        rest, re.DOTALL
    )
    if type_match:
        field["data_type"] = type_match.group(1).upper()
        field["length"] = type_match.group(2).strip() if type_match.group(2) else ""
        rest = type_match.group(3).strip()

    # 解析属性
    rest_upper = rest.upper()

    # 自增
    if 'AUTO_INCREMENT' in rest_upper or 'IDENTITY' in rest_upper or 'SERIAL' in field["data_type"]:
        field["is_auto_increment"] = True

    # NOT NULL / NULL
    if 'NOT NULL' in rest_upper:
        field["nullable"] = False
    elif re.search(r'\bNULL\b', rest_upper) and 'NOT NULL' not in rest_upper:
        field["nullable"] = True

    # DEFAULT
    default_match = re.search(r"DEFAULT\s+(?:'([^']*)'|(\S+))", rest, re.IGNORECASE)
    if default_match:
        field["default"] = default_match.group(1) if default_match.group(1) is not None else default_match.group(2)

    # COMMENT
    comment_match = re.search(r"COMMENT\s+['\"](.+?)['\"]", rest, re.IGNORECASE)
    if comment_match:
        field["comment"] = comment_match.group(1)

    # PRIMARY KEY (行级)
    if re.search(r'\bPRIMARY\s+KEY\b', rest_upper):
        field["is_primary_key"] = True

    # 内联 REFERENCES（PostgreSQL 风格：col TYPE REFERENCES table(col)）
    ref_match = re.search(
        r'REFERENCES\s+[`"\[]?(\w+)[`"\]]?\s*\(\s*[`"\[]?(\w+)[`"\]]?\s*\)'
        r'(\s+ON\s+DELETE\s+(?:CASCADE|SET\s+NULL|RESTRICT|NO\s+ACTION|SET\s+DEFAULT))?'
        r'(\s+ON\s+UPDATE\s+(?:CASCADE|SET\s+NULL|RESTRICT|NO\s+ACTION|SET\s+DEFAULT))?',
        rest, re.IGNORECASE
    )
    if ref_match:
        on_delete = (ref_match.group(3) or "").strip()
        on_update = (ref_match.group(4) or "").strip()
        field["_inline_fk"] = {
            "reference_table": ref_match.group(1),
            "reference_column": ref_match.group(2),
            "on_delete": on_delete.replace("ON DELETE", "").strip() if on_delete else "",
            "on_update": on_update.replace("ON UPDATE", "").strip() if on_update else "",
        }

    # SERIAL / BIGSERIAL (PostgreSQL 自增)
    if field["data_type"] in ('SERIAL', 'BIGSERIAL', 'SMALLSERIAL'):
        field["is_auto_increment"] = True
        field["data_type"] = 'INT' if field["data_type"] == 'SERIAL' else 'BIGINT'

    return field


# ============================================================
# 约束/索引解析
# ============================================================

def _parse_constraint_line(line: str, table: Dict[str, Any]) -> None:
    """解析约束、索引、外键定义行"""
    line = line.strip().rstrip(',')
    upper = line.upper()

    # PRIMARY KEY
    pk_match = re.search(r'PRIMARY\s+KEY\s*\(([^)]+)\)', line, re.IGNORECASE)
    if pk_match:
        cols = _parse_column_list(pk_match.group(1))
        table["primary_keys"].extend(cols)
        table["constraints"].append({
            "name": "PRIMARY KEY",
            "type": "PRIMARY KEY",
            "columns": cols,
            "description": f"主键: {', '.join(cols)}",
        })
        return

    # FOREIGN KEY
    fk_match = re.search(
        r'(?:CONSTRAINT\s+[`"\[]?(\w+)[`"\]]?\s+)?'
        r'FOREIGN\s+KEY\s*\(([^)]+)\)\s*'
        r'REFERENCES\s+[`"\[]?(\w+(?:\.\w+)?)[`"\]]?\s*\(([^)]+)\)'
        r'(\s+ON\s+DELETE\s+(?:CASCADE|SET\s+NULL|RESTRICT|NO\s+ACTION|SET\s+DEFAULT))?'
        r'(\s+ON\s+UPDATE\s+(?:CASCADE|SET\s+NULL|RESTRICT|NO\s+ACTION|SET\s+DEFAULT))?',
        line, re.IGNORECASE
    )
    if fk_match:
        fk_name = fk_match.group(1) or ""
        local_cols = _parse_column_list(fk_match.group(2))
        ref_table = _strip_quotes(fk_match.group(3))
        ref_cols = _parse_column_list(fk_match.group(4))
        on_delete = (fk_match.group(5) or "").strip()
        on_update = (fk_match.group(6) or "").strip()

        for lc, rc in zip(local_cols, ref_cols):
            fk_entry = {
                "name": fk_name,
                "local_column": lc,
                "reference_table": ref_table,
                "reference_column": rc,
                "on_delete": on_delete.replace("ON DELETE", "").strip() if on_delete else "",
                "on_update": on_update.replace("ON UPDATE", "").strip() if on_update else "",
                "description": f"{lc} → {ref_table}.{rc}",
            }
            table["foreign_keys"].append(fk_entry)
        return

    # UNIQUE KEY / UNIQUE INDEX
    unique_match = re.search(
        r'(?:CONSTRAINT\s+[`"\[]?(\w+)[`"\]]?\s+)?'
        r'UNIQUE\s+(?:KEY|INDEX)?\s*[`"\[]?(\w+)?[`"\]]?\s*\(([^)]+)\)',
        line, re.IGNORECASE
    )
    if unique_match:
        idx_name = unique_match.group(2) or unique_match.group(1) or "UNIQUE"
        cols = _parse_column_list(unique_match.group(3))
        table["indexes"].append({
            "name": idx_name,
            "type": "UNIQUE",
            "columns": cols,
            "description": f"唯一索引: {', '.join(cols)}",
        })
        table["constraints"].append({
            "name": idx_name,
            "type": "UNIQUE",
            "columns": cols,
            "description": f"唯一约束: {', '.join(cols)}",
        })
        return

    # INDEX / KEY
    index_match = re.search(
        r'(?:INDEX|KEY)\s*[`"\[]?(\w+)?[`"\]]?\s*\(([^)]+)\)',
        line, re.IGNORECASE
    )
    if index_match:
        idx_name = index_match.group(1) or "idx"
        cols = _parse_column_list(index_match.group(2))
        table["indexes"].append({
            "name": idx_name,
            "type": "INDEX",
            "columns": cols,
            "description": f"索引: {', '.join(cols)}",
        })
        return

    # CHECK 约束
    check_match = re.search(
        r'(?:CONSTRAINT\s+[`"\[]?(\w+)[`"\]]?\s+)?CHECK\s*\((.+?)\)',
        line, re.IGNORECASE
    )
    if check_match:
        constraint_name = check_match.group(1) or "CHECK"
        table["constraints"].append({
            "name": constraint_name,
            "type": "CHECK",
            "columns": [],
            "description": f"检查约束: {check_match.group(2).strip()}",
        })
        return


def _parse_column_list(raw: str) -> List[str]:
    """解析括号内的列名列表"""
    cols = []
    for part in raw.split(','):
        col = _strip_quotes(part.strip())
        if col:
            cols.append(col)
    return cols


# ============================================================
# Markdown 文档生成
# ============================================================

def generate_ddl_doc_markdown(tables: List[Dict[str, Any]], db_name: str = "") -> str:
    """生成数据库表设计文档（Markdown 格式）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    name = db_name or "数据库设计"

    lines = [
        f"# {name} 表设计文档",
        "",
        "## 1. 数据库概述",
        f"- **数据库名称**: {name}",
        f"- **设计时间**: {now}",
        f"- **表数量**: {len(tables)}",
        "",
    ]

    for i, table in enumerate(tables, 1):
        tname = table["name"]
        tcomment = table.get("comment", "")
        lines.append(f"## 2.{i} {tname}")
        if tcomment:
            lines.append(f"- **表注释**: {tcomment}")
        lines.append("")

        # 字段表格
        lines.append("| 字段名 | 数据类型 | 长度 | 可为空 | 默认值 | 主键 | 自增 | 注释 |")
        lines.append("|--------|----------|------|--------|--------|------|------|------|")

        for f in table.get("fields", []):
            nullable = "是" if f["nullable"] else "否"
            default = str(f["default"]) if f["default"] is not None else "-"
            pk = "PK" if f["is_primary_key"] else "-"
            auto = "是" if f["is_auto_increment"] else "-"
            comment = f.get("comment", "-") or "-"
            length = f.get("length", "") or "-"
            lines.append(
                f"| {f['name']} | {f['data_type']} | {length} | {nullable} | {default} | {pk} | {auto} | {comment} |"
            )

        lines.append("")

        # 主键
        if table.get("primary_keys"):
            lines.append(f"**主键**: {', '.join(table['primary_keys'])}")
            lines.append("")

        # 外键
        if table.get("foreign_keys"):
            lines.append("### 外键关系")
            lines.append("| 本地字段 | 引用表 | 引用字段 | ON DELETE | ON UPDATE |")
            lines.append("|----------|--------|----------|----------|-----------|")
            for fk in table["foreign_keys"]:
                od = fk.get("on_delete", "-") or "-"
                ou = fk.get("on_update", "-") or "-"
                lines.append(f"| {fk['local_column']} | {fk['reference_table']} | {fk['reference_column']} | {od} | {ou} |")
            lines.append("")

        # 索引
        if table.get("indexes"):
            lines.append("### 索引信息")
            lines.append("| 索引名 | 类型 | 包含字段 |")
            lines.append("|--------|------|----------|")
            for idx in table["indexes"]:
                lines.append(f"| {idx['name']} | {idx['type']} | {', '.join(idx['columns'])} |")
            lines.append("")

        # 约束
        if table.get("constraints"):
            lines.append("### 约束信息")
            lines.append("| 约束名 | 类型 | 说明 |")
            lines.append("|--------|------|------|")
            for c in table["constraints"]:
                lines.append(f"| {c['name']} | {c['type']} | {c['description']} |")
            lines.append("")

    return "\n".join(lines)


# ============================================================
# 工具函数
# ============================================================

def _extract_balanced_parens(text: str, open_pos: int) -> tuple:
    """
    从 open_pos 位置的 '(' 开始，找到匹配的 ')'，返回括号内的内容和结束位置。
    正确处理嵌套括号和字符串内的括号。
    """
    if open_pos >= len(text) or text[open_pos] != '(':
        return None, open_pos

    depth = 0
    in_quote = None
    start = open_pos + 1

    for i in range(open_pos, len(text)):
        ch = text[i]
        if in_quote:
            if ch == in_quote:
                in_quote = None
            continue
        if ch in ("'", '"'):
            in_quote = ch
            continue
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                return text[start:i], i

    return None, len(text)


def _remove_comments(sql: str) -> str:
    """移除 SQL 注释"""
    # 移除 -- 单行注释
    sql = re.sub(r'--.*?$', '', sql, flags=re.MULTILINE)
    # 移除 # 单行注释（MySQL）
    sql = re.sub(r'#.*?$', '', sql, flags=re.MULTILINE)
    # 移除 /* ... */ 多行注释
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    return sql


def _strip_quotes(name: str) -> str:
    """去除标识符上的引号"""
    name = name.strip()
    if name and name[0] in ('`', '"', '[') and name[-1] in ('`', '"', ']'):
        return name[1:-1]
    return name


def _error_result(error: str, suggestion: str) -> Dict[str, Any]:
    return {
        "success": False,
        "error": error,
        "suggestion": suggestion,
        "tables": [],
        "database": "",
    }
