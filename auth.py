"""Adgangskontrol: to delte kodeord — ét til spillerne, ét til DM'en.

Appen har ingen brugerkonti. Den skelner kun mellem to roller:

  spiller  — karakterarkene og alt andet uden for /dm
  dm       — alt, inklusive /dm (DM'en kan altså også se karaktererne)

Kodeordene ligger ikke i koden, men som scrypt-hashes i to miljøvariabler, der
sættes i systemd-unitten. Det holder hemmelighederne ude af git. Lav dem med
scripts/lav-kodeord-hash.py.

Hvilke variabler der er sat, afgør hvad der er låst:

  ingen af dem   → appen er helt åben (sådan kører den under pytest og lokalt)
  kun DM-hash    → karakterarkene er åbne, kun /dm kræver kodeord
  begge          → alt kræver kodeord

Det er med vilje, at "ingen hashes" betyder åben: ellers ville alle de
eksisterende tests skulle logge ind. Prisen er, at en glemt miljøvariabel i
produktion giver en åben app uden at brokke sig — derfor advarer init_app() i
loggen, når den starter uden kodeord.
"""
import os
from datetime import timedelta

from flask import (current_app, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash

SECRET_ENV = "DND_SECRET_KEY"
PLAYER_HASH_ENV = "DND_PLAYER_PASSWORD_HASH"
DM_HASH_ENV = "DND_DM_PASSWORD_HASH"

ROLE_KEY = "rolle"
DM = "dm"
PLAYER = "spiller"

# Spillerne sidder på tablets og skal ikke taste kodeord hver gang de åbner
# arket. Et halvt år er rigeligt til en kampagne.
SESSION_DAYS = 180


def _hashes():
    """(spiller-hash, dm-hash) fra miljøet — tom streng betyder "ikke sat"."""
    return os.environ.get(PLAYER_HASH_ENV, ""), os.environ.get(DM_HASH_ENV, "")


def is_enabled():
    """Er der overhovedet noget at logge ind på?"""
    player_hash, dm_hash = _hashes()
    return bool(player_hash or dm_hash)


def current_role():
    """Rollen for den nuværende session, eller None hvis ikke logget ind."""
    return session.get(ROLE_KEY)


def _tjek(hash_, password, navn):
    """check_password_hash, men en ødelagt hash bliver til en forståelig log-linje.

    En hash indeholder $-tegn. Bliver env-filen læst af noget der ekspanderer $
    (fx `source` i bash), ryger de midterste felter, og werkzeug kaster ValueError
    — hvilket uden det her ville blive en 500-fejl i stedet for et hint om, at
    kodeordet aldrig kan matche.
    """
    if not hash_:
        return False
    try:
        return check_password_hash(hash_, password)
    except ValueError:
        current_app.logger.error(
            "%s ser ikke ud som en gyldig hash — er $-tegnene overlevet vejen "
            "ind i miljøet? Lav den om med scripts/lav-kodeord-hash.py", navn)
        return False


def _role_for(password):
    """Hvilken rolle giver dette kodeord? DM-kodeordet vinder, hvis begge passer."""
    player_hash, dm_hash = _hashes()
    if _tjek(dm_hash, password, DM_HASH_ENV):
        return DM
    if _tjek(player_hash, password, PLAYER_HASH_ENV):
        return PLAYER
    return None


def _is_dm_path(path):
    """Hører stien til DM-området?

    Path-baseret frem for blueprint-baseret, fordi /dm/monster_token/<slug>
    ligger i app.py og ikke i dm_bp. Stien er den fælles nævner.
    """
    return path == "/dm" or path.startswith("/dm/")


def _wants_json(path):
    """Skal et afslag være JSON?

    JS'en kalder /api/... og /dm/api/.... Får den en HTML-login-side tilbage med
    status 200 (en redirect følges automatisk af fetch), fejler den et
    uforståeligt sted langt fra årsagen. En 401/403 med JSON er til at forstå.
    """
    return "/api/" in path or request.accept_mimetypes.best == "application/json"


def _safe_next(target):
    """Kun interne stier må bruges som next — ellers er login en open redirect.

    "//evil.dk" er en protokol-relativ URL, som browseren læser som et andet
    domæne, så den skal afvises på lige fod med "http://evil.dk".
    """
    if not target or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def init_app(app):
    """Sæt session-konfiguration op og hæng login-ruter og adgangstjek på appen."""
    secret = os.environ.get(SECRET_ENV, "")
    if is_enabled():
        if not secret:
            # En tilfældig nøgle ville give hver gunicorn-worker sin egen, så
            # brugeren blev logget ud hver gang han ramte den anden worker.
            raise RuntimeError(
                f"{SECRET_ENV} skal være sat, når der er kodeord på appen")
        app.secret_key = secret
    else:
        app.logger.warning(
            "Ingen kodeord sat (%s / %s) — appen er åben for alle",
            PLAYER_HASH_ENV, DM_HASH_ENV)
        app.secret_key = secret or "udvikling-uden-kodeord"

    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=SESSION_DAYS)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    # Lax gør, at cookien ikke sendes med POSTs fra fremmede sider — den
    # billigste CSRF-afbødning, når appen ikke har CSRF-tokens.
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    @app.route("/login", methods=["GET", "POST"])
    def auth_login():
        target = _safe_next(request.args.get("next")) or url_for("index")
        if not is_enabled():
            return redirect(target)
        fejl = None
        if request.method == "POST":
            rolle = _role_for(request.form.get("kodeord", ""))
            if rolle:
                session[ROLE_KEY] = rolle
                session.permanent = True
                return redirect(_safe_next(request.form.get("next")) or url_for("index"))
            fejl = "Forkert kodeord."
        return render_template("login.html", fejl=fejl, next=target,
                               rolle=current_role()), (200 if not fejl else 401)

    @app.route("/logout", methods=["GET", "POST"])
    def auth_logout():
        session.pop(ROLE_KEY, None)
        return redirect(url_for("auth_login"))

    @app.before_request
    def auth_gate():
        if request.endpoint in ("auth_login", "auth_logout", "static"):
            return None

        player_hash, dm_hash = _hashes()
        if not (player_hash or dm_hash):
            return None

        rolle = current_role()
        if rolle == DM:
            return None

        if _is_dm_path(request.path):
            if not dm_hash:          # kun spiller-delen er låst
                return None
            if _wants_json(request.path):
                return jsonify({"error": "kræver DM-kodeord"}), 403
            # Login-siden frem for en blank 403: en spiller, der lander her, skal
            # kunne skrive DM-kodeordet uden først at logge ud.
            return render_template(
                "login.html", fejl="Den side kræver DM-kodeordet.",
                next=request.full_path.rstrip("?"), rolle=rolle), 403

        if not player_hash or rolle == PLAYER:
            return None

        if _wants_json(request.path):
            return jsonify({"error": "log ind"}), 401
        return redirect(url_for("auth_login", next=request.full_path.rstrip("?")))

    @app.context_processor
    def _inject_role():
        """Så templates kan vise et logud-link, når der faktisk er logget ind."""
        return {"auth_rolle": current_role() if is_enabled() else None}
