"""Authentication module: password hashing, JWT tokens, and auth endpoints.

Provides registration and login endpoints, helpers for issuing/decoding
JWT access tokens, and a FastAPI dependency for resolving the current user
from a Bearer token.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt  # pylint: disable=import-error
from passlib.context import CryptContext  # pylint: disable=import-error
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import UserCreate, UserResponse

# --- Config ---

SECRET_KEY = "CHANGE_ME_IN_PRODUCTION_USE_ENV_VAR"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

router = APIRouter(tags=["auth"])


# --- Token schema ---

class Token(BaseModel):
    """JWT access-token response returned by the login endpoint."""

    access_token: str
    token_type: str = "bearer"


# --- Password helpers ---

def hash_password(password: str) -> str:
    """Return a bcrypt hash for the given plaintext password."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Check that a plaintext password matches the stored bcrypt hash."""
    return pwd_context.verify(plain, hashed)


# --- JWT helpers ---

def create_access_token(
    subject: str | int, expires_delta: timedelta | None = None
) -> str:
    """Encode a JWT access token carrying the given subject (usually user id)."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT access token, returning its payload."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# --- User lookup helpers ---

def get_user_by_username(db: Session, username: str) -> User | None:
    """Fetch a user by username, or return None if no match."""
    return db.scalars(select(User).where(User.username == username)).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    """Fetch a user by email, or return None if no match."""
    return db.scalars(select(User).where(User.email == email)).first()


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Return the user if credentials are valid, otherwise None."""
    user = get_user_by_username(db, username)
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


# --- Current user dependency ---

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: resolve the authenticated user from a Bearer token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = db.get(User, int(user_id))
    if user is None:
        raise credentials_exception
    return user


# --- Endpoints ---

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)) -> User:
    """Register a new user with a unique username and email."""
    if get_user_by_username(db, data.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    if get_user_by_email(db, data.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """Authenticate user credentials and return a JWT access token."""
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=user.id)
    return Token(access_token=token)
