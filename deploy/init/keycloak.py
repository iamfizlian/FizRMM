from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class KeycloakInit:
    def __init__(
        self,
        base_url: str,
        public_url: str,
        admin_user: str,
        admin_password: str,
        realm: str,
        client_id: str,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.public_url = public_url.rstrip("/")
        self.admin_user = admin_user
        self.admin_password = admin_password
        self.realm = realm
        self.client_id = client_id

    def configure(self) -> dict[str, Any]:
        token = self.admin_token()
        self.ensure_realm(token)
        self.ensure_client(token)
        roles = {
            "platform-admin": self.ensure_role(token, "platform-admin", "Full FizRMM platform access"),
            "technician": self.ensure_role(token, "technician", "Tenant-scoped technician access"),
        }
        self.ensure_user(
            token,
            username=os.getenv("FIZRMM_DEMO_ADMIN_USER", "demo-admin"),
            password=os.getenv("FIZRMM_DEMO_ADMIN_PASSWORD", "demo-admin-password"),
            org_ids=["org_acme", "org_globex"],
            roles=[roles["platform-admin"]],
        )
        self.ensure_user(
            token,
            username=os.getenv("FIZRMM_DEMO_TECH_USER", "demo-tech"),
            password=os.getenv("FIZRMM_DEMO_TECH_PASSWORD", "demo-tech-password"),
            org_ids=["org_acme"],
            roles=[roles["technician"]],
        )
        return {
            "realm": self.realm,
            "client_id": self.client_id,
            "issuer_url": f"{self.public_url}/realms/{self.realm}",
            "jwks_url": f"{self.public_url}/realms/{self.realm}/protocol/openid-connect/certs",
            "token_url": f"{self.public_url}/realms/{self.realm}/protocol/openid-connect/token",
            "auth_url": f"{self.public_url}/realms/{self.realm}/protocol/openid-connect/auth",
        }

    def admin_token(self) -> str:
        deadline = time.monotonic() + 120
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                response = self.form(
                    "/realms/master/protocol/openid-connect/token",
                    {
                        "grant_type": "password",
                        "client_id": "admin-cli",
                        "username": self.admin_user,
                        "password": self.admin_password,
                    },
                    token=None,
                )
                return str(response["access_token"])
            except Exception as exc:  # Keycloak may accept TCP before the realm is ready.
                last_error = exc
                time.sleep(3)
        raise RuntimeError(f"Keycloak admin token request failed: {last_error}")

    def ensure_realm(self, token: str) -> None:
        if self.exists(f"/admin/realms/{self.realm}", token):
            return
        self.json_request(
            "/admin/realms",
            "POST",
            {
                "realm": self.realm,
                "enabled": True,
                "displayName": "FizRMM",
            },
            token,
            expected=(201, 204),
        )

    def ensure_client(self, token: str) -> None:
        existing = self.json_request(
            f"/admin/realms/{self.realm}/clients?clientId={self.client_id}",
            "GET",
            None,
            token,
        )
        if isinstance(existing, list) and existing:
            return
        self.json_request(
            f"/admin/realms/{self.realm}/clients",
            "POST",
            {
                "clientId": self.client_id,
                "name": "FizRMM Portal",
                "enabled": True,
                "publicClient": True,
                "standardFlowEnabled": True,
                "directAccessGrantsEnabled": True,
                "redirectUris": [
                    "http://127.0.0.1:5173/*",
                    "http://localhost:5173/*",
                ],
                "webOrigins": [
                    "http://127.0.0.1:5173",
                    "http://localhost:5173",
                ],
            },
            token,
            expected=(201, 204),
        )

    def ensure_role(self, token: str, name: str, description: str) -> dict[str, Any]:
        path = f"/admin/realms/{self.realm}/roles/{name}"
        if not self.exists(path, token):
            self.json_request(
                f"/admin/realms/{self.realm}/roles",
                "POST",
                {"name": name, "description": description},
                token,
                expected=(201, 204),
            )
        role = self.json_request(path, "GET", None, token)
        if not isinstance(role, dict):
            raise RuntimeError(f"Keycloak role lookup returned unexpected payload for {name}")
        return role

    def ensure_user(
        self,
        token: str,
        username: str,
        password: str,
        org_ids: list[str],
        roles: list[dict[str, Any]],
    ) -> None:
        user_id = self.lookup_user_id(token, username)
        if user_id is None:
            self.json_request(
                f"/admin/realms/{self.realm}/users",
                "POST",
                {
                    "username": username,
                    "enabled": True,
                    "emailVerified": True,
                    "attributes": {"fizrmm_orgs": org_ids},
                },
                token,
                expected=(201, 204),
            )
            user_id = self.lookup_user_id(token, username)
        if user_id is None:
            raise RuntimeError(f"failed to create Keycloak user: {username}")
        self.json_request(
            f"/admin/realms/{self.realm}/users/{user_id}/reset-password",
            "PUT",
            {"type": "password", "value": password, "temporary": False},
            token,
            expected=(204,),
        )
        self.json_request(
            f"/admin/realms/{self.realm}/users/{user_id}/role-mappings/realm",
            "POST",
            roles,
            token,
            expected=(204,),
        )

    def lookup_user_id(self, token: str, username: str) -> str | None:
        users = self.json_request(
            f"/admin/realms/{self.realm}/users?username={username}&exact=true",
            "GET",
            None,
            token,
        )
        if isinstance(users, list) and users:
            return str(users[0]["id"])
        return None

    def exists(self, path: str, token: str) -> bool:
        try:
            self.json_request(path, "GET", None, token)
            return True
        except HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def form(self, path: str, payload: dict[str, str], token: str | None) -> dict[str, Any]:
        body = urlencode(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token is not None:
            request.add_header("Authorization", f"Bearer {token}")
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def json_request(
        self,
        path: str,
        method: str,
        payload: Any,
        token: str,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )
        if data is not None:
            request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=10) as response:
            if response.status not in expected:
                raise RuntimeError(f"unexpected Keycloak status {response.status} for {method} {path}")
            body = response.read().decode("utf-8")
        return json.loads(body) if body else None
