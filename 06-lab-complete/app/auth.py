"""
Authentication module — API key based (shared secret via X-API-Key header).

Usage in FastAPI route:
    from app.auth import verify_api_key

    @app.post("/ask")
    def ask(_key: str = Depends(verify_api_key)):
        ...
"""
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    FastAPI dependency — raises 401 if header X-API-Key is missing or wrong.
    Returns the caller's api_key (used downstream as a rate-limit / cost-guard bucket id).
    """
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key
