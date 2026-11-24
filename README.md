# Overleaf Keycloak User Management (overleaf-keycloak-add-invites)

Helper toolkit for managing user accounts on an **Overleaf CE** deployment that uses
**Keycloak** (Keycloak at `sso.fb1.uni-bremen.de`) as its single sign-on provider.

It does three things:

1. **Provisioning** – creates Keycloak users for people who were invited to an
   Overleaf project (or for any email address) so they can log in via SSO.
2. **Administration** – promotes an Overleaf user to admin, lists registered
   users and pending invites, deletes Overleaf users.
3. **Reporting** – counts Overleaf/Keycloak users by department (parsed from
   `uni-bremen.de` e-mail domains / SAML affiliations).

## How it works

All Python scripts run **inside a small helper container** (`checkuser`, image
`check_user_image`) instead of on the host:

- `compose.yaml` starts the container on the **external `overleaf-network`**
  network (the same Docker network the Overleaf stack is on), so it can reach
  the Overleaf MongoDB directly at host name `overleafmongo:27017`.
- The container mounts `./data` (the Python scripts) at `/data` and the
  **Docker socket** (`/var/run/docker.sock`), which is needed by
  `delete_user.sh` to `docker exec` into the `overleafserver` container.
- The container's entrypoint is just `sleep infinity` – it is a persistent
  "execution sandbox" you run scripts in via `docker exec`.

The scripts split into two groups:

### Keycloak scripts (SSO side)

| File | Purpose |
|---|---|
| `data/add_user.py` | `add_keycloak_user(username)`: gets a Keycloak admin token (resource-owner password grant + basic auth with `client_id`/`client_secret`), checks whether the user already exists, and if not creates an enabled user with `UPDATE_PASSWORD` required. Returns `False` if it already exists or on any error. |
| `data/autoadd_invited.py` | Reads all pending project invites from Overleaf Mongo (`sharelatex.projectInvites`) and calls `add_keycloak_user()` for each email. This is the main "add invites" workflow. |
| `data/keycloak_stats.py` | Pulls all Keycloak users and prints stats: category counts (A–E based on e-mail domain / `eduPersonScopedAffiliation`, e.g. `student@uni-bremen.de`, `employee@uni-bremen.de`, `member@<dept>.uni-bremen.de`) and per-department counts. |

All Keycloak scripts read their configuration from `data/config.json` (run with
`/data` as the working directory, as the `exec_*.sh` wrappers do):

```json
{
    "keycloak_url": "…/sso",             // Keycloak base URL
    "keycloak_login": "…/login/oidc",    // (informational)
    "admin_username": "…",               // Keycloak admin (realm master)
    "admin_password": "…",
    "client_id": "…",
    "client_secret": "…"
}
```

> ⚠️ `config.json` contains **live credentials** (admin password + client
> secret) in plaintext. Keep it out of public repositories / VCS.

### Overleaf Mongo scripts (Overleaf side)

These talk to the Overleaf MongoDB (`overleafmongo:27017`, database `sharelatex`)
directly via `pymongo`:

| File | Purpose |
|---|---|
| `data/list_user.py` | Prints the e-mail of every user in the `sharelatex.users` collection. |
| `data/list_invited.py` | Prints the e-mail of every pending project invite in `sharelatex.projectInvites`. |
| `data/make_admin.py` | `make_admin.py <email>`: sets `isAdmin: true` on the matching user in `sharelatex.users` (CLI via `argh`). |
| `data/handle_image.py` | Prints the `imageName` field of every project in `sharelatex.projects` (diagnostic). |

## Repository layout

```
├── Dockerfile                 # python:3.14.3 + pymongo/requests/etc.; entrypoint = sleep infinity
├── compose.yaml               # checkuser service on external overleaf-network, mounts ./data and docker.sock
├── make_image.sh              # docker build (see below – note the network flag)
├── exec.sh                    # interactive shell in the checkuser container
├── exec_autoadd_invited.sh    # run data/autoadd_invited.py in the container
├── exec_list_user.sh          # list registered Overleaf users
├── exec_list_invited.sh       # list pending invites
├── exec_count_user.sh         # count registered users (list_user.py | wc -l)
├── exec_make_admin.sh         # promote a user: ./exec_make_admin.sh <email>
├── delete_user.sh             # delete an Overleaf user via overleafserver's delete-user.mjs
└── data/                      # the Python scripts + config.json (see tables above)
```

## Usage

Prerequisite: the Overleaf stack (containers `overleafserver`, `overleafmongo`)
is running on a Docker network named `overleaf-network` (declared as `external`
in `compose.yaml`).

```bash
# 1. Build the helper image
./make_image.sh          # docker build --network host -t check_user_image .

# 2. Put your Keycloak credentials in data/config.json, then start the container
docker compose up -d

# 3. (Optional) create Keycloak accounts for everyone currently invited
./exec_autoadd_invited.sh

# Day-to-day
./exec.sh                            # shell into the sandbox container
./exec_list_invited.sh               # who is invited?
./exec_list_user.sh                  # who is registered?
./exec_count_user.sh                 # how many users?
./exec_make_admin.sh user@example.de # promote a user
./delete_user.sh user@example.de     # delete an Overleaf user (runs overleafserver's
                                     # delete-user.mjs script inside overleafserver)

# Keycloak side (from inside exec.sh, or via docker exec)
python data/keycloak_stats.py        # user counts by category/department
```

All `exec_*.sh` wrappers are thin one-liners:
`docker exec [ -it ] checkuser bash -c "cd /data; python <script>"` – the
`-it` flag is unnecessary for the non-interactive ones and can be dropped.

## Notes & gotchas

- **Container names are hard-coded** (`checkuser`, `overleafserver`,
  `overleafmongo`) in the shell scripts and Python files – rename the
  deployment and you must update the scripts too.
- **`config.json` is not a secret-free file**: it holds the Keycloak admin
  password and client secret. It should not be committed to a public repo.
- `add_keycloak_user()` swallows errors and simply returns `False` (both for
  "user already exists" and for failures) – `autoadd_invited.py` prints one
  `… -- DONE` line per successfully created user, so silence ≠ failure,
  it means "already existed".
- `make_admin.py`'s final `client.close()` is unreachable (both branches
  `return` before it); harmless, but worth knowing.
- `delete_user.sh` targets `overleafserver` and expects
  `/overleaf/services/web/modules/server-ce-scripts/scripts/delete-user.mjs`
  to exist (standard in Overleaf CE).
- The `Dockerfile` installs a lot of packages that the current scripts don't
  use (Flask, gunicorn, recaptcha, BeautifulSoup, …) – the image is a generic
  Python sandbox, not a minimal one.
