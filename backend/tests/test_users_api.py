"""Tests for the user-management API.

These cover the admin-protected user operations over the real FastAPI, router,
dependency, and SQLAlchemy stack, against an isolated temporary SQLite
database.

What is verified here: organisation scoping of the user list, admin-only
enforcement, creation, role changes, deactivation and reactivation, manager
assignment, and the protection that stops an organisation from losing its
last active administrator.
"""

from __future__ import annotations

from httpx import AsyncClient

USERS_URL = "/api/v1/users/"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"

PASSWORD = "ValidPassword1!"


async def access_token(client: AsyncClient, email: str, password: str = PASSWORD) -> str:
    """Sign a user in and return the access token.

    Args:
        client: The HTTP client under test.
        email: The user's email address.
        password: The user's password.

    Returns:
        The access token.
    """
    response = await client.post(LOGIN_URL, params={"email": email, "password": password})

    assert response.status_code == 200, response.text

    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    """Return the Authorization header for an access token.

    Args:
        token: The access token.

    Returns:
        The request headers.
    """
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


async def test_list_users_returns_only_the_callers_organization(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A user sees their own colleagues and nobody from another tenant."""
    mine = await make_organization(name="Mine", slug="mine")
    theirs = await make_organization(name="Theirs", slug="theirs")

    admin = await make_user("admin@example.com", role="admin", organization_id=mine.id)
    colleague = await make_user("colleague@example.com", organization_id=mine.id)
    stranger = await make_user("stranger@example.com", organization_id=theirs.id)

    token = await access_token(auth_client, admin.email)
    response = await auth_client.get(USERS_URL, headers=auth_headers(token))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    emails = {user["email"] for user in body["data"]}
    assert emails == {admin.email, colleague.email}
    assert stranger.email not in emails
    # The listing never carries the token version.
    assert all("token_version" not in user for user in body["data"])


async def test_list_users_requires_authentication(auth_client: AsyncClient) -> None:
    """The listing is not public."""
    response = await auth_client.get(USERS_URL)

    assert response.status_code == 401


async def test_list_users_is_available_to_an_employee(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """Any active member of an organisation may list its users."""
    organization = await make_organization()
    employee = await make_user("employee@example.com", organization_id=organization.id)

    token = await access_token(auth_client, employee.email)
    response = await auth_client.get(USERS_URL, headers=auth_headers(token))

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


async def test_create_user_is_refused_for_an_employee(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """Creating a user requires the admin role."""
    organization = await make_organization()
    employee = await make_user("employee@example.com", organization_id=organization.id)

    token = await access_token(auth_client, employee.email)
    response = await auth_client.post(
        USERS_URL,
        params={"email": "new@example.com", "full_name": "New Person"},
        headers=auth_headers(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_create_user_requires_authentication(auth_client: AsyncClient) -> None:
    """Creating a user is not public."""
    response = await auth_client.post(
        USERS_URL,
        params={"email": "new@example.com", "full_name": "New Person"},
    )

    assert response.status_code == 401


async def test_admin_creates_a_user_in_their_own_organization(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A created user belongs to the creating admin's organization."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)

    token = await access_token(auth_client, admin.email)
    response = await auth_client.post(
        USERS_URL,
        params={"email": "New.Person@Example.com", "full_name": "New Person", "role": "employee"},
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["email"] == "new.person@example.com"
    assert data["role"] == "employee"
    assert data["organization_id"] == organization.id
    assert data["is_active"] is True
    # The one-time password is shown once and never stored in plain text.
    assert data["temporary_password"]


async def test_create_user_rejects_a_duplicate_email(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """The same email cannot be created twice."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)
    await make_user("taken@example.com", organization_id=organization.id)

    token = await access_token(auth_client, admin.email)
    response = await auth_client.post(
        USERS_URL,
        params={"email": "taken@example.com", "full_name": "Taken"},
        headers=auth_headers(token),
    )

    assert response.status_code == 409


async def test_create_user_rejects_an_unknown_role(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A role outside the three known ones is refused."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)

    token = await access_token(auth_client, admin.email)
    response = await auth_client.post(
        USERS_URL,
        params={"email": "new@example.com", "full_name": "New", "role": "superuser"},
        headers=auth_headers(token),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_create_user_rejects_a_manager_from_another_organization(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A manager must belong to the same organization as the new user."""
    mine = await make_organization(name="Mine", slug="mine")
    theirs = await make_organization(name="Theirs", slug="theirs")
    admin = await make_user("admin@example.com", role="admin", organization_id=mine.id)
    foreign_manager = await make_user(
        "manager@example.com",
        role="manager",
        organization_id=theirs.id,
    )

    token = await access_token(auth_client, admin.email)
    response = await auth_client.post(
        USERS_URL,
        params={
            "email": "new@example.com",
            "full_name": "New",
            "manager_id": foreign_manager.id,
        },
        headers=auth_headers(token),
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Role changes
# ---------------------------------------------------------------------------


async def test_change_role_is_refused_for_an_employee(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """Changing a role requires the admin role."""
    organization = await make_organization()
    employee = await make_user("employee@example.com", organization_id=organization.id)
    target = await make_user("target@example.com", organization_id=organization.id)

    token = await access_token(auth_client, employee.email)
    response = await auth_client.patch(
        f"{USERS_URL}{target.id}",
        params={"new_role": "manager"},
        headers=auth_headers(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_admin_changes_a_users_role(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """An admin can promote a user."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)
    target = await make_user("target@example.com", organization_id=organization.id)

    token = await access_token(auth_client, admin.email)
    response = await auth_client.patch(
        f"{USERS_URL}{target.id}",
        params={"new_role": "manager"},
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["data"]["role"] == "manager"


async def test_changing_a_role_revokes_the_targets_access_token(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """The promoted user's existing access token stops working."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)
    target = await make_user("target@example.com", organization_id=organization.id)

    target_token = await access_token(auth_client, target.email)
    assert (await auth_client.get(ME_URL, headers=auth_headers(target_token))).status_code == 200

    admin_token = await access_token(auth_client, admin.email)
    await auth_client.patch(
        f"{USERS_URL}{target.id}",
        params={"new_role": "manager"},
        headers=auth_headers(admin_token),
    )

    response = await auth_client.get(ME_URL, headers=auth_headers(target_token))

    assert response.status_code == 401


async def test_admin_cannot_change_a_user_in_another_organization(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A user of another tenant cannot be modified."""
    mine = await make_organization(name="Mine", slug="mine")
    theirs = await make_organization(name="Theirs", slug="theirs")
    admin = await make_user("admin@example.com", role="admin", organization_id=mine.id)
    stranger = await make_user("stranger@example.com", organization_id=theirs.id)

    token = await access_token(auth_client, admin.email)
    response = await auth_client.patch(
        f"{USERS_URL}{stranger.id}",
        params={"new_role": "employee"},
        headers=auth_headers(token),
    )

    assert response.status_code == 409


async def test_the_only_admin_cannot_demote_themselves(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """An organisation cannot lose its last active administrator.

    The administrator is the only one, so demoting themselves would leave the
    organisation with nobody able to administer it.
    """
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)

    token = await access_token(auth_client, admin.email)
    response = await auth_client.patch(
        f"{USERS_URL}{admin.id}",
        params={"new_role": "employee"},
        headers=auth_headers(token),
    )

    assert response.status_code == 400
    assert "administrator" in response.json()["error"]["message"].lower()


async def test_the_last_active_admin_cannot_be_demoted(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """An inactive administrator cannot be demoted while alone in the role.

    The organisation's only active administrator is the caller, so the
    organisation is one demotion away from having none.
    """
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)
    inactive_admin = await make_user(
        "second@example.com",
        role="admin",
        organization_id=organization.id,
        is_active=False,
    )

    token = await access_token(auth_client, admin.email)
    response = await auth_client.patch(
        f"{USERS_URL}{inactive_admin.id}",
        params={"new_role": "employee"},
        headers=auth_headers(token),
    )

    assert response.status_code == 400
    assert "administrator" in response.json()["error"]["message"].lower()


async def test_an_admin_can_be_demoted_when_another_admin_remains(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """The protection only applies to the last active administrator."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)
    second_admin = await make_user(
        "second@example.com",
        role="admin",
        organization_id=organization.id,
    )

    token = await access_token(auth_client, admin.email)
    response = await auth_client.patch(
        f"{USERS_URL}{second_admin.id}",
        params={"new_role": "employee"},
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["data"]["role"] == "employee"


# ---------------------------------------------------------------------------
# Deactivation and activation
# ---------------------------------------------------------------------------


async def test_admin_deactivates_a_user(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """An admin can deactivate a colleague."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)
    target = await make_user("target@example.com", organization_id=organization.id)

    token = await access_token(auth_client, admin.email)
    response = await auth_client.post(
        f"{USERS_URL}{target.id}/deactivate",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is False


async def test_a_deactivated_user_loses_access(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A deactivated user's access token stops working immediately."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)
    target = await make_user("target@example.com", organization_id=organization.id)

    target_token = await access_token(auth_client, target.email)

    admin_token = await access_token(auth_client, admin.email)
    await auth_client.post(
        f"{USERS_URL}{target.id}/deactivate",
        headers=auth_headers(admin_token),
    )

    response = await auth_client.get(ME_URL, headers=auth_headers(target_token))

    assert response.status_code == 401


async def test_a_deactivated_user_cannot_sign_in(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A deactivated account cannot obtain a new session."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)
    target = await make_user("target@example.com", organization_id=organization.id)

    admin_token = await access_token(auth_client, admin.email)
    await auth_client.post(
        f"{USERS_URL}{target.id}/deactivate",
        headers=auth_headers(admin_token),
    )

    response = await auth_client.post(
        LOGIN_URL,
        params={"email": target.email, "password": PASSWORD},
    )

    assert response.status_code == 401


async def test_an_admin_reactivates_a_deactivated_user(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A deactivated account works again once it is activated."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)
    target = await make_user("target@example.com", organization_id=organization.id)

    token = await access_token(auth_client, admin.email)
    await auth_client.post(
        f"{USERS_URL}{target.id}/deactivate",
        headers=auth_headers(token),
    )

    response = await auth_client.post(
        f"{USERS_URL}{target.id}/activate",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is True

    login = await auth_client.post(
        LOGIN_URL,
        params={"email": target.email, "password": PASSWORD},
    )
    assert login.status_code == 200


async def test_an_admin_cannot_deactivate_their_own_account(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """Self-deactivation is refused before anything else is checked."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)

    token = await access_token(auth_client, admin.email)
    response = await auth_client.post(
        f"{USERS_URL}{admin.id}/deactivate",
        headers=auth_headers(token),
    )

    assert response.status_code == 400
    assert "own account" in response.json()["error"]["message"].lower()


async def test_an_admin_can_deactivate_another_admin_when_two_exist(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """Deactivating one administrator is allowed while another remains."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)
    second_admin = await make_user(
        "second@example.com",
        role="admin",
        organization_id=organization.id,
    )

    token = await access_token(auth_client, admin.email)
    response = await auth_client.post(
        f"{USERS_URL}{second_admin.id}/deactivate",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is False


async def test_an_inactive_admin_can_be_activated_again(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A deactivated administrator is restored, so the tenant can have two."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)
    second_admin = await make_user(
        "second@example.com",
        role="admin",
        organization_id=organization.id,
    )

    token = await access_token(auth_client, admin.email)

    deactivated = await auth_client.post(
        f"{USERS_URL}{second_admin.id}/deactivate",
        headers=auth_headers(token),
    )
    assert deactivated.status_code == 200

    response = await auth_client.post(
        f"{USERS_URL}{second_admin.id}/activate",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is True


async def test_deactivation_is_refused_for_a_user_in_another_organization(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A user of another tenant cannot be deactivated."""
    mine = await make_organization(name="Mine", slug="mine")
    theirs = await make_organization(name="Theirs", slug="theirs")
    admin = await make_user("admin@example.com", role="admin", organization_id=mine.id)
    stranger = await make_user("stranger@example.com", organization_id=theirs.id)

    token = await access_token(auth_client, admin.email)
    response = await auth_client.post(
        f"{USERS_URL}{stranger.id}/deactivate",
        headers=auth_headers(token),
    )

    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Manager assignment
# ---------------------------------------------------------------------------


async def test_manager_assignment_is_refused_for_an_employee(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """Only a manager or an admin may assign a manager."""
    organization = await make_organization()
    employee = await make_user("employee@example.com", organization_id=organization.id)
    target = await make_user("target@example.com", organization_id=organization.id)

    token = await access_token(auth_client, employee.email)
    response = await auth_client.patch(
        f"{USERS_URL}{target.id}/manager",
        params={"manager_id": employee.id},
        headers=auth_headers(token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_a_manager_assigns_a_manager(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A manager may set a colleague's manager inside the organisation."""
    organization = await make_organization()
    manager = await make_user(
        "manager@example.com",
        role="manager",
        organization_id=organization.id,
    )
    target = await make_user("target@example.com", organization_id=organization.id)

    token = await access_token(auth_client, manager.email)
    response = await auth_client.patch(
        f"{USERS_URL}{target.id}/manager",
        params={"manager_id": manager.id},
        headers=auth_headers(token),
    )

    assert response.status_code == 200


async def test_a_manager_cannot_be_taken_from_another_organization(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A manager from another tenant cannot be assigned."""
    mine = await make_organization(name="Mine", slug="mine")
    theirs = await make_organization(name="Theirs", slug="theirs")
    admin = await make_user("admin@example.com", role="admin", organization_id=mine.id)
    target = await make_user("target@example.com", organization_id=mine.id)
    foreign_manager = await make_user(
        "foreign@example.com",
        role="manager",
        organization_id=theirs.id,
    )

    token = await access_token(auth_client, admin.email)
    response = await auth_client.patch(
        f"{USERS_URL}{target.id}/manager",
        params={"manager_id": foreign_manager.id},
        headers=auth_headers(token),
    )

    assert response.status_code == 409


async def test_a_user_cannot_be_their_own_manager(
    auth_client: AsyncClient,
    make_user,
    make_organization,
) -> None:
    """A circular reporting line is refused."""
    organization = await make_organization()
    admin = await make_user("admin@example.com", role="admin", organization_id=organization.id)

    token = await access_token(auth_client, admin.email)
    response = await auth_client.patch(
        f"{USERS_URL}{admin.id}/manager",
        params={"manager_id": admin.id},
        headers=auth_headers(token),
    )

    assert response.status_code == 400
