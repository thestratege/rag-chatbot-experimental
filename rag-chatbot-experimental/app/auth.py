from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Depends, Header, HTTPException, Request, status

from app.config import Settings, settings


ANONYMOUS_DEMO_USER_ID = "anonymous_demo_user"
DEMO_USER_ID = "demo-user"
DEMO_ADMIN_ID = "demo-admin"
ENTRA_AUTH_PROVIDERS = {"entra", "microsoft_entra_id"}
PUBLIC_PATHS = {"/health"}
DEVELOPMENT_PUBLIC_PATHS = {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}
DEMO_PROFILE_GROUPS = {
    "anonymous_demo_user": ("public",),
    "demo-user": ("public",),
    "demo-ti": ("public", "TI"),
    "demo-rh": ("public", "RH"),
    "demo-manager": ("public", "gestionnaires"),
    "demo-admin": ("public", "TI", "RH", "gestionnaires", "admin"),
}


@dataclass(frozen=True)
class UserContext:
    user_id: str
    auth_provider: str
    is_authenticated: bool
    auth_enabled: bool
    groups: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    token_present: bool = False


def verify_auth(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> UserContext:
    return resolve_current_user(settings, authorization)


def require_auth(user_context: Annotated[UserContext, Depends(verify_auth)]) -> UserContext:
    if settings.auth_enabled and not user_context.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_context


def require_role(required_role: str) -> Callable[[UserContext], UserContext]:
    def dependency(user_context: Annotated[UserContext, Depends(require_auth)]) -> UserContext:
        if required_role not in user_context.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès refusé : rôle requis '{required_role}'.",
            )
        return user_context

    return dependency


def get_current_user_optional(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> UserContext:
    return verify_auth(authorization)


def is_public_request(request: Request, config: Settings) -> bool:
    if request.method == "OPTIONS":
        return True
    if request.url.path in PUBLIC_PATHS:
        return True
    return config.environment in {"development", "demo", "test"} and request.url.path in DEVELOPMENT_PUBLIC_PATHS


def resolve_current_user(config: Settings, authorization: str | None) -> UserContext:
    if not config.auth_enabled:
        return UserContext(
            user_id=ANONYMOUS_DEMO_USER_ID,
            auth_provider=config.auth_provider,
            is_authenticated=False,
            auth_enabled=False,
            groups=("public",),
        )

    token = extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise. Fournissez un token Bearer valide.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if config.auth_provider == "mock":
        return resolve_mock_user(config, token)

    if config.auth_provider not in ENTRA_AUTH_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AUTH_PROVIDER non supporté : {config.auth_provider}.",
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Token Bearer reçu, mais la validation JWT Microsoft Entra ID n'est pas encore "
            "implémentée dans cette V1 préparatoire."
        ),
    )


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def resolve_mock_user(config: Settings, token: str) -> UserContext:
    if config.demo_auth_token and secrets.compare_digest(token, config.demo_auth_token):
        return UserContext(
            user_id=DEMO_USER_ID,
            auth_provider="mock",
            is_authenticated=True,
            auth_enabled=True,
            groups=DEMO_PROFILE_GROUPS[DEMO_USER_ID],
            roles=("demo",),
            token_present=True,
        )
    if config.demo_admin_auth_token and secrets.compare_digest(token, config.demo_admin_auth_token):
        return UserContext(
            user_id=DEMO_ADMIN_ID,
            auth_provider="mock",
            is_authenticated=True,
            auth_enabled=True,
            groups=DEMO_PROFILE_GROUPS[DEMO_ADMIN_ID],
            roles=("admin",),
            token_present=True,
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token Bearer invalide.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def ensure_required_groups(user_context: UserContext, required_groups: tuple[str, ...]) -> None:
    if not required_groups:
        return
    if not set(user_context.groups).intersection(required_groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : l'utilisateur ne fait pas partie des groupes autorisés.",
        )


def effective_groups(
    config: Settings,
    user_context: UserContext,
    demo_profile: str | None = None,
) -> tuple[str, ...]:
    if (
        config.sharepoint_simulator_enabled
        and config.environment in {"development", "demo", "test"}
        and demo_profile in DEMO_PROFILE_GROUPS
    ):
        return DEMO_PROFILE_GROUPS[demo_profile]
    return user_context.groups or ("public",)
