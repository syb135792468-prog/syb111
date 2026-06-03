"""
config/messages.py - 用户可见消息常量
所有 API 返回的用户提示统一在此管理，避免硬编码散落各处。
"""

# ============================================================
# 1. 通用成功/错误
# ============================================================
MSG_SUCCESS = "success"
MSG_SERVER_ERROR = "服务器错误"
MSG_SERVER_INTERNAL_ERROR = "服务器内部错误"
MSG_SERVICE_UNAVAILABLE = "服务不可用"
MSG_REQUEST_PARAM_ERROR = "请求参数错误"
MSG_REQUEST_TIMEOUT = "请求超时"
MSG_GENERATE_TIMEOUT = "生成超时"
MSG_GENERATE_NO_DATA = "生成失败，无数据"
MSG_DELETE_SUCCESS = "删除成功"
MSG_DELETE_FAILED = "删除失败"
MSG_RESOURCE_NOT_FOUND = "资源不存在"

# ============================================================
# 2. 认证
# ============================================================
MSG_REGISTER_SUCCESS = "注册成功"
MSG_LOGIN_SUCCESS = "登录成功"
MSG_NOT_LOGGED_IN = "未登录"
MSG_TOKEN_INVALID = "Token 无效或已过期"
MSG_USER_NOT_FOUND_OR_DISABLED = "用户不存在或已禁用"
MSG_USERNAME_OR_PASSWORD_WRONG = "用户名或密码错误"
MSG_USERNAME_EXISTS = "用户名已存在"
MSG_ACCOUNT_DISABLED = "账户已禁用"

# ============================================================
# 3. 对话会话
# ============================================================
MSG_CONVERSATION_CREATED = "对话已创建"
MSG_CONVERSATION_DELETED = "对话已删除"
MSG_CONVERSATION_NOT_FOUND = "对话不存在"
MSG_CONVERSATION_UPDATED = "更新成功"
MSG_CHAT_HISTORY_CLEARED = "聊天记录已清空"

# ============================================================
# 4. 练习题
# ============================================================
MSG_QUIZ_NOT_FOUND = "题目不存在"
MSG_NOT_QUIZ_RESOURCE = "该资源不是练习题"
MSG_QUIZ_SUBMIT_SUCCESS = "success"

# ============================================================
# 5. 用户画像
# ============================================================
MSG_PROFILE_GET_FAILED = "获取用户画像失败"
MSG_PROFILE_UPDATE_SUCCESS = "用户画像更新成功"
MSG_PROFILE_UPDATE_FAILED = "更新用户画像失败"
MSG_PROFILE_RESET_SUCCESS = "用户画像已重置为默认值"
MSG_PROFILE_RESET_FAILED = "重置用户画像失败"
MSG_PROFILE_SERVICE_ERROR = "画像服务异常"

# ============================================================
# 6. 错题本
# ============================================================
MSG_ERROR_BOOK_ITEM_NOT_FOUND = "条目不存在"
MSG_ERROR_BOOK_MASTERED = "已标记为掌握"
MSG_ERROR_BOOK_REVIEW_RECORDED = "复习记录已更新"
MSG_ERROR_BOOK_NO_DUE_ITEMS = "暂无待复习题目"

# ============================================================
# 7. 代码执行
# ============================================================
MSG_CODE_EMPTY = "代码不能为空"
MSG_CODE_EXEC_FAILED = "执行失败"

# ============================================================
# 8. 用户ID
# ============================================================
MSG_INVALID_USER_ID = "user_id 非法"

# ============================================================
# 9. A/B 测试
# ============================================================
MSG_EXPERIMENT_NOT_FOUND = "实验不存在"
MSG_EXPERIMENT_ANALYSIS = "实验分析结果"
MSG_EXPERIMENT_STATUS_UPDATED = "实验状态已更新"

# ============================================================
# 10. 学习路径
# ============================================================
MSG_LEARNING_PATH_NOT_FOUND = "学习路径不存在"
MSG_LEARNING_PATH_GENERATED = "学习路径生成成功"
MSG_LEARNING_PATH_NODE_NOT_FOUND = "路径节点不存在"
MSG_LEARNING_PATH_NODE_COMPLETED = "节点已标记完成"
MSG_LEARNING_PATH_RESOURCE_GENERATING = "资源生成中"
MSG_LEARNING_PATH_RESOURCE_CACHED = "资源已从缓存加载"
MSG_LEARNING_PATH_QUIZ_RECORDED = "测验结果已记录"
