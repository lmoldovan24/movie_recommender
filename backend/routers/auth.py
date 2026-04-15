import hashlib
from datetime import datetime, timezone, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.limiter import limiter
from backend.models import User, RefreshToken, LoginAttempt
from backend.schemas import UserCreate, UserLogin, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# --- Constante lockout ---
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_MINUTES = 15

# --- Cookie config ---
_COOKIE_OPTS = dict(
    httponly=True,
    samesite="strict",
)


def _is_prod() -> bool:
    return settings.ENVIRONMENT == "production"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Setează ambele cookie-uri httpOnly în răspuns."""
    secure = _is_prod()
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        secure=secure,
        **_COOKIE_OPTS,
    )
    # Refresh token limitat la /auth — browserul nu îl trimite pe alte endpoint-uri,
    # limitând suprafața de atac în cazul unui request forjat spre alt path.
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/auth",
        secure=secure,
        **_COOKIE_OPTS,
    )


def _clear_auth_cookies(response: Response) -> None:
    """Șterge cookie-urile de autentificare."""
    response.delete_cookie(key="access_token", path="/", samesite="strict")
    response.delete_cookie(key="refresh_token", path="/auth", samesite="strict")


# --- Helpers parole ---

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# --- Helpers JWT ---

def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.REFRESH_SECRET_KEY, algorithm=settings.ALGORITHM)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Helpers lockout ---

def is_account_locked(username: str, db: Session) -> bool:
    window = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_WINDOW_MINUTES)
    recent_failures = (
        db.query(LoginAttempt)
        .filter(
            LoginAttempt.username == username,
            LoginAttempt.attempted_at >= window,
            LoginAttempt.success == False,
        )
        .count()
    )
    return recent_failures >= MAX_FAILED_ATTEMPTS


def record_attempt(username: str, success: bool, db: Session):
    attempt = LoginAttempt(username=username, success=success)
    db.add(attempt)
    db.commit()


# --- Endpoints ---

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
def register(request: Request, data: UserCreate, db: Session = Depends(get_db)):
    # Hash-ul se calculează ÎNAINTE de a verifica existența userului.
    # Altfel, timing-ul răspunsului ar revela dacă username/email-ul există deja:
    # user existent → ~1ms (fără hash), user nou → ~100ms (Argon2).
    hashed = hash_password(data.password)

    # Mesaj generic pentru ambele cazuri — previne enumerarea userilor și emailurilor
    existing = db.query(User).filter(
        (User.username == data.username) | (User.email == data.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username sau email deja înregistrat")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hashed,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, data: UserLogin, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()

    # Lockout check — înainte de orice altceva
    if is_account_locked(data.username, db):
        raise HTTPException(
            status_code=429,
            detail=f"Cont blocat temporar după {MAX_FAILED_ATTEMPTS} încercări eșuate. "
                   f"Încearcă din nou în {LOCKOUT_WINDOW_MINUTES} minute.",
        )

    # User inexistent sau parolă greșită.
    # Înregistrăm eșecul ÎNAINTE de a re-verifica lockout: dacă această încercare
    # atinge pragul, informăm imediat userul că e blocat (în loc să afle la next request).
    # Elimină și race condition-ul: concurrent requests care trec de lockout check inițial
    # vor vedea lockout-ul declanșat după ce înregistrează eșecul propriu.
    if not user:
        record_attempt(data.username, success=False, db=db)
        if is_account_locked(data.username, db):
            raise HTTPException(
                status_code=429,
                detail=f"Cont blocat temporar după {MAX_FAILED_ATTEMPTS} încercări eșuate. "
                       f"Încearcă din nou în {LOCKOUT_WINDOW_MINUTES} minute.",
            )
        raise HTTPException(status_code=401, detail="Username sau parolă incorectă")

    ok = verify_password(data.password, user.hashed_password)
    if not ok:
        record_attempt(data.username, success=False, db=db)
        if is_account_locked(data.username, db):
            raise HTTPException(
                status_code=429,
                detail=f"Cont blocat temporar după {MAX_FAILED_ATTEMPTS} încercări eșuate. "
                       f"Încearcă din nou în {LOCKOUT_WINDOW_MINUTES} minute.",
            )
        raise HTTPException(status_code=401, detail="Username sau parolă incorectă")

    # Cont dezactivat
    if not user.is_active:
        record_attempt(data.username, success=False, db=db)
        raise HTTPException(status_code=403, detail="Contul este dezactivat")

    record_attempt(data.username, success=True, db=db)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    db_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(db_token)
    db.commit()

    _set_auth_cookies(response, access_token, refresh_token)
    return TokenResponse(user=UserOut.model_validate(user))


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token lipsă")

    try:
        payload = jwt.decode(refresh_token, settings.REFRESH_SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token invalid")
        user_id = int(payload["sub"])
    except jwt.ExpiredSignatureError:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh token expirat")
    except jwt.PyJWTError:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh token invalid")

    token_hash = hash_token(refresh_token)
    db_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.is_revoked == False,
    ).first()

    if not db_token:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="Refresh token revocat sau inexistent")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        _clear_auth_cookies(response)
        raise HTTPException(status_code=401, detail="User invalid")

    # Rotire token — revocăm vechiul, emitem unul nou
    db_token.is_revoked = True

    new_access = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)

    new_db_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_db_token)
    db.commit()

    _set_auth_cookies(response, new_access, new_refresh)
    return TokenResponse(user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")

    if refresh_token:
        token_hash = hash_token(refresh_token)
        db_token = db.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash
        ).first()
        if db_token:
            db_token.is_revoked = True
            db.commit()

    _clear_auth_cookies(response)
    return {"detail": "Deconectat cu succes"}
