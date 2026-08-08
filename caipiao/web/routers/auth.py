"""认证路由：注册 / 登录（返回 JWT）。"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from starlette.requests import Request

from ..db import get_db
from ..models import User
from ..ratelimit import limiter
from ..schemas import Token, UserCreate, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# 鉴权网关的限流默认值；测试环境可通过 CAIPIAO_WEB_AUTH_RATE_LIMIT 调高，
# 避免大量注册/登录请求触发 429。生产默认值保持 30/minute。
_AUTH_RATE_LIMIT = os.getenv("CAIPIAO_WEB_AUTH_RATE_LIMIT", "30/minute")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(_AUTH_RATE_LIMIT)
def register(request: Request, payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.query(User).filter_by(username=payload.username).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在")
    # P5.E：首个注册用户自动成为管理员（便于初始化）；其余为普通用户
    role = "admin" if db.query(User).first() is None else "user"
    user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
@limiter.limit(_AUTH_RATE_LIMIT)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    user = db.query(User).filter_by(username=form.username).first()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    return Token(access_token=create_access_token(user.id))
