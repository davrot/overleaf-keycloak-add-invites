#!/usr/bin/env python3
"""
keycloak_user_stats.py

Computes two statistics over all users in a Keycloak realm:

  Statistic I  - Distribution over type of user:
                 A. eduPersonScopedAffiliation = student@uni-bremen.de
                 B. eduPersonScopedAffiliation = employee@uni-bremen.de
                 C. Email @marum.de
                 D. Email @awi.de
                 E. Email @<sub>.uni-bremen.de or @uni-bremen.de (split by subdomain)
                 F. External partners (anything else)

  Statistic II - For users under uni-bremen.de: department, taken from
                 eduPersonScopedAffiliation = member@<department>.uni-bremen.de

Reuses the same config.json / auth flow as add_user.py.
"""

import json
import sys
from collections import Counter
from requests.auth import HTTPBasicAuth
import requests  # type: ignore

CONFIG_PATH = "config.json"


def get_token(config):
    token_url = f"{config['keycloak_url']}/realms/master/protocol/openid-connect/token"
    token_data = {
        "grant_type": "password",
        "username": config["admin_username"],
        "password": config["admin_password"],
    }
    resp = requests.post(
        token_url,
        data=token_data,
        auth=HTTPBasicAuth(config["client_id"], config["client_secret"]),
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_all_users(config, access_token):
    # NOTE: target_realm defaults to "master" to match add_user.py's existing
    # behaviour. Set config["target_realm"] if your users live elsewhere.
    realm = config.get("target_realm", "master")
    users_url = f"{config['keycloak_url']}/admin/realms/{realm}/users"
    headers = {"Authorization": f"Bearer {access_token}"}

    all_users = []
    first = 0
    page_size = 100
    while True:
        params = {"first": first, "max": page_size, "briefRepresentation": False}
        resp = requests.get(users_url, headers=headers, params=params)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_users.extend(batch)
        if len(batch) < page_size:
            break
        first += page_size
    return all_users


def get_affiliations(user):
    """Return eduPersonScopedAffiliation values (lower-cased), case-insensitive key lookup."""
    attrs = user.get("attributes", {}) or {}
    for key, vals in attrs.items():
        if key.lower() == "edupersonscopedaffiliation":
            if isinstance(vals, list):
                return [str(v).lower() for v in vals]
            return [str(vals).lower()]
    return []


def classify_user(user, affiliations):
    """Statistic I classification. Priority: A/B (affiliation) > C/D (email) > E (subdomain) > F."""
    email = (user.get("email") or "").lower().strip()

    if any(a == "student@uni-bremen.de" for a in affiliations):
        return "A. student@uni-bremen.de"
    if any(a == "employee@uni-bremen.de" for a in affiliations):
        return "B. employee@uni-bremen.de"

    if not email:
        return "F. external / no email"

    if email.endswith("@marum.de"):
        return "C. @marum.de"
    if email.endswith("@awi.de"):
        return "D. @awi.de"

    if email.endswith("@uni-bremen.de"):
        return "E. @uni-bremen.de (no subdomain)"
    if email.endswith(".uni-bremen.de"):
        domain = email.split("@", 1)[1]
        sub = domain[: -len(".uni-bremen.de")]
        return f"E. @{sub}.uni-bremen.de"

    return "F. external partner"


def get_department(affiliations):
    """Statistic II: member@<department>.uni-bremen.de"""
    for a in affiliations:
        if a.startswith("member@") and a.endswith(".uni-bremen.de"):
            dept = a[len("member@") : -len(".uni-bremen.de")]
            if dept:
                return dept
    return None


def main():
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Could not find {CONFIG_PATH} in the current directory.", file=sys.stderr)
        sys.exit(1)

    print("Authenticating...")
    token = get_token(config)

    print("Fetching users (paginated)...")
    users = get_all_users(config, token)
    print(f"Total users fetched: {len(users)}\n")

    stat1 = Counter()
    stat2 = Counter()
    uni_bremen_total = 0

    for user in users:
        affiliations = get_affiliations(user)
        category = classify_user(user, affiliations)
        stat1[category] += 1

        email = (user.get("email") or "").lower().strip()
        if email.endswith("@uni-bremen.de") or email.endswith(".uni-bremen.de"):
            uni_bremen_total += 1
            dept = get_department(affiliations)
            if dept:
                stat2[dept] += 1
            else:
                stat2["(no member@<dept>.uni-bremen.de affiliation found)"] += 1

    print("=" * 60)
    print("Statistic I: User type distribution")
    print("=" * 60)
    for cat, count in sorted(stat1.items()):
        pct = 100 * count / len(users) if users else 0
        print(f"{cat:45s} {count:6d}  ({pct:5.1f}%)")

    print()
    print("=" * 60)
    print(f"Statistic II: Department distribution ({uni_bremen_total} @uni-bremen.de users)")
    print("=" * 60)
    for dept, count in sorted(stat2.items(), key=lambda kv: -kv[1]):
        pct = 100 * count / uni_bremen_total if uni_bremen_total else 0
        print(f"{dept:45s} {count:6d}  ({pct:5.1f}%)")


if __name__ == "__main__":
    main()
