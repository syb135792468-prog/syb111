"""
api/routes/auth.py - 用户认证接口（注册/登录/当前用户）
- 用户名 + 密码注册/登录
- JWT Token 鉴权
- 无手机号/邮箱，保持简洁
"""
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import bcrypt
from jose import jwt, JWTError

from api.schemas import (
    RegisterRequest, LoginRequest, TokenResponse,
    UserInfoResponse, BaseResponse,
)
from models.user import User
from models.database import get_db
from config.settings import settings
from config.constants import HTTP_OK, HTTP_BAD_REQUEST
from utils.logger import get_logger

logger = get_logger(__name__, task_id="auth")
router = APIRouter(prefix="/auth", tags=["认证"])

# 密码哈希工具
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(user_id: int, username: str) -> str:
    """生成 JWT access token"""
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 Authorization header 解析当前用户（FastAPI 依赖注入）"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")

    token = auth_header[7:]
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    return user


@router.post("/register", response_model=BaseResponse, summary="用户注册")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=HTTP_BAD_REQUEST, detail="用户名已存在")

    # 创建用户
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    await db.flush()

    # 自动登录，返回 token
    token = create_access_token(user.id, user.username)
    logger.info(f"新用户注册: {user.username} (id={user.id})")

    return BaseResponse(
        code=HTTP_OK,
        message="注册成功",
        data=TokenResponse(
            access_token=token,
            user_id=user.id,
            username=user.username,
        ).model_dump(),
    )


@router.post("/login", response_model=BaseResponse, summary="用户登录")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=HTTP_BAD_REQUEST, detail="用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=HTTP_BAD_REQUEST, detail="账户已禁用")

    token = create_access_token(user.id, user.username)
    logger.info(f"用户登录: {user.username} (id={user.id})")

    return BaseResponse(
        code=HTTP_OK,
        message="登录成功",
        data=TokenResponse(
            access_token=token,
            user_id=user.id,
            username=user.username,
        ).model_dump(),
    )


@router.get("/me", response_model=BaseResponse, summary="获取当前用户信息")
async def get_me(current_user: User = Depends(get_current_user)):
    return BaseResponse(
        code=HTTP_OK,
        message="success",
        data=UserInfoResponse(
            user_id=current_user.id,
            username=current_user.username,
            created_at=current_user.created_at,
        ).model_dump(),
    )
