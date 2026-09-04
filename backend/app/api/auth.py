from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.user import User
from app.schemas.user import Token, UserCreate, UserResponse, ChangePasswordRequest
from app.utils.security import verify_password, get_password_hash, create_access_token
from app.config import settings
from app.api.deps import require_admin_auth

router = APIRouter()

@router.post("/login", response_model=Token)
async def login_access_token(
    db: AsyncSession = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    query = select(User).where(User.email == form_data.username)
    result = await db.execute(query)
    user = result.scalars().first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Usuário inativo")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register", response_model=UserResponse)
async def register_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new user. Currently open for setup, should be restricted in production.
    """
    query = select(User).where(User.email == user_in.email)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="Já existe um usuário com este email.",
        )
        
    user = User(
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        is_superuser=user_in.is_superuser
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user

@router.put("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    auth=Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db)
):
    """
    Alteração segura de senha de administrador/usuário.
    Exige autenticação de administrador (Token JWT ou Master API Key).
    """
    if isinstance(auth, User):
        user = auth
        if not data.current_password or not verify_password(data.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Senha atual incorreta."
            )
        user.hashed_password = get_password_hash(data.new_password)
        await db.commit()
        return {"message": "Senha alterada com sucesso!"}
        
    # Se autenticado via Master API Key
    target_email = getattr(data, "email", None)
    if not target_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ao utilizar API Key mestre, informe o campo 'email' do usuário."
        )
    query = select(User).where(User.email == target_email)
    result = await db.execute(query)
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Usuário '{target_email}' não encontrado.")
        
    user.hashed_password = get_password_hash(data.new_password)
    await db.commit()
    return {"message": f"Senha do usuário '{target_email}' alterada com sucesso!"}
