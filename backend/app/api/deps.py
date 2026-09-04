import secrets
from typing import Optional, Union
from fastapi import Depends, HTTPException, Header, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.user import TokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
        
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    query = select(User).where(User.email == token_data.email)
    result = await db.execute(query)
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuário inativo")
    return user

async def get_current_active_superuser(current_user: User = Depends(get_current_user)):
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Privilégios insuficientes")
    return current_user

async def require_admin_auth(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db)
) -> Union[User, dict]:
    """
    Dependência unificada de autenticação de administrador:
    1. Valida Master API Key via header X-API-Key ou Authorization Bearer.
    2. Valida Token JWT Bearer verificando se o usuário existe, está ativo e possui is_superuser=True.
    """
    master_key = getattr(settings, "ADMIN_API_KEY", None)

    # 1. Validação via X-API-Key
    if x_api_key and master_key and secrets.compare_digest(x_api_key, master_key):
        return {"auth_type": "api_key", "role": "admin"}

    # 2. Validação via Authorization header
    if authorization:
        parts = authorization.split(" ", 1)
        scheme = parts[0].lower()
        token = parts[1].strip() if len(parts) > 1 else ""

        if scheme in ("bearer", "token") and token:
            # Verifica se o próprio token é a Master API Key
            if master_key and secrets.compare_digest(token, master_key):
                return {"auth_type": "api_key", "role": "admin"}

            # Decodifica e valida o JWT
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                email: str = payload.get("sub")
                if not email:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token inválido: sujeito não encontrado",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
            except JWTError:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token JWT inválido ou expirado",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            query = select(User).where(User.email == email)
            result = await db.execute(query)
            user = result.scalars().first()

            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuário administrador não encontrado",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if not user.is_active:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário inativo")
            if not user.is_superuser:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Privilégios insuficientes: requer perfil de administrador",
                )
            return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Autenticação obrigatória: forneça um Token de Administrador ou Chave de API válida.",
        headers={"WWW-Authenticate": "Bearer"},
    )

