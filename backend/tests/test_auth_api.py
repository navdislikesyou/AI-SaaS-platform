"""Tests for the authentication endpoints.

These cover the token lifecycle over the real FastAPI, router, dependency,
and SQLAlchemy stack, against an isolated temporary SQLite database. The
password hashing is the real Argon2 implementation and the tokens are the real
JWTs, so a passing test means the flow works rather than that a stub was
called.

What is verified here: login success and failure, the access token, the
``/auth/me`` profile endpoint, refresh-token rotation, reuse detection,
logout revocation, and the origin check that protects the cookie endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from httpx import AsyncClient

from app.core.config import Settings

LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
ME_URL = "/api/v1/auth/me"

#: The origin the auth settings trust. The refresh and logout routes refuse a
#: request whose Origin is not in that list.
TRUSTED_ORIGIN = "http://testserver"

#: A password the seeded users are created with.
PASSWORD = "ValidPassword1!"


def cookie_header(token: str) -> dict[str, str]:
    """Return the headers that present one refresh cookie to the server.

    The cookie is sent as a raw header rather than through the client cookie
    jar. The jar keeps whatever the server last set, so a replayed or revoked
    token could otherwise be masked by the newer one.

    Args:
        token: The refresh token to present.

    Returns:
        The request headers carrying the cookie and the trusted origin.
    """
    return {"Cookie": f"refresh_token={token}", "Origin": TRUSTED_ORIGIN}


async def login(client: AsyncClient, email: str, password: str = PASSWORD):
    """Sign a user in and return the response.

    Args:
        client: The HTTP client under test.
        email: The user's email address.
        password: The user's password.

    Returns:
        The login response.
    """
    return await client.post(LOGIN_URL, params={"email": email, "password": password})


def sign_token(settings: Settings, user_id: str, token_version: int, expires_at: datetime | None):
    """Sign an access token for a test.

    Args:
        settings: The settings holding the signing key.
        user_id: The user the token belongs to.
        token_version: The token version the user currently holds.
        expires_at: The expiry, or None to sign a token without one.

    Returns:
        The signed token.
    """
    payload = {"sub": user_id, "token_version": token_version}

    if expires_at is not None:
        payload["exp"] = expires_at

    return pyjwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


async def test_login_returns_profile_and_access_token(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """Valid credentials return the profile and an access token."""
    organization = await make_organization()
    user = await make_user("admin@example.com", role="admin", organization_id=organization.id)

    response = await login(auth_client, user.email)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user.id
    assert body["email"] == "admin@example.com"
    assert body["role"] == "admin"
    assert body["organization_id"] == organization.id
    assert body["access_token"]


async def test_login_sets_an_http_only_refresh_cookie(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """The refresh token is delivered as an HttpOnly cookie scoped to /auth."""
    user = await make_user("admin@example.com")

    response = await login(auth_client, user.email)

    set_cookie = " ".join(response.headers.get_list("set-cookie"))
    assert "refresh_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/api/v1/auth" in set_cookie


async def test_login_accepts_a_mixed_case_email(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """The email is matched case-insensitively."""
    user = await make_user("admin@example.com")

    response = await login(auth_client, "Admin@Example.COM")

    assert response.status_code == 200
    assert response.json()["id"] == user.id


async def test_login_with_a_wrong_password_returns_401(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """A wrong password is refused."""
    user = await make_user("admin@example.com")

    response = await login(auth_client, user.email, "WrongPassword1!")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_with_an_unknown_email_returns_the_same_error(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """An unknown email is refused exactly like a wrong password.

    A different message would turn the login endpoint into an enumeration
    oracle, so the two responses must be indistinguishable.
    """
    await make_user("admin@example.com")

    unknown = await login(auth_client, "nobody@example.com")
    wrong_password = await login(auth_client, "admin@example.com", "WrongPassword1!")

    assert unknown.status_code == 401
    assert wrong_password.status_code == 401
    assert unknown.json()["error"]["message"] == wrong_password.json()["error"]["message"]
    assert unknown.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_login_of_a_deactivated_user_returns_401(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """A deactivated account cannot sign in."""
    user = await make_user("admin@example.com", is_active=False)

    response = await login(auth_client, user.email)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


# ---------------------------------------------------------------------------
# Access token expiry
# ---------------------------------------------------------------------------


async def test_the_access_token_carries_an_expiry(
    auth_client: AsyncClient,
    auth_settings: Settings,
    make_user,
) -> None:
    """The issued token states when it stops being valid."""
    user = await make_user("admin@example.com")

    token = (await login(auth_client, user.email)).json()["access_token"]
    payload = pyjwt.decode(token, auth_settings.jwt_secret_key, algorithms=["HS256"])

    assert "exp" in payload
    assert "iat" in payload

    lifetime = payload["exp"] - payload["iat"]
    expected = auth_settings.jwt_access_token_expire_minutes * 60
    assert abs(lifetime - expected) <= 5


async def test_a_valid_access_token_is_accepted(
    auth_client: AsyncClient,
    auth_settings: Settings,
    make_user,
) -> None:
    """A token that is signed and not expired is accepted."""
    user = await make_user("admin@example.com")

    token = sign_token(
        auth_settings,
        user.id,
        user.token_version,
        datetime.now(UTC) + timedelta(minutes=15),
    )
    response = await auth_client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["id"] == user.id


async def test_an_expired_access_token_is_rejected(
    auth_client: AsyncClient,
    auth_settings: Settings,
    make_user,
) -> None:
    """A token whose expiry has passed is refused with 401.

    The expiry has to be enforced on the server: a token that was copied out
    of the browser must stop working even though it was never revoked.
    """
    user = await make_user("admin@example.com")

    token = sign_token(
        auth_settings,
        user.id,
        user.token_version,
        datetime.now(UTC) - timedelta(seconds=1),
    )
    response = await auth_client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"].lower()


async def test_an_access_token_without_an_expiry_is_rejected(
    auth_client: AsyncClient,
    auth_settings: Settings,
    make_user,
) -> None:
    """A token that states no expiry is refused.

    Accepting it would mean a token could live forever, which is exactly what
    the expiry exists to prevent.
    """
    user = await make_user("admin@example.com")

    token = sign_token(auth_settings, user.id, user.token_version, None)
    response = await auth_client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_a_refreshed_token_expires_too(
    auth_client: AsyncClient,
    auth_settings: Settings,
    make_user,
) -> None:
    """The token issued by a refresh carries an expiry as well."""
    user = await make_user("admin@example.com")

    cookie = (await login(auth_client, user.email)).cookies["refresh_token"]
    refreshed = await auth_client.post(REFRESH_URL, headers=cookie_header(cookie))

    assert refreshed.status_code == 200

    payload = pyjwt.decode(
        refreshed.json()["access_token"],
        auth_settings.jwt_secret_key,
        algorithms=["HS256"],
    )

    assert "exp" in payload


async def test_the_session_is_renewed_after_the_access_token_expired(
    auth_client: AsyncClient,
    auth_settings: Settings,
    make_user,
) -> None:
    """An expired access token can be replaced by refreshing.

    This is the flow the browser relies on: the request fails with 401, the
    client refreshes once, and the new token works.
    """
    user = await make_user("admin@example.com")

    cookie = (await login(auth_client, user.email)).cookies["refresh_token"]

    expired = sign_token(
        auth_settings,
        user.id,
        user.token_version,
        datetime.now(UTC) - timedelta(minutes=1),
    )
    rejected = await auth_client.get(ME_URL, headers={"Authorization": f"Bearer {expired}"})
    assert rejected.status_code == 401

    refreshed = await auth_client.post(REFRESH_URL, headers=cookie_header(cookie))
    assert refreshed.status_code == 200

    accepted = await auth_client.get(
        ME_URL,
        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["id"] == user.id


async def test_the_expiry_is_configurable(
    auth_client: AsyncClient,
    auth_settings: Settings,
    make_user,
) -> None:
    """The lifetime comes from the configuration, not from a constant."""
    user = await make_user("admin@example.com")

    token = (await login(auth_client, user.email)).json()["access_token"]

    payload = pyjwt.decode(token, auth_settings.jwt_secret_key, algorithms=["HS256"])
    lifetime_minutes = (payload["exp"] - payload["iat"]) / 60

    assert lifetime_minutes == pytest.approx(auth_settings.jwt_access_token_expire_minutes, abs=0.1)
    assert auth_settings.jwt_access_token_expire_minutes == 15


# ---------------------------------------------------------------------------
# Access token and /auth/me
# ---------------------------------------------------------------------------


async def test_me_returns_the_authenticated_profile(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A valid access token returns the caller's own profile."""
    organization = await make_organization()
    user = await make_user("admin@example.com", role="admin", organization_id=organization.id)

    token = (await login(auth_client, user.email)).json()["access_token"]
    response = await auth_client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user.id
    assert body["email"] == "admin@example.com"
    assert body["role"] == "admin"
    assert body["organization_id"] == organization.id
    # The profile endpoint never issues a token.
    assert body["access_token"] is None


async def test_me_without_a_token_returns_401(auth_client: AsyncClient) -> None:
    """No credentials means no profile."""
    response = await auth_client.get(ME_URL)

    assert response.status_code == 401


async def test_me_with_a_tampered_token_returns_401(auth_client: AsyncClient) -> None:
    """A token that was not signed by this server is refused."""
    response = await auth_client.get(
        ME_URL,
        headers={"Authorization": "Bearer not.a.real.token"},
    )

    assert response.status_code == 401


async def test_a_previous_access_token_is_revoked_by_a_new_login(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """Signing in again invalidates the access token issued before.

    The token version is bumped on every login, so the older token no longer
    matches the stored version and is refused.
    """
    user = await make_user("admin@example.com")

    first_token = (await login(auth_client, user.email)).json()["access_token"]
    await login(auth_client, user.email)

    response = await auth_client.get(
        ME_URL,
        headers={"Authorization": f"Bearer {first_token}"},
    )

    assert response.status_code == 401
    assert "revoked" in response.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# Refresh rotation
# ---------------------------------------------------------------------------


async def test_refresh_rotates_the_refresh_token(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """Refreshing issues a new refresh token and a new access token."""
    user = await make_user("admin@example.com")

    login_response = await login(auth_client, user.email)
    old_cookie = login_response.cookies["refresh_token"]
    old_access_token = login_response.json()["access_token"]

    response = await auth_client.post(REFRESH_URL, headers=cookie_header(old_cookie))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user.id
    assert body["access_token"] != old_access_token
    assert response.cookies["refresh_token"] != old_cookie


async def test_refresh_returns_a_usable_access_token(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """The access token issued by a refresh works on the protected routes.

    The refresh bumps the stored token version. If that bump is not committed,
    the new access token carries a version the database does not hold and is
    refused straight away.
    """
    user = await make_user("admin@example.com")

    cookie = (await login(auth_client, user.email)).cookies["refresh_token"]
    refreshed = await auth_client.post(REFRESH_URL, headers=cookie_header(cookie))

    assert refreshed.status_code == 200

    response = await auth_client.get(
        ME_URL,
        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == user.id


async def test_refresh_with_a_reused_token_returns_401(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """A refresh token that was already consumed cannot be used again."""
    user = await make_user("admin@example.com")

    cookie = (await login(auth_client, user.email)).cookies["refresh_token"]

    first = await auth_client.post(REFRESH_URL, headers=cookie_header(cookie))
    assert first.status_code == 200

    replay = await auth_client.post(REFRESH_URL, headers=cookie_header(cookie))

    assert replay.status_code == 401


async def test_refresh_without_a_cookie_returns_401(auth_client: AsyncClient) -> None:
    """Refreshing without a refresh token is refused."""
    response = await auth_client.post(REFRESH_URL, headers={"Origin": TRUSTED_ORIGIN})

    assert response.status_code == 401


async def test_refresh_from_an_untrusted_origin_returns_400(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """A cross-site refresh is refused before the token is even read."""
    user = await make_user("admin@example.com")
    cookie = (await login(auth_client, user.email)).cookies["refresh_token"]

    response = await auth_client.post(
        REFRESH_URL,
        headers={"Cookie": f"refresh_token={cookie}", "Origin": "http://attacker.example"},
    )

    assert response.status_code == 400


async def test_refresh_of_a_deactivated_user_returns_401(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A deactivated user cannot refresh their session."""
    organization = await make_organization()
    admin = await make_user(
        "admin@example.com",
        role="admin",
        organization_id=organization.id,
    )
    employee = await make_user(
        "employee@example.com",
        organization_id=organization.id,
    )

    cookie = (await login(auth_client, employee.email)).cookies["refresh_token"]

    # The admin deactivates the employee.
    admin_token = (await login(auth_client, admin.email)).json()["access_token"]
    deactivate = await auth_client.post(
        f"/api/v1/users/{employee.id}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate.status_code == 200

    response = await auth_client.post(REFRESH_URL, headers=cookie_header(cookie))

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


async def test_logout_revokes_the_refresh_token(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """After logout the refresh token no longer works."""
    user = await make_user("admin@example.com")

    cookie = (await login(auth_client, user.email)).cookies["refresh_token"]

    logout = await auth_client.post(LOGOUT_URL, headers=cookie_header(cookie))
    assert logout.status_code == 200

    response = await auth_client.post(REFRESH_URL, headers=cookie_header(cookie))

    assert response.status_code == 401


async def test_logout_from_an_untrusted_origin_returns_400(
    auth_client: AsyncClient,
    make_user,
) -> None:
    """A cross-site logout is refused and the token is left untouched."""
    user = await make_user("admin@example.com")
    cookie = (await login(auth_client, user.email)).cookies["refresh_token"]

    response = await auth_client.post(
        LOGOUT_URL,
        headers={"Cookie": f"refresh_token={cookie}", "Origin": "http://attacker.example"},
    )

    assert response.status_code == 400

    # The token was not revoked by the refused request.
    refresh = await auth_client.post(REFRESH_URL, headers=cookie_header(cookie))
    assert refresh.status_code == 200


@pytest.mark.parametrize(
    ("url", "method"),
    [(LOGIN_URL, "post"), (REFRESH_URL, "post"), (LOGOUT_URL, "post"), (ME_URL, "get")],
)
async def test_auth_endpoints_are_registered(
    auth_client: AsyncClient,
    url: str,
    method: str,
) -> None:
    """Every auth endpoint is mounted under the versioned prefix."""
    response = await getattr(auth_client, method)(url)

    # None of these may answer with "no such route".
    assert response.status_code != 404
