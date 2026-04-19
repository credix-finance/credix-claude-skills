# `swarm.json` schema

The input file the swarm reads. Lives at the repo root.

## Top-level

| Field   | Type   | Required | Default  | Notes                                        |
|---------|--------|----------|----------|----------------------------------------------|
| `trunk` | string | no       | `"main"` | Branch to cut worktrees from and target PRs. |
| `tasks` | array  | yes      | —        | List of task objects (see below).            |

## Per task

| Field           | Type     | Required | Default    | Notes                                                            |
|-----------------|----------|----------|------------|------------------------------------------------------------------|
| `id`            | string   | yes      | —          | Stable identifier. Becomes the teammate name and branch suffix.  |
| `title`         | string   | yes      | —          | Used in the PR title (`"<id>: <title>"`).                        |
| `spec`          | string   | yes      | —          | Full refined description + acceptance criteria. Pasted verbatim into the spawn prompt. |
| `depends_on`    | string[] | yes      | —          | Empty `[]` if none. Explicit only; swarm does not infer.         |
| `scope_files`   | string[] | no       | `[]`       | Globs of files this task expects to touch. Used for overlap detection, not enforcement. |
| `requires_plan` | bool     | no       | `false`    | Teammate must submit a plan for lead approval before implementing. |
| `model`         | string   | no       | (inherit)  | Any model id your Claude Code harness accepts. Omit to inherit from the lead's user settings. If you must pin, prefer `claude-opus-4-7[1m]` for complex tasks. |

### `id` rules

- Must be unique within the file.
- Becomes part of the branch name (`swarm/<id>`) and the worktree path
  (`.swarm/worktrees/<id>/`). Use a slug-safe format: `[a-z0-9-]+`.
- Cannot contain `/` or whitespace.

### `depends_on` semantics

**`depends_on` means: don't spawn until the dep's PR is MERGED (not just
approved).** After a dep merges, the lead rebases the dependent worktree onto
the fresh trunk before spawning. Chained works (A → B → C). Parallel works (D
depends on A and B; D spawns once both are merged).

### `scope_files` semantics

`scope_files` is an advisory declaration. `plan.py` uses it to warn when two
tasks with no declared dependency between them look like they'll touch the
same files. It does **not** enforce file boundaries at runtime.

### `model`

Omit to inherit the model from the lead's user settings — the swarm does
not pick a model for you. Pin a `model` per task only when you specifically
need a different one for that task. For complex refactors, tricky debugging,
or performance-sensitive changes, pin `"claude-opus-4-7[1m]"` (Opus 4.7 with
1M context).

## What the skill refuses

- **Cycles** in `depends_on`. `plan.py` DFS-detects them and refuses.
- **Missing dep ids** — a `depends_on` entry that doesn't match any `id`.
- **Missing required fields** — `id`, `title`, `spec`, or `depends_on`.
- **Duplicate ids**.
- **Malformed input** — `tasks` not an array, `depends_on` not a list, etc.

## Worked example

```json
{
  "trunk": "main",
  "tasks": [
    {
      "id": "add-user-model",
      "title": "Add User model with email + password",
      "spec": "Create src/models/user.py with SQLAlchemy User(id, email unique, password_hash, created_at). Add migration. Unit tests in tests/models/test_user.py covering create, uniqueness violation, password hashing round-trip. Acceptance: `pytest tests/models/test_user.py` passes; alembic upgrade head succeeds on a fresh DB.",
      "depends_on": [],
      "scope_files": ["src/models/user.py", "migrations/**", "tests/models/test_user.py"]
    },
    {
      "id": "add-auth-endpoints",
      "title": "Add /login and /logout endpoints",
      "spec": "Add POST /auth/login (email+password → session cookie) and POST /auth/logout (clear cookie) in src/api/auth.py. Wire into the router. Integration tests in tests/api/test_auth.py covering happy path, wrong password, unknown email, logout while unauthenticated. Acceptance: all auth tests pass; manual curl against the dev server returns expected status codes.",
      "depends_on": ["add-user-model"],
      "scope_files": ["src/api/auth.py", "src/api/__init__.py", "tests/api/test_auth.py"],
      "requires_plan": true,
      "model": "claude-opus-4-7[1m]"
    },
    {
      "id": "docs-auth-readme",
      "title": "Document auth setup in README",
      "spec": "Add a 'Authentication' section to README.md: env vars, endpoint usage, cookie lifetime. No code changes. Acceptance: section renders correctly in GitHub preview; links to API reference work.",
      "depends_on": [],
      "scope_files": ["README.md"]
    }
  ]
}
```

In this example:

- `add-user-model` and `docs-auth-readme` are both wave 0 — they run in
  parallel.
- `add-auth-endpoints` waits for `add-user-model` to merge, then its worktree
  is rebased onto fresh `main` and the teammate is spawned. It requires a plan
  approval before implementing and pins `claude-opus-4-7[1m]` because the work
  is complex.
- `add-user-model` and `docs-auth-readme` do not set `model` and inherit
  whatever the lead's user settings specify.
- No scope overlap (`src/models/**` vs `src/api/**` vs `README.md`), so no
  warnings.
