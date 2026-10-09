"""
Schemas (formatos de dados) usados pelos endpoints de autenticação.

Um "schema" aqui define exatamente o que a API espera receber (request)
e o que ela promete devolver (response) — o FastAPI usa isso para validar
automaticamente os dados e gerar a documentação interativa (/docs).
"""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
