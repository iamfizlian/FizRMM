from __future__ import annotations

import os
from typing import Any

from .integrations.config import runtime_service_value
from .models import AccessDenied, TenantContext


def context_from_authorization(authorization: str | None) -> TenantContext | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    claims = validate_bearer_token(token.strip())
    return context_from_claims(claims)


def validate_bearer_token(token: str) -> dict[str, Any]:
    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError as exc:
        raise AccessDenied("JWT validation dependencies are not installed") from exc

    issuer = keycloak_issuer()
    jwks_url = keycloak_jwks_url()
    client_id = keycloak_client_id()
    if not issuer or not jwks_url or not client_id:
        raise AccessDenied("Keycloak JWT validation is not configured")

    try:
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )
    except Exception as exc:
        raise AccessDenied("invalid bearer token") from exc

    audiences = claims.get("aud", [])
    if isinstance(audiences, str):
        audiences = [audiences]
    authorized_party = claims.get("azp")
    if client_id not in audiences and authorized_party != client_id:
        raise AccessDenied("bearer token was not issued for FizRMM")
    return claims


def context_from_claims(claims: dict[str, Any]) -> TenantContext:
    roles = realm_roles(claims)
    platform_admin = "platform-admin" in roles
    org_ids = org_claims(claims)
    role = "platform-admin" if platform_admin else "technician"
    return TenantContext(
        user_id=str(claims.get("preferred_username") or claims.get("sub") or "unknown"),
        allowed_org_ids=tuple(org_ids),
        role=role,
        platform_admin=platform_admin,
    )


def realm_roles(claims: dict[str, Any]) -> set[str]:
    realm_access = claims.get("realm_access", {})
    roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    return {str(role) for role in roles}


def org_claims(claims: dict[str, Any]) -> list[str]:
    value = claims.get("fizrmm_orgs") or claims.get("org_ids") or claims.get("organizations") or []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item).strip()]
    return []


def keycloak_client_id() -> str:
    return os.getenv("OIDC_CLIENT_ID", "") or runtime_service_value("identity", "client_id", "")


def keycloak_issuer() -> str:
    explicit = os.getenv("KEYCLOAK_ISSUER", "") or runtime_service_value("identity", "issuer_url", "")
    if explicit:
        return explicit
    url = os.getenv("KEYCLOAK_URL", "") or runtime_service_value("identity", "public_url", "")
    realm = os.getenv("KEYCLOAK_REALM", "") or runtime_service_value("identity", "realm", "")
    return f"{url.rstrip('/')}/realms/{realm}" if url and realm else ""


def keycloak_jwks_url() -> str:
    explicit = os.getenv("KEYCLOAK_JWKS_URL", "") or runtime_service_value("identity", "jwks_url", "")
    if explicit:
        return explicit
    issuer = keycloak_issuer()
    return f"{issuer.rstrip('/')}/protocol/openid-connect/certs" if issuer else ""
