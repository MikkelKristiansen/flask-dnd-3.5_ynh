#!/usr/bin/env python3
"""
Lav scrypt-hashes til de to kodeord i auth.py (spiller og DM).

Kør den, tast de to kodeord, og skriv de tre udskrevne linjer i
/etc/flask_dnd.env på apps-mk (chmod 600, ejet af root). Kodeordene læses med
getpass, så de hverken vises på skærmen eller ender i shell-historikken.

    .venv/bin/python scripts/lav-kodeord-hash.py

Hashen indeholder $-tegn, som systemd ville fortolke i en Environment=-linje i
selve unit-filen. Derfor env-filen: den læses literalt, og hemmelighederne
holdes samtidig ude af git.
"""
import getpass
import secrets
import sys

from werkzeug.security import generate_password_hash


def _spørg(navn):
    kode = getpass.getpass(f"{navn}-kodeord: ")
    if not kode:
        sys.exit(f"Tomt {navn}-kodeord — afbrudt.")
    if kode != getpass.getpass(f"{navn}-kodeord igen: "):
        sys.exit("De to indtastninger var ikke ens — afbrudt.")
    return generate_password_hash(kode)


def main():
    spiller = _spørg("Spiller")
    dm = _spørg("DM")
    print("\n# Ind i /etc/flask_dnd.env på apps-mk (chmod 600, ejer root):")
    print(f"DND_SECRET_KEY={secrets.token_urlsafe(32)}")
    print(f"DND_PLAYER_PASSWORD_HASH={spiller}")
    print(f"DND_DM_PASSWORD_HASH={dm}")
    print("\n# Skift ikke DND_SECRET_KEY bagefter — så bliver alle logget ud.")


if __name__ == "__main__":
    main()
