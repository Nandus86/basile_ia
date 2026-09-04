"""
Utilitário para gerenciar e redefinir senhas de usuários/administradores do Basile IA.

Uso:
  Listar usuários:
    python reset_password.py --list

  Redefinir senha de um usuário existente:
    python reset_password.py <email> <nova_senha>

  Criar ou atualizar usuário com senha:
    python reset_password.py <email> <nova_senha> --create-if-missing
"""

import sys
import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.user import User
from app.utils.security import get_password_hash


async def list_users():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        if not users:
            print("\n⚠️  Nenhum usuário cadastrado na tabela 'users'.\n")
            return
        print("\n📋 Usuários cadastrados no sistema:")
        print("-" * 70)
        for u in users:
            admin_flag = " [SUPERUSER/ADMIN]" if u.is_superuser else ""
            status = "Ativo" if u.is_active else "Inativo"
            print(f" • Email: {u.email:<30} | Nome: {u.full_name or 'N/A':<15} | {status}{admin_flag}")
        print("-" * 70 + "\n")


async def set_password(email: str, new_password: str, create_if_missing: bool = False):
    email = email.strip().lower()
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()

        if not user:
            if create_if_missing:
                print(f"ℹ️  Usuário '{email}' não encontrado. Criando novo usuário admin...")
                new_user = User(
                    email=email,
                    hashed_password=get_password_hash(new_password),
                    full_name="Administrador",
                    is_active=True,
                    is_superuser=True
                )
                session.add(new_user)
                await session.commit()
                print(f"✅ Usuário '{email}' criado com sucesso como SUPERUSER!")
                return
            else:
                print(f"\n❌ Usuário com o e-mail '{email}' não foi encontrado no banco de dados.")
                print("Dica: Use '--list' para ver os usuários existentes ou adicione '--create-if-missing'.\n")
                return

        user.hashed_password = get_password_hash(new_password)
        await session.commit()
        print(f"\n✅ Senha do usuário '{email}' alterada com sucesso!\n")


async def main():
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print(__doc__)
        return

    if "--list" in args:
        await list_users()
        return

    create_if_missing = "--create-if-missing" in args
    clean_args = [a for a in args if not a.startswith("--")]

    if len(clean_args) < 2:
        print("❌ Erro: Parâmetros insuficientes.")
        print("Uso: python reset_password.py <email> <nova_senha> [--create-if-missing]")
        return

    email = clean_args[0]
    new_password = clean_args[1]

    await set_password(email, new_password, create_if_missing=create_if_missing)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        asyncio.run(engine.dispose())
