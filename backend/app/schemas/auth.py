from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

ADDRESS_RE_LEN = 42


class NonceRequest(BaseModel):
    address: str = Field(..., min_length=ADDRESS_RE_LEN, max_length=ADDRESS_RE_LEN)

    @field_validator("address")
    @classmethod
    def _lower_hex(cls, v: str) -> str:
        if not v.startswith("0x"):
            raise ValueError("address must start with 0x")
        try:
            int(v, 16)
        except ValueError as e:
            raise ValueError("address must be hex") from e
        return v.lower()


class NonceResponse(BaseModel):
    address: str
    nonce: str
    message: str
    expires_at: str


class VerifyRequest(BaseModel):
    address: str = Field(..., min_length=ADDRESS_RE_LEN, max_length=ADDRESS_RE_LEN)
    signature: str = Field(..., min_length=10)
    message: str = Field(..., min_length=10)

    @field_validator("address")
    @classmethod
    def _lower_hex(cls, v: str) -> str:
        return v.lower()


class SessionInfo(BaseModel):
    address: str
    expires_at: str
