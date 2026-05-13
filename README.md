# JupyterHub + Keycloak prototype

Prototype for wiring JupyterHub to Keycloak via OIDC, with role- and group-based access control.

## Setup

```sh
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in the values. `JUPYTERHUB_CRYPT_KEY` can be generated with `openssl rand -hex 32`.

## Run

```sh
./start.sh
```

This starts Keycloak via Docker Compose, waits for it to be healthy, imports the realm config, then launches JupyterHub.

JupyterHub: http://localhost:8000  
Keycloak admin: http://localhost:8080 (user: `admin`)

## Test users

All provisioned against the staging hub. Passwords are all `password`.

| Username | Access | Tenant |
|---|---|---|
| `basic-user-test` | basic profiles | veda/team-1 |
| `power-user-test` | large memory profiles | veda/team-2 |
| `gpu-user-test` | GPU profiles | disasters |
| `admin-test` | JupyterHub admin | — |
| `no-access-test` | can authenticate, no server profiles | — |
| `student-user` | basic profiles | classroom/students |
| `ta-user` | large memory profiles | classroom/TAs |
| `instructor-user` | JupyterHub admin | classroom/instructors |
| `project-alpha-researcher` | large memory profiles | research/project-alpha |
| `project-beta-researcher` | GPU profiles | research/project-beta |
| `professor-researcher` | JupyterHub admin | research/professors |
