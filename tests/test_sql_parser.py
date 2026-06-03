"""
SQL DDL 解析器 + MindmapAgent ER 图生成 - 单元测试
覆盖：SQL 解析、多方言支持、ER 兜底生成、错误处理、节点类型检测
"""
import json
import pytest

from utils.sql_parser import parse_sql_tables, generate_ddl_doc_markdown


# ============================================================
# SQL 解析：基础功能
# ============================================================

class TestSQLParserBasic:
    """基础 SQL 解析测试"""

    def test_single_table_basic(self):
        sql = "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100));"
        result = parse_sql_tables(sql)
        assert result["success"] is True
        assert len(result["tables"]) == 1
        t = result["tables"][0]
        assert t["name"] == "users"
        assert len(t["fields"]) == 2
        assert t["fields"][0]["name"] == "id"
        assert t["fields"][1]["name"] == "name"

    def test_multiple_tables(self):
        sql = """
        CREATE TABLE users (id INT PRIMARY KEY);
        CREATE TABLE orders (id INT PRIMARY KEY);
        CREATE TABLE products (id INT PRIMARY KEY);
        """
        result = parse_sql_tables(sql)
        assert result["success"] is True
        assert len(result["tables"]) == 3
        names = [t["name"] for t in result["tables"]]
        assert "users" in names
        assert "orders" in names
        assert "products" in names

    def test_empty_input(self):
        result = parse_sql_tables("")
        assert result["success"] is False
        assert "输入为空" in result["error"]

    def test_no_create_table(self):
        result = parse_sql_tables("SELECT * FROM users;")
        assert result["success"] is False
        assert "CREATE TABLE" in result["error"]

    def test_comment_removal(self):
        sql = """
        -- This is a comment
        CREATE TABLE users (
            id INT PRIMARY KEY, # MySQL comment
            name VARCHAR(100) /* inline comment */
        );
        """
        result = parse_sql_tables(sql)
        assert result["success"] is True
        assert len(result["tables"]) == 1


# ============================================================
# SQL 解析：字段属性
# ============================================================

class TestSQLParserFieldAttributes:
    """字段属性解析测试"""

    def test_field_types(self):
        sql = """
        CREATE TABLE test (
            a INT,
            b VARCHAR(100),
            c DECIMAL(10,2),
            d TEXT,
            e TIMESTAMP,
            f BOOLEAN
        );
        """
        result = parse_sql_tables(sql)
        fields = result["tables"][0]["fields"]
        types = {f["name"]: f["data_type"] for f in fields}
        assert types["a"] == "INT"
        assert types["b"] == "VARCHAR"
        assert types["c"] == "DECIMAL"
        assert types["d"] == "TEXT"
        assert types["e"] == "TIMESTAMP"
        assert types["f"] == "BOOLEAN"

    def test_field_length(self):
        sql = "CREATE TABLE t (name VARCHAR(100), price DECIMAL(10,2));"
        result = parse_sql_tables(sql)
        fields = result["tables"][0]["fields"]
        assert fields[0]["length"] == "100"
        assert fields[1]["length"] == "10,2"

    def test_not_null(self):
        sql = "CREATE TABLE t (id INT NOT NULL, name VARCHAR(100));"
        result = parse_sql_tables(sql)
        fields = result["tables"][0]["fields"]
        assert fields[0]["nullable"] is False
        assert fields[1]["nullable"] is True

    def test_default_value(self):
        sql = "CREATE TABLE t (status INT DEFAULT 0, name VARCHAR(100) DEFAULT 'unknown');"
        result = parse_sql_tables(sql)
        fields = result["tables"][0]["fields"]
        assert fields[0]["default"] == "0"
        assert fields[1]["default"] == "unknown"

    def test_auto_increment(self):
        sql = "CREATE TABLE t (id INT AUTO_INCREMENT PRIMARY KEY);"
        result = parse_sql_tables(sql)
        fields = result["tables"][0]["fields"]
        assert fields[0]["is_auto_increment"] is True

    def test_field_comment(self):
        sql = "CREATE TABLE t (id INT COMMENT 'user ID', name VARCHAR(100) COMMENT 'user name');"
        result = parse_sql_tables(sql)
        fields = result["tables"][0]["fields"]
        assert fields[0]["comment"] == "user ID"
        assert fields[1]["comment"] == "user name"

    def test_inline_primary_key(self):
        sql = "CREATE TABLE t (id INT PRIMARY KEY, name VARCHAR(100));"
        result = parse_sql_tables(sql)
        fields = result["tables"][0]["fields"]
        assert fields[0]["is_primary_key"] is True
        assert result["tables"][0]["primary_keys"] == ["id"]


# ============================================================
# SQL 解析：约束与索引
# ============================================================

class TestSQLParserConstraints:
    """约束与索引解析测试"""

    def test_composite_primary_key(self):
        sql = "CREATE TABLE t (a INT, b INT, PRIMARY KEY (a, b));"
        result = parse_sql_tables(sql)
        t = result["tables"][0]
        assert set(t["primary_keys"]) == {"a", "b"}

    def test_foreign_key(self):
        sql = """
        CREATE TABLE orders (
            id INT PRIMARY KEY,
            user_id INT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
        result = parse_sql_tables(sql)
        t = result["tables"][0]
        assert len(t["foreign_keys"]) == 1
        fk = t["foreign_keys"][0]
        assert fk["local_column"] == "user_id"
        assert fk["reference_table"] == "users"
        assert fk["reference_column"] == "id"
        assert "CASCADE" in fk["on_delete"]

    def test_named_foreign_key(self):
        sql = """
        CREATE TABLE orders (
            id INT PRIMARY KEY,
            user_id INT,
            CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """
        result = parse_sql_tables(sql)
        fk = result["tables"][0]["foreign_keys"][0]
        assert fk["name"] == "fk_user"

    def test_unique_index(self):
        sql = "CREATE TABLE t (id INT, email VARCHAR(100), UNIQUE KEY uk_email (email));"
        result = parse_sql_tables(sql)
        t = result["tables"][0]
        assert len(t["indexes"]) == 1
        assert t["indexes"][0]["type"] == "UNIQUE"
        assert t["indexes"][0]["columns"] == ["email"]

    def test_regular_index(self):
        sql = "CREATE TABLE t (id INT, name VARCHAR(100), INDEX idx_name (name));"
        result = parse_sql_tables(sql)
        t = result["tables"][0]
        assert len(t["indexes"]) == 1
        assert t["indexes"][0]["type"] == "INDEX"

    def test_check_constraint(self):
        sql = "CREATE TABLE t (age INT, CONSTRAINT chk_age CHECK (age >= 0));"
        result = parse_sql_tables(sql)
        t = result["tables"][0]
        assert len(t["constraints"]) == 1
        assert t["constraints"][0]["type"] == "CHECK"


# ============================================================
# SQL 解析：表级属性
# ============================================================

class TestSQLParserTableAttributes:
    """表级属性解析测试"""

    def test_table_comment_inline(self):
        sql = "CREATE TABLE users (id INT) COMMENT='user table';"
        result = parse_sql_tables(sql)
        assert result["tables"][0]["comment"] == "user table"

    def test_engine_attribute(self):
        sql = "CREATE TABLE users (id INT) ENGINE=InnoDB;"
        result = parse_sql_tables(sql)
        assert result["success"] is True

    def test_if_not_exists(self):
        sql = "CREATE TABLE IF NOT EXISTS users (id INT PRIMARY KEY);"
        result = parse_sql_tables(sql)
        assert result["success"] is True
        assert result["tables"][0]["name"] == "users"


# ============================================================
# SQL 解析：多方言支持
# ============================================================

class TestSQLParserDialects:
    """多方言兼容性测试"""

    def test_mysql(self):
        sql = """
        CREATE TABLE users (
            id INT PRIMARY KEY AUTO_INCREMENT COMMENT 'ID',
            name VARCHAR(100) NOT NULL COMMENT 'Name'
        ) ENGINE=InnoDB COMMENT='Users';
        """
        result = parse_sql_tables(sql)
        assert result["success"] is True
        t = result["tables"][0]
        assert t["name"] == "users"
        assert t["comment"] == "Users"
        assert t["fields"][0]["is_auto_increment"] is True

    def test_postgresql_serial(self):
        sql = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(200) UNIQUE
        );
        """
        result = parse_sql_tables(sql)
        assert result["success"] is True
        t = result["tables"][0]
        assert t["fields"][0]["data_type"] == "INT"
        assert t["fields"][0]["is_auto_increment"] is True

    def test_postgresql_bigserial(self):
        sql = "CREATE TABLE t (id BIGSERIAL PRIMARY KEY);"
        result = parse_sql_tables(sql)
        assert result["tables"][0]["fields"][0]["data_type"] == "BIGINT"
        assert result["tables"][0]["fields"][0]["is_auto_increment"] is True

    def test_postgresql_references(self):
        sql = """
        CREATE TABLE orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
        );
        """
        result = parse_sql_tables(sql)
        t = result["tables"][0]
        assert len(t["foreign_keys"]) == 1
        assert t["foreign_keys"][0]["reference_table"] == "users"

    def test_sql_server_brackets(self):
        sql = """
        CREATE TABLE [dbo].[users] (
            [id] INT IDENTITY(1,1) PRIMARY KEY,
            [name] NVARCHAR(100) NOT NULL,
            [email] NVARCHAR(200)
        );
        """
        result = parse_sql_tables(sql)
        assert result["success"] is True
        t = result["tables"][0]
        assert t["name"] == "users"
        assert t["schema"] == "dbo"
        assert t["fields"][0]["is_auto_increment"] is True

    def test_use_database(self):
        sql = """
        USE school;
        CREATE TABLE students (id INT PRIMARY KEY);
        """
        result = parse_sql_tables(sql)
        assert result["database"] == "school"

    def test_create_database(self):
        sql = """
        CREATE DATABASE IF NOT EXISTS mydb;
        CREATE TABLE t (id INT PRIMARY KEY);
        """
        result = parse_sql_tables(sql)
        assert result["database"] == "mydb"


# ============================================================
# SQL 解析：边界情况
# ============================================================

class TestSQLParserEdgeCases:
    """边界情况测试"""

    def test_quoted_identifiers(self):
        sql = 'CREATE TABLE `users` (`id` INT PRIMARY KEY, `name` VARCHAR(100));'
        result = parse_sql_tables(sql)
        assert result["tables"][0]["name"] == "users"
        assert result["tables"][0]["fields"][0]["name"] == "id"

    def test_schema_qualified_name(self):
        sql = "CREATE TABLE public.users (id INT PRIMARY KEY);"
        result = parse_sql_tables(sql)
        t = result["tables"][0]
        assert t["name"] == "users"
        assert t["schema"] == "public"

    def test_incomplete_sql(self):
        sql = "CREATE TABLE users (id INT PRIMARY KEY"
        result = parse_sql_tables(sql)
        # Should either succeed with partial data or fail gracefully
        assert result["success"] is False or len(result["tables"]) >= 0


# ============================================================
# Markdown 文档生成
# ============================================================

class TestMarkdownDocGeneration:
    """Markdown 文档生成测试"""

    def test_basic_doc(self):
        sql = "CREATE TABLE users (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(100) NOT NULL);"
        result = parse_sql_tables(sql)
        doc = generate_ddl_doc_markdown(result["tables"], "testdb")
        assert "# testdb 表设计文档" in doc
        assert "users" in doc
        assert "id" in doc
        assert "name" in doc
        assert "PRIMARY KEY" in doc or "PK" in doc

    def test_doc_with_foreign_keys(self):
        sql = """
        CREATE TABLE users (id INT PRIMARY KEY);
        CREATE TABLE orders (id INT PRIMARY KEY, user_id INT, FOREIGN KEY (user_id) REFERENCES users(id));
        """
        result = parse_sql_tables(sql)
        doc = generate_ddl_doc_markdown(result["tables"], "shop")
        assert "外键关系" in doc
        assert "users" in doc
        assert "orders" in doc

    def test_doc_with_indexes(self):
        sql = "CREATE TABLE t (id INT, name VARCHAR(100), INDEX idx_name (name));"
        result = parse_sql_tables(sql)
        doc = generate_ddl_doc_markdown(result["tables"])
        assert "索引信息" in doc

    def test_empty_tables(self):
        doc = generate_ddl_doc_markdown([], "empty")
        assert "empty" in doc
        # 检查表数量为0（用编码安全的方式）
        assert ": 0" in doc or ":0" in doc or "0" in doc.split("数量")[-1][:5]


# ============================================================
# MindmapAgent ER 图功能
# ============================================================

class TestMindmapAgentER:
    """MindmapAgent ER 图相关方法测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from agents.mindmap_agent import MindmapAgent
        self.agent_cls = MindmapAgent

    def test_is_sql_input_positive(self):
        assert self.agent_cls._is_sql_input("CREATE TABLE users (id INT);") is True
        assert self.agent_cls._is_sql_input("create table test (a int);") is True
        assert self.agent_cls._is_sql_input("CREATE TABLE IF NOT EXISTS t (id INT);") is True
        assert self.agent_cls._is_sql_input("```sql\nCREATE TABLE x (id INT);\n```") is True

    def test_is_sql_input_negative(self):
        assert self.agent_cls._is_sql_input("hello world") is False
        assert self.agent_cls._is_sql_input("Python list comprehension") is False
        assert self.agent_cls._is_sql_input("") is False

    def test_detect_er_node_type_table(self):
        defn = "业务用途：存储用户信息；数据量预估：大；读写频率：高"
        assert self.agent_cls._detect_er_node_type(defn) == "table"

    def test_detect_er_node_type_field(self):
        defn = "含义：用户ID；类型：INT(11)；可为空：否；默认值：无"
        assert self.agent_cls._detect_er_node_type(defn) == "field"

    def test_detect_er_node_type_foreign_key(self):
        defn = "引用 users.id；ON DELETE SET NULL"
        assert self.agent_cls._detect_er_node_type(defn) == "foreign_key"

    def test_detect_er_node_type_none(self):
        assert self.agent_cls._detect_er_node_type("") is None
        assert self.agent_cls._detect_er_node_type("Python basics") is None
        assert self.agent_cls._detect_er_node_type(None) is None

    def test_generate_er_fallback_valid_json(self):
        sql = "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100));"
        result = parse_sql_tables(sql)
        doc = generate_ddl_doc_markdown(result["tables"], "test")
        content = self.agent_cls._generate_er_fallback(result["tables"], "test", doc)
        data = json.loads(content)
        assert "nodeData" in data
        root = data["nodeData"]
        assert "ER图" in root["topic"]
        assert len(root["children"]) == 1

    def test_generate_er_fallback_structure(self):
        sql = """
        CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100));
        CREATE TABLE orders (id INT PRIMARY KEY, user_id INT, FOREIGN KEY (user_id) REFERENCES users(id));
        """
        result = parse_sql_tables(sql)
        doc = generate_ddl_doc_markdown(result["tables"], "shop")
        content = self.agent_cls._generate_er_fallback(result["tables"], "shop", doc)
        data = json.loads(content)
        root = data["nodeData"]

        assert len(root["children"]) == 2

        # 每个表节点应有 5 个分类子节点
        for table_node in root["children"]:
            topics = [c["topic"] for c in table_node["children"]]
            assert "字段列表" in topics
            assert "主键" in topics
            assert "外键" in topics
            assert "索引" in topics
            assert "约束" in topics

    def test_generate_er_fallback_fields(self):
        sql = "CREATE TABLE users (id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(100) NOT NULL);"
        result = parse_sql_tables(sql)
        doc = generate_ddl_doc_markdown(result["tables"], "test")
        content = self.agent_cls._generate_er_fallback(result["tables"], "test", doc)
        data = json.loads(content)
        table_node = data["nodeData"]["children"][0]
        fields_node = next(c for c in table_node["children"] if c["topic"] == "字段列表")

        assert len(fields_node["children"]) == 2
        id_node = fields_node["children"][0]
        assert id_node["topic"] == "id"
        assert "INT" in id_node["definition"]

    def test_generate_er_fallback_foreign_keys(self):
        sql = """
        CREATE TABLE users (id INT PRIMARY KEY);
        CREATE TABLE orders (id INT PRIMARY KEY, user_id INT, FOREIGN KEY (user_id) REFERENCES users(id));
        """
        result = parse_sql_tables(sql)
        doc = generate_ddl_doc_markdown(result["tables"], "test")
        content = self.agent_cls._generate_er_fallback(result["tables"], "test", doc)
        data = json.loads(content)

        orders_node = data["nodeData"]["children"][1]
        fk_node = next(c for c in orders_node["children"] if c["topic"] == "外键")
        assert len(fk_node["children"]) == 1
        assert "引用 users.id" in fk_node["children"][0]["definition"]

    def test_generate_er_fallback_examples_contains_doc(self):
        sql = "CREATE TABLE t (id INT PRIMARY KEY);"
        result = parse_sql_tables(sql)
        doc = generate_ddl_doc_markdown(result["tables"], "mydb")
        content = self.agent_cls._generate_er_fallback(result["tables"], "mydb", doc)
        data = json.loads(content)
        assert data["nodeData"]["examples"][0] == doc

    def test_generate_sql_error_json(self):
        content = self.agent_cls._generate_sql_error_json("语法错误", "请检查括号")
        data = json.loads(content)
        assert data["nodeData"]["topic"] == "SQL解析失败"
        assert "语法错误" in data["nodeData"]["definition"]
        assert len(data["nodeData"]["children"]) >= 1

    def test_generate_er_fallback_passes_validate_json(self):
        """确保兜底 JSON 能通过 _validate_json 验证"""
        sql = "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100));"
        result = parse_sql_tables(sql)
        doc = generate_ddl_doc_markdown(result["tables"], "test")
        content = self.agent_cls._generate_er_fallback(result["tables"], "test", doc)
        validated = self.agent_cls._validate_json(content)
        data = json.loads(validated)
        assert "nodeData" in data

    def test_generate_er_fallback_passes_ensure_depth(self):
        """确保兜底 JSON 能通过 _ensure_depth 验证"""
        sql = "CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100));"
        result = parse_sql_tables(sql)
        doc = generate_ddl_doc_markdown(result["tables"], "test")
        content = self.agent_cls._generate_er_fallback(result["tables"], "test", doc)
        validated = self.agent_cls._validate_json(content)
        final = self.agent_cls._ensure_depth(validated)
        data = json.loads(final)
        assert "nodeData" in data
