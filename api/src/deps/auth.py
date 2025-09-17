from fastapi import Header, HTTPException, status, Request


async def require_api_key(x_api_key: str | None = Header(default=None), request: Request = None) -> None:
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")
    store = request.app.state.api_key_store
    if not store.is_key_active(x_api_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or inactive API key")
    # Attach key to request state for downstream rate limiting
    request.state.api_key = x_api_key

