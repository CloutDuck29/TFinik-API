from pydantic import BaseModel, EmailStr

class Creds(BaseModel):
    email: EmailStr
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
