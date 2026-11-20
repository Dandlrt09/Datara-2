"""Authentication router: register, login, logout, me.

All endpoints are unauthenticated except ``/logout`` and ``/me``.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from core.errors import DuplicateError
from server.api.deps import current_user, get_store
from server.app_mode import get_mode
from server.api.rate_limit import PersistentAttemptLimiter
from server.services.auth_service import (
    MAX_DISPLAY_NAME_LENGTH,
    RESET_TOKEN_TTL_SECONDS,
    TOKEN_PURPOSE_RESET_PASSWORD,
    TOKEN_PURPOSE_VERIFY_EMAIL,
    VERIFICATION_TOKEN_TTL_SECONDS,
    build_expire_cookie_header,
    build_set_cookie_header,
    generate_raw_token,
    hash_password,
    hash_token,
    is_valid_email,
    normalize_display_name,
    normalize_email,
    verify_credentials,
    verify_password,
)
from server.services.mailer import (
    Mailer,
    get_mailer,
    render_new_session_email,
    render_password_changed_email,
    render_password_reset_email,
    render_reset_email,
    render_verification_email,
    reset_link,
    resolve_app_url,
    verification_link,
)
from server.services.sqlite_store import SqliteStore
from server.services.terms import TERMS_VERSION

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request / Response schemas ─────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """Body of ``POST /api/auth/register``.

    ``name`` is optional on purpose (register-experience S2): the signup form
    asks for a name but lets it empty, and an empty name means the same as no
    name at all -- the display falls back to the email-derived one, exactly as
    for an account that never chose one.

    ``terms_version`` is the terms of use version the person read before
    ticking the box (terms-of-use D5). The route refuses anything that is not
    the version in force, so what an account records is the text accepted.
    """

    email: str
    password: str
    name: str | None = None
    terms_version: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class LocalProfileRequest(BaseModel):
    """Body of ``POST /api/auth/local-profile`` (F1/T2b, L10).

    ``name`` is required only when the profile is being created: a local
    profile has no email, so the display name is the only thing that can name
    it (D5). An open call -- the profile already exists -- has nothing to name,
    so the field is optional and any value is ignored (a boot never renames).
    """

    name: str | None = None


class LocalProfileStatus(BaseModel):
    """Body of ``GET /api/auth/local-profile`` (F1/T2b, L10; T3, D3; T4, D4).

    The identity state the first-boot landing needs. ``exists`` lets the first
    boot tell "create the profile" (false) from "open the profile" (true)
    before it holds any session. ``hosted_accounts`` reports whether the
    database already holds email accounts: when it does, the local profile is
    only OFFERED on an empty database (D3), so the visitor keeps the email
    login instead of seeing the creation form. ``locked`` reports whether the
    optional local lock is ON (D4), so the frontend knows to ask for the
    password instead of opening silently. ``lock_step_pending`` reports whether
    the optional lock step on the onboarding path (T3/D1) still needs an
    answer: true for an unlocked profile that neither turned the lock on nor
    declined, false once either answer was persisted.

    This signal lives on the auth surface, not in ``/api/app-config``: the mode
    there is a deployment property (D2), while "is there a local profile / are
    there email accounts / is it locked / is the step answered" is data. The
    rescue key is deliberately NOT here: it is shown once at lock time and
    never read back.
    """

    exists: bool
    hosted_accounts: bool
    locked: bool
    lock_step_pending: bool


class LocalLockRequest(BaseModel):
    """Body of ``POST /api/auth/local-profile/lock`` (F1/T4, D4).

    The password that turns the optional lock on. It is hashed before storage;
    the raw rescue key minted alongside it is the only secret ever returned in
    the clear, and only in this response.
    """

    password: str


class LocalOpenRequest(BaseModel):
    """Body of ``POST /api/auth/local-profile/open`` (F1/T4, D4)."""

    password: str


class LocalRescueRequest(BaseModel):
    """Body of ``POST /api/auth/local-profile/rescue`` (F1/T4, D4).

    ``rescue_key`` is the raw key shown once when the profile was locked;
    ``new_password`` replaces the lock's password, and the accepted key is
    rotated so it stops working.
    """

    rescue_key: str
    new_password: str


class LocalRescueKeyResponse(BaseModel):
    """The one-time rescue key, returned by lock and rescue (F1/T4, D4).

    The only shape that carries the raw key: it is minted here, shown once, and
    never stored -- the database keeps only its SHA-256 hash.
    """

    rescue_key: str


class VerifyEmailRequest(BaseModel):
    """Body of ``POST /api/auth/verify-email`` (D9).

    The raw token travels in the body, not the URL: the mailed link points at
    the frontend route, and the screen is what POSTs the token here.
    """

    token: str


class ResendVerificationRequest(BaseModel):
    """Body of ``POST /api/auth/resend-verification`` (D6)."""

    email: str


class ForgotPasswordRequest(BaseModel):
    """Body of ``POST /api/auth/forgot-password`` (D6)."""

    email: str


class ResetPasswordRequest(BaseModel):
    """Body of ``POST /api/auth/reset-password`` (D8).

    ``token`` is the raw token from the mailed link; ``new_password`` is only
    shaped (length) after the token has proven to belong to a live request.
    """

    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    confirmation: str
    current_password: str


class NameUpdateRequest(BaseModel):
    """Body of ``PATCH /api/auth/me`` (T1/D2).

    ``name`` is required: an empty string is the documented way to clear the
    name, so a missing field is a malformed request (422 from FastAPI), not a
    second spelling of "clear" (D3).
    """

    name: str


class UserResponse(BaseModel):
    id: int
    # None for a local profile, which has no address (F1/T2b); hosted accounts
    # always carry one, so every existing caller keeps passing the same value.
    email: str | None
    # The user-chosen display name, or None when they never set one (T1/D1).
    # The frontend resolves None to the email-derived name (D6).
    name: str | None = None
    # Scheduled purge deadline, or None. Exposed so login and /me can render the
    # grace-period interstitial (S7) without a second request.
    pending_deletion_at: str | None = None


class AuthSessionResponse(BaseModel):
    """One row of the active-sessions list (T2).

    ``user_agent`` is the truncated header captured when that session was
    opened; ``is_current`` marks the row the request came from. The token hash
    is deliberately absent from this schema, not just from the response.
    """

    id: int
    user_agent: str | None = None
    created_at: str
    last_seen_at: str
    is_current: bool


class ActiveSessionsResponse(BaseModel):
    sessions: list[AuthSessionResponse]
    # When another live session was created and the user has not acknowledged
    # it yet; the frontend uses it to raise the in-app notice once (D4/D9).
    new_session_at: str | None = None


# ── Helper ─────────────────────────────────────────────────────────────────────


def _require_hosted_mode() -> None:
    """Refuse every email flow outside hosted mode (F1/T2, S2, D2).

    The desktop build runs with ``DATARA_MODE=local`` and has no mailbox, so
    register, verification and recovery cannot work there: hiding the screens
    in the frontend is the UX, not the enforcement. Serving them anyway would
    let a hosted account exist in a local install, which flips
    ``hosted_accounts`` and sends every later boot to the login screen with no
    path back to the local profile (S2). In hosted mode this is a no-op.

    Attached as a router dependency rather than checked inside each body, so it
    runs before the request body is validated: a refused call must not spend an
    attempt brake, hash a password, create a row, or mail anything, and the
    answer must not depend on how well formed the payload was.
    """
    if get_mode() != "hosted":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email flows are only available in hosted mode",
        )


def _cookie_secure() -> bool:
    """Whether the session cookie should carry ``Secure`` (F9/S3).

    True only when the app is served over HTTPS, which the deployment
    publishes in ``DATARA_APP_URL`` (the desktop build sets ``http://...``,
    where a ``Secure`` cookie would never be sent and login would break).
    """
    return resolve_app_url().startswith("https://")


async def _mint_session(
    store: SqliteStore,
    user_id: int,
    user_agent: str | None,
) -> tuple[str, str, dict]:
    """Generate a raw token and create the corresponding auth session.

    ``user_agent`` is the request header, stored truncated (D2) so the sessions
    list can name the browser; no IP is stored anywhere.

    Returns (raw_token, set_cookie_header, session_row): the stored row is
    handed back so the caller can use its truncated ``user_agent`` and its
    ``token_hash`` without a second lookup (F9/S10).
    """
    raw_token = generate_raw_token()
    token_hash = hash_token(raw_token)
    session = await store.create_auth_session(
        user_id, token_hash, user_agent=user_agent
    )
    cookie = build_set_cookie_header(raw_token, secure=_cookie_secure())
    return raw_token, cookie, session


async def _send_notice(
    mailer: Mailer,
    *,
    to: str,
    subject: str,
    body: str,
    user_id: int,
    description: str,
) -> None:
    """Send one notice, swallowing any delivery failure (F9/S10).

    A broken mailbox must never change the HTTP response nor undo the side
    effect the request already applied -- the same best-effort rule the
    verification and reset mails follow.
    """
    try:
        await mailer.send(to=to, subject=subject, body=body)
    except Exception:
        logger.exception(
            "Failed to send %s email to user_id=%s", description, user_id
        )


async def _issue_and_send_verification(
    store: SqliteStore,
    user: dict,
    mailer: Mailer,
) -> None:
    """Mint a fresh verification token for *user* and mail the link.

    The raw token exists only in the mailed link; the store keeps its hash,
    the purpose and the address the proof belongs to. Issuing a new token
    retires the previous one (D1), so "reenviar" leaves exactly one redeemable
    link. A delivery failure is logged and swallowed: the account already
    exists, and the resend button is the recovery path -- a broken mailbox must
    not undo a signup (S3).
    """
    raw_token = generate_raw_token()
    await store.create_auth_token(
        user["id"],
        hash_token(raw_token),
        TOKEN_PURPOSE_VERIFY_EMAIL,
        VERIFICATION_TOKEN_TTL_SECONDS,
        email=user["email"],
    )
    link = verification_link(resolve_app_url(), raw_token)
    subject, body = render_verification_email(
        link, ttl_hours=VERIFICATION_TOKEN_TTL_SECONDS // 3600
    )
    await _send_notice(
        mailer,
        to=user["email"],
        subject=subject,
        body=body,
        user_id=user["id"],
        description="verification",
    )


async def _issue_and_send_reset(
    store: SqliteStore,
    user: dict,
    mailer: Mailer,
) -> None:
    """Mint a fresh reset token for *user* and mail the link.

    Mirrors ``_issue_and_send_verification``: the store keeps only the hash,
    purpose and address; issuing a new token retires the previous live reset
    link (D1), so a second request leaves exactly one redeemable link. A
    delivery failure is logged and swallowed -- the route must answer 202
    regardless (D6), and a broken mailbox cannot leak that the account exists.
    """
    raw_token = generate_raw_token()
    await store.create_auth_token(
        user["id"],
        hash_token(raw_token),
        TOKEN_PURPOSE_RESET_PASSWORD,
        RESET_TOKEN_TTL_SECONDS,
        email=user["email"],
    )
    link = reset_link(resolve_app_url(), raw_token)
    subject, body = render_reset_email(
        link, ttl_hours=RESET_TOKEN_TTL_SECONDS // 3600
    )
    await _send_notice(
        mailer,
        to=user["email"],
        subject=subject,
        body=body,
        user_id=user["id"],
        description="password reset",
    )


async def _send_password_changed_notice(mailer: Mailer, user: dict) -> None:
    """Alert the account that its password just changed (F9/S10)."""
    subject, body = render_password_changed_email()
    await _send_notice(
        mailer,
        to=user["email"],
        subject=subject,
        body=body,
        user_id=user["id"],
        description="password changed",
    )


async def _send_password_reset_notice(mailer: Mailer, user: dict) -> None:
    """Alert the account that its password was just reset (F9/S10)."""
    subject, body = render_password_reset_email()
    await _send_notice(
        mailer,
        to=user["email"],
        subject=subject,
        body=body,
        user_id=user["id"],
        description="password reset completed",
    )


async def _maybe_send_new_session_notice(
    store: SqliteStore,
    user: dict,
    mailer: Mailer,
    session: dict,
) -> None:
    """Alert the account when a login found another live session (F9/S10).

    This is the mail twin of the in-app notice: the notice arms on an older
    session the moment a newer one appears (D4/D9), and the same event is what
    this mail reports. At login the just-created session is the newest, so the
    in-app signal is equivalent to "the account already held another live
    session" -- ``list_auth_sessions`` is the listing that signal is derived
    from, and it filters expired rows exactly like ``pending_new_session_at``.
    The mail names the browser captured for the new session (truncated by the
    store), matching what the sessions list would show.
    """
    sessions = await store.list_auth_sessions(user["id"], session["token_hash"])
    if not any(not row["is_current"] for row in sessions):
        return
    subject, body = render_new_session_email(user_agent=session["user_agent"])
    await _send_notice(
        mailer,
        to=user["email"],
        subject=subject,
        body=body,
        user_id=user["id"],
        description="new session",
    )


def _current_token_hash(request: Request) -> str:
    """Hash of the caller's own session cookie.

    ``current_user`` already rejected a request without a valid cookie, so the
    cookie is present here. Hashing it is what lets the store flag and protect
    the caller's own row without ever handling a raw token twice.
    """
    return hash_token(request.cookies["session_id"])


def _client_ip(request: Request) -> str:
    """The caller's source address, used only to key the limiter (S2).

    It is never written anywhere in clear: it goes into the limiter key, and
    the persisted counter stores only ``hash_attempt_key`` of that key (S4),
    keeping the app's promise of storing no IP.
    """
    return request.client.host if request.client else "unknown"


def _email_attempt_key(scope: str, email: str) -> str:
    """The account-scoped key for one email (F4).

    Built here once so the login route clears exactly the key that
    ``_attempt_keys`` recorded; a second format string would be a silent
    mismatch waiting to happen.
    """
    return f"{scope}:email:{normalize_email(email)}"


def _attempt_keys(scope: str, request: Request, email: str) -> list[str]:
    """The two keys one attempt is counted against (S2).

    The IP brakes an attacker from a single origin; the email brakes an attack
    aimed at one account. Both must be free for the attempt to go through.
    """
    return [
        f"{scope}:ip:{_client_ip(request)}",
        _email_attempt_key(scope, email),
    ]


def _ip_attempt_key(scope: str, request: Request) -> str:
    """The single origin-scoped key for a token-redemption endpoint (F9/S5).

    ``verify-email`` and ``reset-password`` carry no address to key an account
    brake on: their only input is the token, and the token IS the secret being
    tried. Keying on it would give every attempt a distinct key and brake
    nothing, so the source address is the one stable brake those routes have.
    """
    return f"{scope}:ip:{_client_ip(request)}"


def _attempt_scope(key: str) -> str:
    """The scope of a limiter key, for logs (F2).

    The scopes in use today are ``login``, ``register``, ``resend``, ``forgot``,
    ``verify`` and ``reset``.
    """
    return key.split(":", 1)[0]


async def _enforce_attempt_limit(
    limiter: PersistentAttemptLimiter, keys: list[str]
) -> None:
    """Refuse with 429 while any key is over its limit (S3/S4)."""
    for key in keys:
        retry_after = await limiter.retry_after(key)
        if retry_after is not None:
            # A log is storage, so never write the email or the IP (F2): the
            # scope and the wait are all an operator needs.
            logger.warning(
                "Auth attempt limit refused: scope=%s retry_after=%s",
                _attempt_scope(key),
                retry_after,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts, try again later",
                headers={"Retry-After": str(retry_after)},
            )


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.post(
    "/register",
    status_code=200,
    dependencies=[Depends(_require_hosted_mode)],
)
async def register(
    body: RegisterRequest,
    request: Request,
    store: SqliteStore = Depends(get_store),
    mailer: Mailer = Depends(get_mailer),
):
    """Register a new user.

    On success: creates the user row, sends the verification email, and
    returns the user payload. It deliberately does NOT open a session or set a
    cookie (D4/S3): the hard gate is that an account is not usable until its
    address is proven, so registration cannot be a way around login. The person
    proves the address through the mailed link, then logs in.

    On duplicate email: returns 409 Conflict.
    On invalid data: returns 422, including a missing or stale terms of use
    acceptance.
    Outside hosted mode: returns 403 with "Email flows are only available in
    hosted mode", before any of the above -- local mode has no mail, and the
    frontend hiding the signup screen is the UX, not the enforcement (D2/S2).
    """
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    # The email becomes the login identity, so its shape is checked before the
    # account exists (S5): an address nobody could log into is refused here, not
    # discovered later. The browser's ``type="email"`` is convenience, not a
    # defense.
    email = normalize_email(body.email)
    if not is_valid_email(email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid email address",
        )

    # The terms check sits with the other body checks and before the attempt
    # brake (S1): a request that is going to be refused must not spend one of
    # the account's attempts, and must not pay for a password hash either. A
    # stale version gets its own answer (D5): the person accepted a text that
    # is no longer in force, which is not the same as not accepting at all.
    if body.terms_version != TERMS_VERSION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Terms of use version has changed"
                if body.terms_version
                else "Terms of use must be accepted"
            ),
        )

    # Every register call counts, not just the failed ones: there is no
    # credential to fail here, and account creation is the abuse (S1).
    keys = _attempt_keys("register", request, email)
    limiter = PersistentAttemptLimiter(store)
    await _enforce_attempt_limit(limiter, keys)
    for key in keys:
        await limiter.record(key)

    # The optional name shares the profile's normalization and ceiling (D4):
    # trimmed, inner whitespace collapsed, blank -> None. It is validated here,
    # before the attempt brake, so a malformed name does not spend an attempt
    # (the same rule as the email shape above).
    name = normalize_display_name(body.name) if body.name else None
    if name is not None and len(name) > MAX_DISPLAY_NAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Name must be at most {MAX_DISPLAY_NAME_LENGTH} characters",
        )

    pw_hash = hash_password(body.password)
    try:
        user = await store.create_user(
            email, pw_hash, name=name, terms_version=body.terms_version
        )
    except DuplicateError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    await _issue_and_send_verification(store, user, mailer)
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user.get("name"),
        pending_deletion_at=user.get("pending_deletion_at"),
    )


@router.post("/login", status_code=200)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    mailer: Mailer = Depends(get_mailer),
):
    """Log in with email and password.

    On success: verifies bcrypt hash, mints session, sets cookie, returns user.

    On failure: returns consistent 401 (same response for unknown email
    and wrong password).
    On too many failed attempts: returns 429.
    """
    keys = _attempt_keys("login", request, body.email)
    limiter = PersistentAttemptLimiter(store)
    await _enforce_attempt_limit(limiter, keys)

    user = await store.get_user_by_email(body.email)
    if not verify_credentials(
        body.password, user["password_hash"] if user else None
    ):
        for key in keys:
            await limiter.record(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Hard gate (S3/D5): correct credentials are not enough while the address
    # is unproven. Nothing is minted and no cookie is set, so the caller cannot
    # acquire a session through login either. This is not enumeration: it is
    # only reachable after the password checked out, and whoever knows the
    # password already knows the account exists. The attempt brake is NOT
    # cleared here -- only a fully successful login clears it.
    if user["email_verified_at"] is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified",
        )

    # A real sign-in clears the brake on the account, not on the shared origin
    # (F4/S3): the person proved they own this account, so its failures were
    # mistyped passwords -- but one valid account must not let an attacker reset
    # the IP brake at will. The IP key survives a successful login.
    await limiter.clear(_email_attempt_key("login", body.email))

    _raw_token, cookie, session = await _mint_session(
        store, user["id"], request.headers.get("user-agent")
    )
    response.headers["Set-Cookie"] = cookie
    await _maybe_send_new_session_notice(store, user, mailer, session)
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user.get("name"),
        pending_deletion_at=user.get("pending_deletion_at"),
    )


@router.post("/local-profile", status_code=201)
async def create_local_profile(
    body: LocalProfileRequest,
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
):
    """Create the machine's local profile, or open it, and start a session (F1/T2b, L10).

    Only reachable in local mode (D2): in hosted mode the route is a backstop
    that answers 403. The frontend hides the screen, but hiding existence is
    not access control, so a direct call is refused too -- 403 rather than 404
    says "not here", not "never existed".

    Unlike register, this route DOES open a session (D5): a local profile has
    no address to prove, so there is no gate to hold it behind, and a first
    boot that created a profile nobody could enter would be a dead end.

    Get-or-create (L10): the local lock is optional (D4), so when it is OFF the
    app must simply open -- a profile with no password plus an 8h session expiry
    would otherwise trap the analyst out of their own install. The first call
    creates the profile and answers 201, requiring a name (D5); every later
    call opens the existing profile and answers 200, ignoring any ``name`` in
    the body so a boot never renames. "At most one local profile" is enforced
    by the store's partial unique index (0015): if two first boots race, the
    loser re-reads the winner and opens its session instead of a 409.
    """
    if get_mode() != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local profile is only available in local mode",
        )

    user = await store.get_local_user()
    if user is not None:
        # The lock, once on, is never bypassed here (T4/D4): a boot must ask
        # for the password (``/local-profile/open``) instead of opening a
        # locked profile silently.
        if user["password_hash"] is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This profile is locked",
            )
        # Opening: an existing profile is not renamed by a boot (L10), so any
        # name in the body is deliberately ignored and never validated.
        response.status_code = status.HTTP_200_OK
    else:
        name = normalize_display_name(body.name) if body.name else None
        if not name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Name is required",
            )
        if len(name) > MAX_DISPLAY_NAME_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Name must be at most {MAX_DISPLAY_NAME_LENGTH} characters",
            )

        try:
            user = await store.create_local_user(name)
        except DuplicateError:
            # A concurrent first boot won the race (L10). Re-read its row and
            # open that profile's session -- exactly what this call wanted --
            # rather than surfacing a 409.
            user = await store.get_local_user()
            if user is None:
                # The winner's row vanished between our failed insert and this
                # read, so there is no profile to open and no session to mint.
                # This cannot happen while the partial index holds; treat it as
                # the server error it is instead of inventing an identity.
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Local profile could not be created",
                )
            response.status_code = status.HTTP_200_OK

    _raw_token, cookie, _session = await _mint_session(
        store, user["id"], request.headers.get("user-agent")
    )
    response.headers["Set-Cookie"] = cookie
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user.get("name"),
        pending_deletion_at=user.get("pending_deletion_at"),
    )


@router.get("/local-profile", status_code=200)
async def get_local_profile_status(
    store: SqliteStore = Depends(get_store),
) -> LocalProfileStatus:
    """Report the machine's identity state before any session (F1/T2b, L10; T3).

    Answers whether a local profile exists and whether the database already
    holds email accounts. Only reachable in local mode (D2): outside it the
    route is the same 403 backstop as the POST. Unauthenticated on purpose --
    the frontend needs this BEFORE it holds any session, to choose between
    showing the first-boot screen, opening the existing profile silently, and
    sending an install that already has accounts to its email login (D3). The
    mode is a deployment property, so this signal lives on the auth surface,
    not in ``/api/app-config``.
    """
    if get_mode() != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local profile is only available in local mode",
        )

    local = await store.get_local_user()
    locked = local is not None and local["password_hash"] is not None
    return LocalProfileStatus(
        exists=local is not None,
        hosted_accounts=await store.has_hosted_accounts(),
        locked=locked,
        # A locked profile has answered the step by definition (the lock IS the
        # answer), including a pre-migration row whose flag kept the default.
        lock_step_pending=(
            local is not None and not locked and not local["lock_step_answered"]
        ),
    )


@router.post("/local-profile/lock", status_code=200)
async def lock_local_profile(
    body: LocalLockRequest,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
) -> LocalRescueKeyResponse:
    """Turn the optional local lock on and hand back a one-time rescue key (F1/T4, D4).

    Requires the caller's own session (``current_user``): turning the lock on is
    an act on a profile the caller is already inside. Only the machine's local
    profile can be locked -- a hosted account behind this session answers 404,
    the same as an id that is not there. A profile that already has a password
    is refused with 409 rather than overwritten, so a second lock cannot silently
    invalidate the rescue key shown the first time.

    On success the password is hashed with bcrypt, a fresh rescue key is minted
    with ``generate_raw_token()``, only its SHA-256 hash is stored, and the RAW
    key is returned exactly once (D4). It is never persisted and never appears
    in a later read: forgetting both the password and the raw key means starting
    over.

    This is NOT a login route: ``login`` is by email and a local profile has no
    email (`L9`). Opening a locked profile is ``POST /local-profile/open``.

    Outside local mode the mode gate answers 403 before any row is touched.
    """
    if get_mode() != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local profile is only available in local mode",
        )

    # ``current_user`` reads through ``get_user_by_id``, whose column list
    # deliberately omits ``kind`` (only ``get_local_user`` exposes the rescue
    # column). Comparing ids against the single local row is what tells a local
    # session from a hosted one without widening that helper.
    local = await store.get_local_user()
    if local is None or local["id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local profile not found",
        )

    if local["password_hash"] is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This profile is already locked",
        )

    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    rescue_key = generate_raw_token()
    await store.set_local_lock(
        local["id"], hash_password(body.password), hash_token(rescue_key)
    )
    return LocalRescueKeyResponse(rescue_key=rescue_key)


@router.post("/local-profile/lock-step/decline", status_code=204)
async def decline_local_lock_step(
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Record that the analyst declined the optional lock step (F1/T3, D1).

    The step is mandatory on the onboarding path but the lock itself stays
    optional (D4): the screen offers it, and whoever does not want it must say
    "not now" explicitly. Declining is an answer, so this route persists the
    flag and the step does not come back. It does NOT touch the password: the
    profile stays without a lock, exactly as D4 allows.

    Requires the caller's own session (``current_user``), like the lock route:
    answering the step is an act on the profile the caller is already inside.
    Only the machine's local profile can be answered -- a hosted session behind
    this route answers 404, the same as an id that is not there. The route is
    idempotent: answering "not now" twice leaves the same persisted answer.

    Turning the lock on is the other answer and is handled by
    ``POST /local-profile/lock``; both routes write the same flag.

    Outside local mode the mode gate answers 403 before any row is touched.
    """
    if get_mode() != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local profile is only available in local mode",
        )

    local = await store.get_local_user()
    if local is None or local["id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local profile not found",
        )

    await store.mark_local_lock_step_answered(local["id"])
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post("/local-profile/open", status_code=200)
async def open_local_profile(
    body: LocalOpenRequest,
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
):
    """Open a locked local profile and start a session (F1/T4, D4).

    Unauthenticated on purpose: this route is the way back in when the 8h
    session expired, so it cannot require what it is trying to produce. It is
    the reason the get-or-create route was left unauthenticated (L10): the
    first boot creates the profile, and this route opens it once the lock is on.

    A wrong password and a profile that never had a lock answer the same 401
    "Invalid password": there is no lock to open with a password, and saying so
    would only help guessing. On success it mints a session exactly like
    ``login`` does (cookie + ``Set-Cookie``) and returns the ``UserResponse``.

    This is NOT the email ``login``: ``login`` is by email, and a local profile
    has no email (`L9`), so there is deliberately no local path through it.

    Outside local mode the mode gate answers 403 before any lookup.
    """
    if get_mode() != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local profile is only available in local mode",
        )

    user = await store.get_local_user()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local profile not found",
        )

    password_hash = user["password_hash"]
    if password_hash is None or not verify_password(body.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
        )

    _raw_token, cookie, _session = await _mint_session(
        store, user["id"], request.headers.get("user-agent")
    )
    response.headers["Set-Cookie"] = cookie
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user.get("name"),
        pending_deletion_at=user.get("pending_deletion_at"),
    )


@router.post("/local-profile/rescue", status_code=200)
async def rescue_local_profile(
    body: LocalRescueRequest,
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
) -> LocalRescueKeyResponse:
    """Recover a locked local profile with its one-time rescue key (F1/T4, D4).

    Unauthenticated like ``open``: whoever forgot the password proves ownership
    with the raw rescue key shown when they locked the profile.

    The stored hash is compared in constant time; a missing stored hash (the
    lock was never turned on, or the key was already rotated) and a wrong key
    answer the same 401 "Invalid rescue key", so the route cannot confirm which
    one it is. On success the new password is hashed, the rescue key is ROTATED
    -- the key just used stops working, deliberately (D4) -- and a session is
    minted exactly like ``login``, returning the NEW raw key. It is the same
    one-time reveal as the lock route: stored hashed, shown once.

    This is NOT the email ``login``: a local profile has no email (`L9`).

    Outside local mode the mode gate answers 403 before any lookup.
    """
    if get_mode() != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local profile is only available in local mode",
        )

    user = await store.get_local_user()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Local profile not found",
        )

    stored_hash = user.get("local_rescue_hash")
    if not stored_hash or not hmac.compare_digest(
        hash_token(body.rescue_key), stored_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid rescue key",
        )

    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    new_rescue_key = generate_raw_token()
    await store.set_local_password(user["id"], hash_password(body.new_password))
    await store.set_local_rescue_hash(user["id"], hash_token(new_rescue_key))

    _raw_token, cookie, _session = await _mint_session(
        store, user["id"], request.headers.get("user-agent")
    )
    response.headers["Set-Cookie"] = cookie
    return LocalRescueKeyResponse(rescue_key=new_rescue_key)


@router.post(
    "/verify-email",
    status_code=204,
    dependencies=[Depends(_require_hosted_mode)],
)
async def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    store: SqliteStore = Depends(get_store),
):
    """Prove the address behind a mailed verification token (D10).

    The token is redeemed atomically exactly once (D2/D12): an unknown, expired
    or already-used token is indistinguishable and answers the same 400. The
    proof must belong to the address we mailed (defensive): if the account's
    email changed since the token was issued, the token is refused even though
    it was genuine. On success the address is stamped verified and every
    sibling verification token is dropped. Verifying does NOT log the person in
    (D10): the screen confirms and sends them to login.

    The brake runs first (F9/S5), keyed on the source address: a flood of bad
    tokens is refused before it costs a database lookup.

    Outside hosted mode the mode guard answers 403 before any of that: local
    mode has no mailed links to redeem, and the frontend hiding the screen is
    the UX, not the enforcement (D2/S2).
    """
    brake_key = _ip_attempt_key("verify", request)
    limiter = PersistentAttemptLimiter(store)
    await _enforce_attempt_limit(limiter, [brake_key])
    await limiter.record(brake_key)

    token = await store.consume_auth_token(
        hash_token(body.token), TOKEN_PURPOSE_VERIFY_EMAIL
    )
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

    user = await store.get_user_by_id(token["user_id"])
    if user is None or token["email"] != user["email"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

    await store.mark_email_verified(user["id"])
    await store.invalidate_user_tokens(user["id"], TOKEN_PURPOSE_VERIFY_EMAIL)
    return None


@router.post(
    "/resend-verification",
    status_code=202,
    dependencies=[Depends(_require_hosted_mode)],
)
async def resend_verification(
    body: ResendVerificationRequest,
    request: Request,
    store: SqliteStore = Depends(get_store),
    mailer: Mailer = Depends(get_mailer),
):
    """Re-send the verification link, never confirming who exists (D6).

    Always answers 202, whether the address is unknown, already verified, or
    real and unverified (D6): a forked answer would turn this into an
    enumeration oracle. Only a real, unverified account gets a new token and a
    mail. Every attempt is counted against the IP and the email (S2) so the
    endpoint cannot be used to bomb a mailbox.

    Outside hosted mode the mode guard answers 403 before any brake is spent or
    any mail is sent: this route exists to mail a link, and local mode has no
    mailbox. The frontend hiding the link is the UX, not the enforcement
    (D2/S2) -- which is why this resend is guarded along with the four flows
    the finding named.
    """
    email = normalize_email(body.email)
    keys = _attempt_keys("resend", request, email)
    limiter = PersistentAttemptLimiter(store)
    await _enforce_attempt_limit(limiter, keys)
    for key in keys:
        await limiter.record(key)

    user = await store.get_user_by_email(email)
    if user is not None and user["email_verified_at"] is None:
        await _issue_and_send_verification(store, user, mailer)
    return None


@router.post(
    "/forgot-password",
    status_code=202,
    dependencies=[Depends(_require_hosted_mode)],
)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    store: SqliteStore = Depends(get_store),
    mailer: Mailer = Depends(get_mailer),
):
    """Start password recovery without confirming who exists (D6).

    Always answers 202 with an empty body, whether the address is unknown,
    verified, or real and unverified: a forked answer would turn this into an
    enumeration oracle. The email shape is deliberately NOT validated here --
    a 422 would leak which inputs the server considers real, and this route has
    no use for the address beyond looking it up. Only a real account gets a
    token and a mail. Every attempt is counted against the IP and the email
    (S2) so the endpoint cannot be used to bomb a mailbox.

    Outside hosted mode the mode guard answers 403 before any brake is spent or
    any mail is sent: recovery depends on a mailbox, which a local install does
    not have. The frontend hiding the link is the UX, not the enforcement
    (D2/S2).
    """
    email = normalize_email(body.email)
    keys = _attempt_keys("forgot", request, email)
    limiter = PersistentAttemptLimiter(store)
    await _enforce_attempt_limit(limiter, keys)
    for key in keys:
        await limiter.record(key)

    user = await store.get_user_by_email(email)
    if user is not None:
        await _issue_and_send_reset(store, user, mailer)
    return None


@router.post(
    "/reset-password",
    status_code=204,
    dependencies=[Depends(_require_hosted_mode)],
)
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    mailer: Mailer = Depends(get_mailer),
):
    """Set a new password from a mailed reset token (S4, D7, D8, D12).

    The brake runs first (F9/S5), keyed on the source address: a flood of bad
    tokens is refused before it costs a database lookup. The length check runs
    BEFORE the token is touched (D12-ish): a short password is a malformed
    request, not a redemption, so it must not burn the one-shot token and force
    the person to request another link. The token is
    then redeemed atomically exactly once; an unknown, expired, or already-used
    token answers the same 400. On success the password is replaced, the
    address is marked verified (D7 -- receiving the link at that mailbox proves
    the same thing as the verification link), every session of the user is
    closed (D8 -- a reset is the "my account was stolen" act, so no session may
    survive it), and any sibling reset token is dropped.

    Outside hosted mode the mode guard answers 403 before the brake and before
    the body is looked at: a reset link can only be redeemed here, so local mode
    -- which has no mail and therefore no link -- refuses the call. The frontend
    hiding the screen is the UX, not the enforcement (D2/S2).
    """
    brake_key = _ip_attempt_key("reset", request)
    limiter = PersistentAttemptLimiter(store)
    await _enforce_attempt_limit(limiter, [brake_key])
    await limiter.record(brake_key)

    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    token = await store.consume_auth_token(
        hash_token(body.token), TOKEN_PURPOSE_RESET_PASSWORD
    )
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

    await store.update_user_password(
        token["user_id"], hash_password(body.new_password)
    )
    await store.mark_email_verified(token["user_id"])
    await store.delete_all_auth_sessions(token["user_id"])
    await store.invalidate_user_tokens(
        token["user_id"], TOKEN_PURPOSE_RESET_PASSWORD
    )
    user = await store.get_user_by_id(token["user_id"])
    if user is not None:
        await _send_password_reset_notice(mailer, user)
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Log out the current user.

    Deletes the auth session row and clears the session cookie.
    """
    raw_token: str | None = request.cookies.get("session_id")
    if raw_token:
        token_hash = hash_token(raw_token)
        await store.delete_auth_session(token_hash)
    response.headers["Set-Cookie"] = build_expire_cookie_header(secure=_cookie_secure())
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.get("/me", status_code=200)
async def me(
    user: dict = Depends(current_user),
):
    """Return the current authenticated user."""
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user.get("name"),
        pending_deletion_at=user.get("pending_deletion_at"),
    )


@router.patch("/me", status_code=200)
async def update_me(
    body: NameUpdateRequest,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Change the authenticated user's display name (T1).

    No password gate: unlike ``/password`` or ``/account/delete``, this neither
    grants nor exposes anything (D5), so requiring a session is the whole
    authorization. The name is normalized first (D3) -- trimmed, inner
    whitespace collapsed -- and a blank result is a 422: NULL still means "never
    chose a name" for a new or legacy account, but the edit route refuses to
    create that state (D3 rewritten). Anything longer than
    ``MAX_DISPLAY_NAME_LENGTH`` after normalization is a 422 (D4) and leaves the
    stored name untouched. The user id always comes from the session, never from
    the body, so one user can never rename another (D5).
    """
    name = normalize_display_name(body.name)
    if name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Name cannot be empty",
        )

    if len(name) > MAX_DISPLAY_NAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Name must be at most {MAX_DISPLAY_NAME_LENGTH} characters",
        )

    await store.update_user_name(user["id"], name)
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=name,
        pending_deletion_at=user.get("pending_deletion_at"),
    )


@router.get("/sessions", status_code=200)
async def list_active_sessions(
    request: Request,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """List the caller's live sessions, most recent activity first.

    Only the caller's own sessions are listed, the row the request came from is
    flagged ``is_current`` (D3), and no token hash ever leaves the server.
    ``new_session_at`` carries the new-session notice when another live session
    was created and the user has not acknowledged it yet (D4/D9).
    """
    token_hash = _current_token_hash(request)
    sessions = await store.list_auth_sessions(user["id"], token_hash)
    return ActiveSessionsResponse(
        sessions=[
            AuthSessionResponse(
                id=row["id"],
                user_agent=row["user_agent"],
                created_at=row["created_at"],
                last_seen_at=row["last_seen_at"],
                is_current=row["is_current"],
            )
            for row in sessions
        ],
        new_session_at=await store.pending_new_session_at(user["id"], token_hash),
    )


@router.delete("/sessions", status_code=204)
async def close_other_sessions(
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Close every session of the user except the caller's own (D7).

    Idempotent: with no other sessions it is a no-op that still answers 204.
    """
    await store.delete_other_auth_sessions(user["id"], _current_token_hash(request))
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post("/sessions/notice-ack", status_code=204)
async def acknowledge_new_session_notice(
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Mark the new-session notice as seen (D4/D9).

    Idempotent, and never closes anything: acknowledging is not logging out.
    """
    await store.mark_sessions_notice_seen(user["id"], _current_token_hash(request))
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.delete("/sessions/{session_id}", status_code=204)
async def close_active_session(
    session_id: int,
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Close one session of the caller (D5/D7).

    A session owned by somebody else answers 404, exactly like an id that does
    not exist, so the route can never confirm that a foreign session id is
    real. The caller's own session is refused with 409 (D3): that is what
    ``POST /api/auth/logout`` is for.
    """
    target = await store.get_auth_session_by_id(user["id"], session_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if target["token_hash"] == _current_token_hash(request):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot close the current session",
        )

    await store.delete_auth_session_row(user["id"], session_id)
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post("/password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    store: SqliteStore = Depends(get_store),
    mailer: Mailer = Depends(get_mailer),
    user: dict = Depends(current_user),
):
    """Change the authenticated user's password.

    Verifies the current password, rejects a new password shorter than 8
    characters, re-hashes and persists the new one, then deletes every other
    session of the user while keeping the caller's session alive.

    On wrong current password: 401.
    On short new password: 422.
    On success: 204.
    """
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    await store.update_user_password(user["id"], hash_password(body.new_password))

    raw_token: str | None = request.cookies.get("session_id")
    if raw_token:
        await store.delete_other_auth_sessions(user["id"], hash_token(raw_token))

    await _send_password_changed_notice(mailer, user)

    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post("/account/delete", status_code=204)
async def request_account_deletion(
    body: DeleteAccountRequest,
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Schedule the authenticated account for deletion after a grace period.

    Authorization is the same as ``/password`` (S9/D4): the current password is
    verified first (401 on mismatch), and only then is the ``ELIMINAR``
    confirmation word validated (422). On success the purge deadline is written
    seven days out (D1), every session of the user is closed (D3), and the
    session cookie is cleared — the caller lands back on ``/login`` (S5). The
    account and its data are left untouched until the deadline passes (S3).
    """
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if body.confirmation != "ELIMINAR":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Type ELIMINAR to confirm",
        )

    await store.request_user_deletion(user["id"])
    await store.delete_all_auth_sessions(user["id"])
    response.headers["Set-Cookie"] = build_expire_cookie_header(secure=_cookie_secure())
    response.status_code = status.HTTP_204_NO_CONTENT
    return None


@router.post("/account/cancel-deletion", status_code=204)
async def cancel_account_deletion(
    response: Response,
    store: SqliteStore = Depends(get_store),
    user: dict = Depends(current_user),
):
    """Cancel a scheduled deletion so the account survives (S3).

    Idempotent: cancelling with no schedule is a no-op that still returns 204.
    """
    await store.cancel_user_deletion(user["id"])
    response.status_code = status.HTTP_204_NO_CONTENT
    return None