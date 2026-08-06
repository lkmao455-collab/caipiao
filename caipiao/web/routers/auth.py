"""认证路由：注册 / 登录（返回 JWT）。"""

from __future__ import annotations

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


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def register(request: Request, payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.query(User).filter_by(username=payload.username).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在")
    user = User(username=payload.username, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
@limiter.limit("30/minute")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    user = db.query(User).filter_by(username=form.username).first()
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    return Token(access_token=create_access_token(user.id))
