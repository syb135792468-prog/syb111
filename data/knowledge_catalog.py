"""
data/knowledge_catalog.py - Python 知识图谱种子目录

65 个知识点，9 个模块，68 条前置依赖边。
设计原则：
- code 用稳定 snake_case（py_xxx），跨环境迁移不变
- aliases 保留旧中文知识点名称，用于 name-based 回退匹配
- level: 1=基础（语法/类型/控制流），2=进阶（函数/数据结构/文件/模块），3=高级（OOP/进阶）
- difficulty 0-1：基础 0.1-0.3，进阶 0.35-0.55，高级 0.45-0.65
- estimated_time 单位分钟
"""
from __future__ import annotations


# ============================================================
# 节点定义：65 个
# ============================================================
NODES = [
    # ---------- 模块1: basics 基础语法 (12) ----------
    {"code": "py_intro", "name": "Python简介与环境", "module": "basics", "level": 1,
     "difficulty": 0.10, "estimated_time": 15, "aliases": [],
     "description": "Python语言特点、应用领域、解释器与开发环境搭建"},
    {"code": "py_print", "name": "输出与print", "module": "basics", "level": 1,
     "difficulty": 0.15, "estimated_time": 10, "aliases": [],
     "description": "print函数、sep/end参数、多值输出、格式化输出基础"},
    {"code": "py_comment", "name": "注释", "module": "basics", "level": 1,
     "difficulty": 0.10, "estimated_time": 5, "aliases": [],
     "description": "单行注释#、多行注释、文档字符串docstring"},
    {"code": "py_variable", "name": "变量与赋值", "module": "basics", "level": 1,
     "difficulty": 0.20, "estimated_time": 15, "aliases": ["变量与数据类型"],
     "description": "变量命名规则、赋值、多重赋值、动态类型"},
    {"code": "py_input", "name": "输入input", "module": "basics", "level": 1,
     "difficulty": 0.20, "estimated_time": 10, "aliases": [],
     "description": "input函数、类型转换、用户交互基础"},
    {"code": "py_arith", "name": "算术运算符", "module": "basics", "level": 1,
     "difficulty": 0.20, "estimated_time": 15, "aliases": ["运算符与表达式"],
     "description": "加减乘除、整除、取模、幂运算、运算优先级"},
    {"code": "py_compare", "name": "比较运算符", "module": "basics", "level": 1,
     "difficulty": 0.20, "estimated_time": 10, "aliases": [],
     "description": "==、!=、<、>、<=、>=、链式比较"},
    {"code": "py_logic", "name": "逻辑运算符", "module": "basics", "level": 1,
     "difficulty": 0.25, "estimated_time": 15, "aliases": [],
     "description": "and/or/not、短路求值、布尔上下文中的真值测试"},
    {"code": "py_assign_op", "name": "赋值运算符", "module": "basics", "level": 1,
     "difficulty": 0.25, "estimated_time": 10, "aliases": [],
     "description": "复合赋值+=、-=、*=、/=、海象运算符:="},
    {"code": "py_type_convert", "name": "类型转换", "module": "basics", "level": 1,
     "difficulty": 0.25, "estimated_time": 15, "aliases": [],
     "description": "int/float/str/bool/list等显式转换、隐式转换规则"},
    {"code": "py_fstring", "name": "f-string格式化", "module": "basics", "level": 1,
     "difficulty": 0.25, "estimated_time": 15, "aliases": [],
     "description": "f-string、format方法、对齐与精度、表达式嵌入"},
    {"code": "py_indent", "name": "缩进与代码块", "module": "basics", "level": 1,
     "difficulty": 0.20, "estimated_time": 10, "aliases": [],
     "description": "Python缩进规则、代码块界定、PEP8规范"},

    # ---------- 模块2: datatypes 数据类型 (10) ----------
    {"code": "py_number", "name": "数字类型int/float", "module": "datatypes", "level": 1,
     "difficulty": 0.20, "estimated_time": 15, "aliases": [],
     "description": "整数、浮点数、精度问题、math模块基础"},
    {"code": "py_bool", "name": "布尔类型", "module": "datatypes", "level": 1,
     "difficulty": 0.20, "estimated_time": 10, "aliases": [],
     "description": "True/False、truthy/falsy、布尔运算"},
    {"code": "py_str_basic", "name": "字符串基础", "module": "datatypes", "level": 1,
     "difficulty": 0.25, "estimated_time": 15, "aliases": ["字符串操作"],
     "description": "字符串定义、转义、拼接、不可变性"},
    {"code": "py_str_method", "name": "字符串方法", "module": "datatypes", "level": 1,
     "difficulty": 0.35, "estimated_time": 20, "aliases": [],
     "description": "split/join/replace/strip/find/upper/lower等常用方法"},
    {"code": "py_str_slice", "name": "字符串切片", "module": "datatypes", "level": 1,
     "difficulty": 0.30, "estimated_time": 15, "aliases": [],
     "description": "切片语法[start:stop:step]、负索引、反转字符串"},
    {"code": "py_list_basic", "name": "列表基础", "module": "datatypes", "level": 1,
     "difficulty": 0.25, "estimated_time": 15, "aliases": ["列表与元组"],
     "description": "列表创建、索引、可变性、遍历"},
    {"code": "py_list_method", "name": "列表方法", "module": "datatypes", "level": 1,
     "difficulty": 0.35, "estimated_time": 20, "aliases": [],
     "description": "append/insert/remove/pop/sort/reverse/index"},
    {"code": "py_list_comp", "name": "列表推导式", "module": "datatypes", "level": 1,
     "difficulty": 0.45, "estimated_time": 20, "aliases": [],
     "description": "[expr for x in iter if cond]、嵌套推导式、性能优势"},
    {"code": "py_tuple", "name": "元组", "module": "datatypes", "level": 1,
     "difficulty": 0.30, "estimated_time": 15, "aliases": [],
     "description": "元组不可变性、解包、命名元组、应用场景"},
    {"code": "py_dict_basic", "name": "字典基础", "module": "datatypes", "level": 1,
     "difficulty": 0.35, "estimated_time": 20, "aliases": ["字典与集合"],
     "description": "键值对、增删改查、in判断、遍历items/keys/values"},

    # ---------- 模块3: control_flow 控制流 (6) ----------
    {"code": "py_if", "name": "条件语句if-elif-else", "module": "control_flow", "level": 1,
     "difficulty": 0.25, "estimated_time": 20, "aliases": ["条件判断（if/elif/else）"],
     "description": "if-elif-else结构、嵌套条件、三元表达式"},
    {"code": "py_while", "name": "while循环", "module": "control_flow", "level": 1,
     "difficulty": 0.30, "estimated_time": 20, "aliases": [],
     "description": "while循环、循环条件、无限循环、累加器模式"},
    {"code": "py_for", "name": "for循环", "module": "control_flow", "level": 1,
     "difficulty": 0.30, "estimated_time": 20, "aliases": ["循环（for/while）"],
     "description": "for-in遍历、enumerate、zip、迭代可迭代对象"},
    {"code": "py_range", "name": "range函数", "module": "control_flow", "level": 1,
     "difficulty": 0.25, "estimated_time": 10, "aliases": [],
     "description": "range(start,stop,step)、惰性求值、与for配合"},
    {"code": "py_break_continue", "name": "break与continue", "module": "control_flow", "level": 1,
     "difficulty": 0.30, "estimated_time": 15, "aliases": [],
     "description": "break跳出循环、continue跳过本次、else子句"},
    {"code": "py_nested_loop", "name": "嵌套循环", "module": "control_flow", "level": 1,
     "difficulty": 0.40, "estimated_time": 25, "aliases": [],
     "description": "双层循环、二维遍历、九九乘法表、打印图形"},

    # ---------- 模块4: functions 函数 (8) ----------
    {"code": "py_func_def", "name": "函数定义与调用", "module": "functions", "level": 2,
     "difficulty": 0.35, "estimated_time": 25, "aliases": ["函数定义与调用"],
     "description": "def、参数传递、调用、返回默认None、文档字符串"},
    {"code": "py_func_param", "name": "函数参数与默认值", "module": "functions", "level": 2,
     "difficulty": 0.40, "estimated_time": 25, "aliases": ["函数参数与返回值"],
     "description": "位置参数、关键字参数、默认值、可变默认值陷阱"},
    {"code": "py_func_return", "name": "返回值", "module": "functions", "level": 2,
     "difficulty": 0.35, "estimated_time": 20, "aliases": [],
     "description": "return语句、多值返回、None返回、早返回"},
    {"code": "py_func_args_kwargs", "name": "*args和**kwargs", "module": "functions", "level": 2,
     "difficulty": 0.50, "estimated_time": 25, "aliases": [],
     "description": "可变位置参数、可变关键字参数、参数解包"},
    {"code": "py_lambda", "name": "lambda表达式", "module": "functions", "level": 2,
     "difficulty": 0.45, "estimated_time": 20, "aliases": [],
     "description": "匿名函数、与map/filter/sort配合、闭包陷阱"},
    {"code": "py_scope", "name": "作用域LEGB", "module": "functions", "level": 2,
     "difficulty": 0.50, "estimated_time": 25, "aliases": [],
     "description": "Local/Enclosing/Global/Builtin、global/nonlocal"},
    {"code": "py_recursion", "name": "递归", "module": "functions", "level": 2,
     "difficulty": 0.55, "estimated_time": 30, "aliases": [],
     "description": "递归基线、递归调用、栈溢出、典型问题（阶乘/斐波那契）"},
    {"code": "py_decorator", "name": "装饰器基础", "module": "functions", "level": 2,
     "difficulty": 0.65, "estimated_time": 35, "aliases": [],
     "description": "函数作为对象、装饰器语法糖、functools.wraps、常见用途"},

    # ---------- 模块5: data_structures 数据结构进阶 (6) ----------
    {"code": "py_dict_method", "name": "字典方法", "module": "data_structures", "level": 2,
     "difficulty": 0.40, "estimated_time": 20, "aliases": [],
     "description": "get/setdefault/update/pop/items、defaultdict"},
    {"code": "py_dict_comp", "name": "字典推导式", "module": "data_structures", "level": 2,
     "difficulty": 0.50, "estimated_time": 20, "aliases": [],
     "description": "{k:v for...}、反转字典、计数模式"},
    {"code": "py_set", "name": "集合", "module": "data_structures", "level": 2,
     "difficulty": 0.40, "estimated_time": 20, "aliases": [],
     "description": "集合创建、交并差对称差、去重、成员测试"},
    {"code": "py_nested_data", "name": "嵌套数据结构", "module": "data_structures", "level": 2,
     "difficulty": 0.50, "estimated_time": 25, "aliases": [],
     "description": "列表嵌字典、字典嵌列表、JSON风格数据访问"},
    {"code": "py_sort", "name": "排序sorted与sort", "module": "data_structures", "level": 2,
     "difficulty": 0.40, "estimated_time": 20, "aliases": [],
     "description": "sorted vs list.sort、key参数、reverse、稳定排序"},
    {"code": "py_collections", "name": "collections模块", "module": "data_structures", "level": 2,
     "difficulty": 0.55, "estimated_time": 30, "aliases": [],
     "description": "Counter/deque/defaultdict/namedtuple/OrderedDict"},

    # ---------- 模块6: file_exception 文件与异常 (6) ----------
    {"code": "py_file_read", "name": "文件读取", "module": "file_exception", "level": 2,
     "difficulty": 0.35, "estimated_time": 20, "aliases": ["文件操作"],
     "description": "open/read/readline/readlines、编码、迭代文件"},
    {"code": "py_file_write", "name": "文件写入", "module": "file_exception", "level": 2,
     "difficulty": 0.35, "estimated_time": 20, "aliases": [],
     "description": "write/writelines、模式w/a、flush、编码问题"},
    {"code": "py_with", "name": "with语句", "module": "file_exception", "level": 2,
     "difficulty": 0.40, "estimated_time": 20, "aliases": [],
     "description": "上下文管理器、自动关闭、多资源管理"},
    {"code": "py_try_except", "name": "try-except", "module": "file_exception", "level": 2,
     "difficulty": 0.40, "estimated_time": 25, "aliases": ["异常处理"],
     "description": "try-except-else-finally、多异常捕获、异常传递"},
    {"code": "py_raise", "name": "raise与自定义异常", "module": "file_exception", "level": 2,
     "difficulty": 0.50, "estimated_time": 25, "aliases": [],
     "description": "raise语句、自定义异常类、异常链from"},
    {"code": "py_exception_type", "name": "常见异常类型", "module": "file_exception", "level": 2,
     "difficulty": 0.35, "estimated_time": 20, "aliases": [],
     "description": "ValueError/TypeError/KeyError/IndexError/AttributeError等"},

    # ---------- 模块7: modules 模块与包 (4) ----------
    {"code": "py_import", "name": "import语句", "module": "modules", "level": 2,
     "difficulty": 0.30, "estimated_time": 20, "aliases": ["模块与包"],
     "description": "import模块、as别名、from导入、__name__"},
    {"code": "py_from_import", "name": "from-import", "module": "modules", "level": 2,
     "difficulty": 0.30, "estimated_time": 15, "aliases": [],
     "description": "from...import、导入特定对象、*导入陷阱"},
    {"code": "py_package", "name": "包与__init__.py", "module": "modules", "level": 2,
     "difficulty": 0.40, "estimated_time": 25, "aliases": [],
     "description": "包结构、__init__.py、相对导入、命名空间包"},
    {"code": "py_stdlib", "name": "常用标准库", "module": "modules", "level": 2,
     "difficulty": 0.40, "estimated_time": 30, "aliases": [],
     "description": "os/sys/pathlib/json/datetime/random/re等常用标准库"},

    # ---------- 模块8: oop 面向对象 (8) ----------
    {"code": "py_class", "name": "类与对象", "module": "oop", "level": 3,
     "difficulty": 0.45, "estimated_time": 30, "aliases": ["面向对象基础", "类与对象"],
     "description": "class定义、实例化、类与实例区别、属性访问"},
    {"code": "py_attribute", "name": "属性与方法", "module": "oop", "level": 3,
     "difficulty": 0.45, "estimated_time": 25, "aliases": [],
     "description": "实例属性、类属性、实例方法、类方法、静态方法"},
    {"code": "py_init", "name": "__init__构造器", "module": "oop", "level": 3,
     "difficulty": 0.50, "estimated_time": 25, "aliases": [],
     "description": "__init__、self参数、初始化属性、__new__区别"},
    {"code": "py_self", "name": "self参数", "module": "oop", "level": 3,
     "difficulty": 0.45, "estimated_time": 20, "aliases": [],
     "description": "self本质、显式传递、实例引用、与Java this对比"},
    {"code": "py_inherit", "name": "继承", "module": "oop", "level": 3,
     "difficulty": 0.55, "estimated_time": 30, "aliases": ["继承与多态"],
     "description": "单继承、多继承、MRO、super()、object基类"},
    {"code": "py_override", "name": "方法重写", "module": "oop", "level": 3,
     "difficulty": 0.55, "estimated_time": 25, "aliases": [],
     "description": "方法重写、super调用父类、多态、运行时绑定"},
    {"code": "py_magic", "name": "魔术方法", "module": "oop", "level": 3,
     "difficulty": 0.60, "estimated_time": 35, "aliases": [],
     "description": "__str__/__repr__/__eq__/__len__/__getitem__等双下方法"},
    {"code": "py_property", "name": "property装饰器", "module": "oop", "level": 3,
     "difficulty": 0.60, "estimated_time": 30, "aliases": [],
     "description": "@property、getter/setter、只读属性、计算属性"},

    # ---------- 模块9: advanced 进阶 (5) ----------
    {"code": "py_iterator", "name": "迭代器", "module": "advanced", "level": 3,
     "difficulty": 0.55, "estimated_time": 30, "aliases": [],
     "description": "迭代器协议__iter__/__next__、iter()、next()、StopIteration"},
    {"code": "py_generator", "name": "生成器yield", "module": "advanced", "level": 3,
     "difficulty": 0.60, "estimated_time": 35, "aliases": [],
     "description": "yield、生成器函数、惰性求值、yield from、协程基础"},
    {"code": "py_context_manager", "name": "上下文管理器", "module": "advanced", "level": 3,
     "difficulty": 0.60, "estimated_time": 30, "aliases": [],
     "description": "__enter__/__exit__、contextlib、自定义上下文管理器"},
    {"code": "py_type_hint", "name": "类型提示", "module": "advanced", "level": 3,
     "difficulty": 0.45, "estimated_time": 25, "aliases": [],
     "description": "typing模块、List/Dict/Optional/Union、泛型、mypy"},
    {"code": "py_venv", "name": "虚拟环境与pip", "module": "advanced", "level": 3,
     "difficulty": 0.30, "estimated_time": 20, "aliases": [],
     "description": "venv创建、激活、pip install、requirements.txt、依赖管理"},
]


# ============================================================
# 边定义：68 条前置依赖（source 是 target 的前置）
# ============================================================
EDGES = [
    # ---------- basics 内部 ----------
    ("py_intro", "py_print", "prerequisite"),
    ("py_intro", "py_comment", "prerequisite"),
    ("py_intro", "py_variable", "prerequisite"),
    ("py_print", "py_input", "prerequisite"),
    ("py_variable", "py_arith", "prerequisite"),
    ("py_variable", "py_compare", "prerequisite"),
    ("py_compare", "py_logic", "prerequisite"),
    ("py_arith", "py_assign_op", "prerequisite"),
    ("py_arith", "py_type_convert", "prerequisite"),
    ("py_print", "py_fstring", "prerequisite"),
    ("py_variable", "py_fstring", "prerequisite"),
    ("py_variable", "py_indent", "prerequisite"),

    # ---------- datatypes 内部及前置 ----------
    ("py_variable", "py_number", "prerequisite"),
    ("py_logic", "py_bool", "prerequisite"),
    ("py_variable", "py_str_basic", "prerequisite"),
    ("py_str_basic", "py_str_method", "prerequisite"),
    ("py_str_basic", "py_str_slice", "prerequisite"),
    ("py_variable", "py_list_basic", "prerequisite"),
    ("py_list_basic", "py_list_method", "prerequisite"),
    ("py_list_basic", "py_list_comp", "prerequisite"),
    ("py_for", "py_list_comp", "prerequisite"),
    ("py_list_basic", "py_tuple", "prerequisite"),
    ("py_list_basic", "py_dict_basic", "prerequisite"),

    # ---------- control_flow ----------
    ("py_compare", "py_if", "prerequisite"),
    ("py_if", "py_while", "prerequisite"),
    ("py_range", "py_for", "prerequisite"),
    ("py_variable", "py_range", "prerequisite"),
    ("py_while", "py_break_continue", "prerequisite"),
    ("py_for", "py_break_continue", "prerequisite"),
    ("py_for", "py_nested_loop", "prerequisite"),
    ("py_while", "py_nested_loop", "prerequisite"),

    # ---------- functions ----------
    ("py_indent", "py_func_def", "prerequisite"),
    ("py_if", "py_func_def", "prerequisite"),
    ("py_func_def", "py_func_param", "prerequisite"),
    ("py_func_def", "py_func_return", "prerequisite"),
    ("py_func_param", "py_func_args_kwargs", "prerequisite"),
    ("py_func_def", "py_lambda", "prerequisite"),
    ("py_func_def", "py_scope", "prerequisite"),
    ("py_func_return", "py_recursion", "prerequisite"),
    ("py_func_args_kwargs", "py_decorator", "prerequisite"),
    ("py_scope", "py_decorator", "prerequisite"),

    # ---------- data_structures ----------
    ("py_dict_basic", "py_dict_method", "prerequisite"),
    ("py_dict_basic", "py_dict_comp", "prerequisite"),
    ("py_for", "py_dict_comp", "prerequisite"),
    ("py_list_basic", "py_set", "prerequisite"),
    ("py_list_basic", "py_nested_data", "prerequisite"),
    ("py_dict_basic", "py_nested_data", "prerequisite"),
    ("py_list_method", "py_sort", "prerequisite"),
    ("py_dict_basic", "py_collections", "prerequisite"),
    ("py_list_basic", "py_collections", "prerequisite"),

    # ---------- file_exception ----------
    ("py_str_basic", "py_file_read", "prerequisite"),
    ("py_str_basic", "py_file_write", "prerequisite"),
    ("py_file_read", "py_with", "prerequisite"),
    ("py_func_def", "py_try_except", "prerequisite"),
    ("py_try_except", "py_raise", "prerequisite"),
    ("py_try_except", "py_exception_type", "prerequisite"),

    # ---------- modules ----------
    ("py_func_def", "py_import", "prerequisite"),
    ("py_import", "py_from_import", "prerequisite"),
    ("py_import", "py_package", "prerequisite"),
    ("py_import", "py_stdlib", "prerequisite"),

    # ---------- oop ----------
    ("py_func_def", "py_class", "prerequisite"),
    ("py_class", "py_attribute", "prerequisite"),
    ("py_class", "py_init", "prerequisite"),
    ("py_init", "py_self", "prerequisite"),
    ("py_class", "py_inherit", "prerequisite"),
    ("py_inherit", "py_override", "prerequisite"),
    ("py_class", "py_magic", "prerequisite"),
    ("py_decorator", "py_property", "prerequisite"),
    ("py_attribute", "py_property", "prerequisite"),

    # ---------- advanced ----------
    ("py_for", "py_iterator", "prerequisite"),
    ("py_iterator", "py_generator", "prerequisite"),
    ("py_func_def", "py_generator", "prerequisite"),
    ("py_with", "py_context_manager", "prerequisite"),
    ("py_magic", "py_context_manager", "prerequisite"),
    ("py_func_param", "py_type_hint", "prerequisite"),
    ("py_intro", "py_venv", "prerequisite"),
]


# ============================================================
# 自检：节点 code 唯一、边引用合法、无自环
# ============================================================
def _self_check() -> None:
    codes = {n["code"] for n in NODES}
    if len(codes) != len(NODES):
        dup = [n["code"] for n in NODES if NODES.count(n) > 1]
        raise ValueError(f"节点 code 重复: {dup}")

    for src, tgt, etype in EDGES:
        if src not in codes:
            raise ValueError(f"边引用未知节点: {src}")
        if tgt not in codes:
            raise ValueError(f"边引用未知节点: {tgt}")
        if src == tgt:
            raise ValueError(f"自环边: {src}")

    # 简单环检测（DFS）：prerequisite 边构成的图必须无环
    adj: dict[str, list[str]] = {c: [] for c in codes}
    for src, tgt, _ in EDGES:
        adj[src].append(tgt)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {c: WHITE for c in codes}

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for nxt in adj[node]:
            if color[nxt] == GRAY:
                return False  # 发现环
            if color[nxt] == WHITE and not dfs(nxt):
                return False
        color[node] = BLACK
        return True

    for c in codes:
        if color[c] == WHITE and not dfs(c):
            raise ValueError(f"检测到环，涉及节点: {c}")

    print(f"✅ 自检通过: {len(NODES)} 节点, {len(EDGES)} 边, 无环")


if __name__ == "__main__":
    _self_check()
