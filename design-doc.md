# Keycloak Groups and Roles Design for multi-tenant JupyterHub Access Control

In [2i2c-org/initiatives#13](https://github.com/2i2c-org/initiatives/issues/13) we want to map hub users into groups across multiple axes as follows: 

1. Hub access (can the user log in at all?) 
2. Resource-size access (what kind of compute resources a user has access to? small machines, large machines, GPUs?)
3. Admin access (does the user have admin access on the hub?)
4. Cost monitoring / billing attribution (which groups the users' usage costs should be attributed to?)
5. Social / org structure (which classrooms, research groups, project teams the user belongs to?)

There are many ways to design this. But ideally we want a solution that works well for multitenancy (one Keycloak realm can be used for multiple hubs and multiple organizations/teams), integrates well with how our current setup maps Keycloak groups/roles to JupyterHub groups and is easy enough for Keycloak admins to manage user access.

Here's my proposed solution on how to structure this in Keycloak.

## 1. Two orthogonal axes

The core idea of this proposed approach is that the 5 axes above can be condensed down to 2 orthogonal ones.

- **Who a user is:** in terms of social/organizational structure. This is the same across hubs, identity-shaped (the **tenant** axis).
- **What a user can do:** specific to a hub, capability-shaped (the **capability** axis).

These are managed independently by default. Each of the 5 use cases maps to either the tenant or the capability axis.

(PS: As a convenience, [tenant groups](#4b-tenant-groups) can optionally bundle [capability roles](#3b-capability-roles-client-scoped-what-a-user-can-do-on-a-particular-hub) so that org membership implies hub access. But the two axes remain conceptually distinct and the bundling is optional.)


---


## 2. One client per hub

A Keycloak realm (e.g. `veda-realm`) holds all users, groups, clients, and tenant roles. Each JupyterHub instance registers as a separate Keycloak client:

- `jupyterhub-staging`
- `jupyterhub-prod`

**Why one client per hub:** [Capability roles](#3b-capability-roles-client-scoped-what-a-user-can-do-on-a-particular-hub) are scoped to the client they're defined on. Putting each hub in its own client gives us per-hub capability assignments for free. For example, `gpu-user` on `jupyterhub-staging` and `gpu-user` on `jupyterhub-prod` are two different role assignments, and granting a user `gpu-user` role on the staging client is independent of the user's roles on the prod client. So a user with `gpu-user` role on staging doesn't automatically have that role on production since the roles are scoped to the separate clients.

**Token scoping is enforced by the protocol mapper:** Each client's `client-roles-claim` mapper ([keycloak-config.yaml:21-29](keycloak-config.yaml#L21-L29), [keycloak-config.yaml:55-63](keycloak-config.yaml#L55-L63)) is pinned to its own `clientId`. The token issued when a user logs into `jupyterhub-prod` only has [capability roles](#3b-capability-roles-client-scoped-what-a-user-can-do-on-a-particular-hub) associated with the `jupyterhub-prod` client, and not the ones associated with `jupyterhub-staging`.

---

## 3. Two axes of roles

### 3a. Tenant roles (realm-scoped): *who a user is in terms of social/organizational structure*

Tenant roles represent organizational identity. They are used mostly for cost tracking. But can also be used to grant access when access is granted **uniformly** based on social / organizational group membership (for example all users with role `tenant:veda/team-1` get access to the S3 bucket X).

**Realm-scoped:** because organizational identity is a real world concept and is not tied to any particular hub. A member of the VEDA team is on the VEDA team regardless of which hub they log into (or which other platform service they touch).

**Naming convention:** `tenant:<org>` and `tenant:<org>/<subgroup>`.

Defined at [keycloak-config.yaml:77-125](keycloak-config.yaml#L77-L125):

```
tenant:veda
tenant:veda/team-1
tenant:veda/team-2
tenant:disasters
tenant:classroom
tenant:classroom/students
tenant:classroom/TAs
tenant:classroom/instructors
tenant:research
tenant:research/project-alpha
tenant:research/project-beta
tenant:research/professors
```

**Composite hierarchy:** Every leaf tenant role composes its parent. For example `tenant:veda/team-1` includes `tenant:veda` as a composite ([keycloak-config.yaml:82-84](keycloak-config.yaml#L82-L84)):

```yaml
- name: tenant:veda/team-1
  composites:
    realm:
      - tenant:veda
```

A user assigned only the leaf role automatically carries the parent role too. Downstream cost attribution can roll up at any level without admins explicitly assigning both. As granting `tenant:veda/team-1` also grants `tenant:veda`, cost calculation can aggregate reporting at the `tenant:veda` level too.

### 3b. Capability roles (client-scoped): *what a user can do on a particular hub*

Capability roles control what a user can do inside a specific hub instance.

**Client-scoped:** so per-hub assignments don't leak across instances.

**Naming convention:** the client (`jupyterhub-staging` / `jupyterhub-maap-prod`) already provides the namespace, so we don't repeat the environment in the role name. This isn't limited to staging/production splits. It works just as well for completely separate hub instances.

Defined at [keycloak-config.yaml:131-175](keycloak-config.yaml#L131-L175):

| Role | Purpose |
|---|---|
| `basic-user` | Access to standard compute profiles |
| `power-user` | Access to large memory / high-CPU profiles |
| `gpu-user` | Access to GPU profiles |
| `admin` | JupyterHub admin panel access |

**Composite hierarchy.** `power-user` and `gpu-user` each compose `basic-user`; `admin` composes both ([keycloak-config.yaml:136-175](keycloak-config.yaml#L136-L175)). Concretely:

- A `power-user` is automatically also a `basic-user`.
- A `gpu-user` is automatically also a `basic-user`.
- An `admin` is automatically a `basic-user` and `power-user`.

This is what lets JupyterHub gate access with a single role for example:

```python
c.GenericOAuthenticator.allowed_groups = {"basic-user"}
```

"Must be at least basic" works because every higher-level capability composes `basic-user`. Admins never have to remember to assign multiple roles to one user.

---

## 4. Groups: the admin-facing knob for managing user access

Groups are how admins actually manage user access. There are two types of groups:

### 4a. Capability groups

**Naming Convention**: `/JupyterHub/<Env>/<Capability>` grants the matching client-scoped capability role on that environment's client ([keycloak-config.yaml:180-217](keycloak-config.yaml#L180-L217)).

```
/JupyterHub/Staging/Basic Users     : jupyterhub-staging:basic-user
/JupyterHub/Staging/Power Users     : jupyterhub-staging:power-user
/JupyterHub/Staging/GPU Users       : jupyterhub-staging:gpu-user
/JupyterHub/Staging/Admins          : jupyterhub-staging:admin

/JupyterHub/Prod/Basic Users        : jupyterhub-prod:basic-user
/JupyterHub/Prod/Power Users        : jupyterhub-prod:power-user
/JupyterHub/Prod/GPU Users          : jupyterhub-prod:gpu-user
/JupyterHub/Prod/Admins             : jupyterhub-prod:admin
```

Membership in a staging group has no effect on prod and vice versa. To give a user GPU access in staging but not prod, we add them to `/JupyterHub/Staging/GPU Users` only.

### 4b. Tenant groups

**Naming Convention:** `/Tenants/<org>/...` grant the matching realm-scoped tenant role ([keycloak-config.yaml:222-299](keycloak-config.yaml#L222-L299)):

```
/Tenants/veda                       : tenant:veda + jupyterhub-staging:basic-user
/Tenants/veda/team-1                : tenant:veda/team-1 (+ tenant:veda) [inherits basic-user from parent]
/Tenants/veda/team-2                : tenant:veda/team-2 (+ tenant:veda) + jupyterhub-staging:power-user
/Tenants/disasters                  : tenant:disasters + jupyterhub-staging:power-user + jupyterhub-staging:gpu-user
/Tenants/classroom                  : tenant:classroom + jupyterhub-staging:basic-user
/Tenants/classroom/students         : tenant:classroom/students (+ tenant:classroom) [inherits basic-user from parent]
/Tenants/classroom/TAs              : tenant:classroom/TAs (+ tenant:classroom) + jupyterhub-staging:power-user
/Tenants/classroom/instructors      : tenant:classroom/instructors (+ tenant:classroom) + jupyterhub-staging:admin
/Tenants/research                   : tenant:research + jupyterhub-staging:basic-user
/Tenants/research/project-alpha     : tenant:research/project-alpha (+ tenant:research) + jupyterhub-staging:power-user
/Tenants/research/project-beta      : tenant:research/project-beta (+ tenant:research) + jupyterhub-staging:gpu-user
/Tenants/research/professors        : tenant:research/professors (+ tenant:research) + jupyterhub-staging:admin
```

Tenant groups primarily grant tenant roles for cost attribution. They can **optionally bundle capability roles** at any level in the hierarchy:

- **Parent groups** (`/Tenants/veda`, `/Tenants/classroom`, `/Tenants/research`) bundle the baseline capability (`basic-user`). Keycloak inherits parent group roles down to subgroup members, so every member of any subgroup automatically has at least `basic-user`.
- **Subgroups** bundle the override capability for their specific role (e.g. `/Tenants/classroom/TAs` adds `power-user`, `/Tenants/classroom/instructors` adds `admin`).

As a result, adding a user to a single tenant group is sufficient in almost all cases. For individual exceptions (e.g. a `team-1` member who also needs GPU access), an admin adds them to the appropriate `/JupyterHub/<Hub>/*` capability group on top.

### 4c. Default group

All new users are placed in the `/No Access` group automatically ([keycloak-config.yaml:220](keycloak-config.yaml#L220), [keycloak-config.yaml:300-301](keycloak-config.yaml#L300-L301)). This group grants no roles. Users can authenticate (proving identity) but cannot launch any server until an admin explicitly adds them to a ["capability" group](#4a-capability-groups).

---

## 5. Examples of mapping social structures to tenant groups

These examples try to answer "I have a classroom / research lab / multi-tenant org with subgroups. How do I map that onto groups?"

We model the social structure as tenant groups and bundle the appropriate capability roles into the hierarchy, so a single group assignment per user is sufficient for most cases. Some examples: [keycloak-config.yaml:303-441](keycloak-config.yaml#L303-L441):

### 5a. Classroom

| Social role | Tenant group | Tenant role granted (incl. composite) | Capability roles and source |
|---|---|---|---|
| Student | `/Tenants/classroom/students` | `tenant:classroom/students` (+ `tenant:classroom`) | `basic-user` inherited from `/Tenants/classroom` parent |
| TA | `/Tenants/classroom/TAs` | `tenant:classroom/TAs` (+ `tenant:classroom`) | `power-user` bundled in group (+ `basic-user` inherited from parent) |
| Instructor | `/Tenants/classroom/instructors` | `tenant:classroom/instructors` (+ `tenant:classroom`) | `admin` bundled in group (+ `power-user` + `basic-user` via composite) |

All three have `tenant:classroom` for cost attribution. Each user only needs a single group assignment; capabilities come from the group hierarchy.

### 5b. Research lab

| Social role | Tenant group | Tenant role granted (incl. composite) | Capability roles and source |
|---|---|---|---|
| Project Alpha researcher | `/Tenants/research/project-alpha` | `tenant:research/project-alpha` (+ `tenant:research`) | `power-user` bundled in group (+ `basic-user` inherited from parent) |
| Project Beta researcher | `/Tenants/research/project-beta` | `tenant:research/project-beta` (+ `tenant:research`) | `gpu-user` bundled in group (+ `basic-user` inherited from parent) |
| Professor | `/Tenants/research/professors` | `tenant:research/professors` (+ `tenant:research`) | `admin` bundled in group (+ `power-user` + `basic-user` via composite) |

Different projects roll up to `tenant:research`. Capabilities differ per subgroup; a single group assignment per user is sufficient.

### 5c. Multi-team org

| Social role | Tenant group | Tenant role granted (incl. composite) | Capability roles and source |
|---|---|---|---|
| Team 1 member | `/Tenants/veda/team-1` | `tenant:veda/team-1` (+ `tenant:veda`) | `basic-user` inherited from `/Tenants/veda` parent |
| Team 2 member | `/Tenants/veda/team-2` | `tenant:veda/team-2` (+ `tenant:veda`) | `power-user` bundled in group (+ `basic-user` inherited from parent) |

Both teams roll up to `tenant:veda`. Cost reports can be broken down by team or aggregated to the whole org. Team 2 members get `power-user` because that's encoded in their subgroup; team 1 members get the org-level default of `basic-user`.

### The general recipe

1. Sketch the community's social structure as a tree (org > subgroup > leaf).
2. Mirror that tree as `/Tenants/...` groups; each leaf gets a `tenant:<org>/<leaf>` role that composes its parent.
3. Bundle capability roles into the group hierarchy at the right level: put the baseline capability on the parent group (every member of the org gets it via inheritance) and put role-specific overrides on subgroups. A single group assignment per user is then sufficient for most cases.
4. For individual exceptions that don't fit the group's bundled capability (e.g. one team-1 member who also needs GPU access), assign an additional `/JupyterHub/<Env>/<Capability>` group on top.
5. A user can sit in any number of tenant groups (e.g. an instructor who is also part of a research project); each group contributes its bundled capability independently.

---

## 6. End to end user flow

Let's go through a single user's flow from admin action to JupyterHub login.

**Setup.** Admin adds user to one group:
- `/Tenants/veda/team-1`

`/Tenants/veda/team-1` inherits `jupyterhub-staging:basic-user` from the `/Tenants/veda` parent group, so no separate capability group assignment is needed.

**Login.** User authenticates against `jupyterhub-staging` via Keycloak.

**Token contents.**
- `roles` claim emitted by the client-roles mapper at [keycloak-config.yaml:21-29](keycloak-config.yaml#L21-L29) (per-client; this one is pinned to `jupyterhub-staging`):
  ```
  ["basic-user"]
  ```
- `groups` claim emitted by the groups mapper at [keycloak-config.yaml:31-39](keycloak-config.yaml#L31-L39) with `full.path: "true"`:
  ```
  ["/Tenants/veda/team-1"]
  ```

**JupyterHub side.** The authenticator at [jupyterhub_config.py:35-39](jupyterhub_config.py#L35-L39) ingests `oauth_user.roles` as JupyterHub group membership:

```python
c.GenericOAuthenticator.manage_groups = True
c.GenericOAuthenticator.auth_state_groups_key = "oauth_user.roles"
c.GenericOAuthenticator.allowed_groups = {"basic-user"}
c.GenericOAuthenticator.admin_groups = {"admin"}
```

The user has `basic-user` in their roles, so `allowed_groups = {"basic-user"}` admits them.

The profile filter at [jupyterhub_config.py:58-118](jupyterhub_config.py#L58-L118) then walks the profile list and only exposes profiles whose `allowed_groups` intersect the user's roles. Since this user is only `basic-user`, GPU profiles and large-memory profiles gated on `power-user` are filtered out; only standard profiles are shown.

---

## 7. Naming summary

| Concept | Pattern | Example |
|---|---|---|
| Client | `jupyterhub-<env>` or `jupyterhub-<hubname>` | `jupyterhub-staging` or `jupyterhub-maap-staging` |
| Capability role | `<capability name>` (client-scoped) | `gpu-user` |
| Tenant role | `tenant:<org>/<subgroup>` (realm-scoped) | `tenant:veda/team-1` |
| Capability group | `/JupyterHub/<Env>/<Capability Name>` | `/JupyterHub/Prod/GPU Users` |
| Tenant group | `/Tenants/<org>/...` | `/Tenants/veda/team-1` |
| Default group | `/No Access` | — |

---

## 8. Why roles + groups, and not scopes?

JupyterHub's `GenericOAuthenticator` exposes two access knobs that look similar but behave differently:

- `allowed_groups`: a user is admitted if they're in *any* listed group. This is the right semantics for overlapping memberships — a user can belong to many groups for many reasons, and any matching one is enough.
- `allowed_scopes`: a user must hold *all* listed scopes. This is awkward to combine with overlapping memberships and forces scopes to be very fine-grained, which becomes painful to manage as the set of capabilities grows.

There's also a duplication concern. The list of fine-grained capabilities (like the available machine profiles) already lives on the JupyterHub side. If we gated access on scopes, we'd have to mirror that list as scopes on the Keycloak side and keep them in sync. Hence we do not rely on scopes, and the JupyterHub configuration decides a user's access and capabilities based on `allowed_groups` solely.

We also rely on a specific OAuthenticator feature:

```python
c.GenericOAuthenticator.manage_groups = True
c.GenericOAuthenticator.auth_state_groups_key = "oauth_user.roles"
```

This ingests **Keycloak roles as JupyterHub groups**. So we define the list of user group memberships and capabilities as roles and use groups purely as the admin-facing knobs to assign underlying roles to particular users.

## In Summary

Namespaced, nested **roles** carry a user's organizational identity and capabilities (`tenant:veda/team-1`, `gpu-user`). **Groups** are the admin-facing knob for user access management where admins assign users to groups, groups grant the underlying roles. JupyterHub sees the resolved roles as group memberships and applies `allowed_groups` checks against them for access control and cost attribution.



