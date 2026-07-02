# mulchd — Setup

Read this once per machine, or when joining a new project. Day-to-day usage is in
`SKILL.md`.

Works with **Claude Code** (macOS / Linux / Windows) and **Claude Desktop**
(macOS / Windows).

---

## Security rules

1. **Never send a token over plain HTTP** to a non-localhost server. `localhost` is for
   local testing only; the team server is always HTTPS.
2. **Global token — keep it out of transcripts and command lines.** It can mint project
   tokens for any project you have access to. Store it in the credentials file and
   reference it via env var expansion, never paste it raw into a chat or shell command.
3. **Project tokens — don't commit them to git.** They're scoped to one project and one
   machine; if one leaks the blast radius is limited to what Claude can already read in
   that project. `.mcp.json` uses env var expansion and is safe to commit; any file
   holding a raw token value is not.
4. **Never record secrets into mulchd** — no credentials, API keys, account IDs, or
   client-identifying data. Records are team-visible and permanent.
5. Token possibly leaked? Revoke it — see **Token lifecycle**. Global token leaks are
   higher urgency than project token leaks.

---

## Credentials file

All tokens live in one file per machine, outside any repo.

**macOS / Linux:** `~/.config/mulchd/credentials`

```bash
mkdir -p ~/.config/mulchd && chmod 700 ~/.config/mulchd
printf 'Global token: ' && IFS= read -rs GLBTOK && echo
cat > ~/.config/mulchd/credentials <<EOF
export MULCHD_URL="http://localhost:8000"
export MULCHD_GLOBAL_TOKEN="$GLBTOK"
# One line per project token:
export MULCHD_TOKEN_PERSONAL_MULCHD="prj_..."
EOF
chmod 600 ~/.config/mulchd/credentials && echo "Saved."
```

`IFS= read -rs` works in bash and zsh. The token never appears in the transcript.

Load: `source ~/.config/mulchd/credentials`

**Windows:** `%USERPROFILE%\.mulchd\credentials.ps1`

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.mulchd" | Out-Null
@'
$env:MULCHD_URL = "http://localhost:8000"
$env:MULCHD_GLOBAL_TOKEN = "glb_..."
$env:MULCHD_TOKEN_PERSONAL_MULCHD = "prj_..."
'@ | Set-Content "$env:USERPROFILE\.mulchd\credentials.ps1"
```

Load: `. $env:USERPROFILE\.mulchd\credentials.ps1`

The **global token** is issued once by the admin with your account. Keep it here
permanently — it's needed again for every new project or machine. **Project tokens** are
self-service (below), one per project per machine, so a single machine can be revoked
without re-onboarding you.

---

## Project setup (once per project per machine)

Use whatever HTTP tool is available (curl, PowerShell `Invoke-RestMethod`, WebFetch).

**1. Load credentials, list your accessible projects**

```bash
source ~/.config/mulchd/credentials   # Windows: . $env:USERPROFILE\.mulchd\credentials.ps1
curl -s "$MULCHD_URL/api/me/projects" \
  -H "Authorization: Bearer $MULCHD_GLOBAL_TOKEN"
```

**2. Mint a project token**, labelled with the machine so it can be revoked individually:

```bash
curl -s -X POST "$MULCHD_URL/api/projects/personal/mulchd/tokens" \
  -H "Authorization: Bearer $MULCHD_GLOBAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"label\": \"claude-code-$(hostname)\"}"
```

The raw token is shown **once**. Add it to the credentials file immediately as
`MULCHD_TOKEN_PERSONAL_MULCHD` and paste it nowhere else.

**3. Register the MCP server**

### Claude Code — `.mcp.json` in the project root

Env var expansion makes this file **safe to commit** where a repo exists (and it should
be — it onboards the next teammate for free):

```json
{
  "mcpServers": {
    "mulchd": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer ${MULCHD_TOKEN_PERSONAL_MULCHD}"
      }
    }
  }
}
```

The env vars must exist in the environment Claude Code launches from: source the
credentials file in your shell profile (`.bashrc` / `.zshrc` / PowerShell `$PROFILE`), or
use a gitignored `.env` if your launcher supports it.

Approve the server and supply the token in `.claude/settings.local.json` (gitignored — do
not commit). There are two ways to provide the env vars:

**Option A — credentials file (recommended for shared machines or multiple projects)**

Source the credentials file in your shell profile (`.bashrc` / `.zshrc` / PowerShell
`$PROFILE`) so the vars are present when Claude Code launches, then add only the approval
key to `settings.local.json`:

```json
{
  "enabledMcpjsonServers": ["mulchd"]
}
```

**Option B — inline env in `settings.local.json` (simpler for a single project)**

Put the vars directly in `settings.local.json`. Claude Code injects them into MCP server
processes automatically — no shell profile change needed:

```json
{
  "enabledMcpjsonServers": ["mulchd"],
  "env": {
    "MULCHD_URL": "http://localhost:8000",
    "MULCHD_TOKEN_PERSONAL_MULCHD": "prj_..."
  }
}
```

`settings.local.json` is gitignored by default, but it sits inside the repo directory.
If you ever share or commit that file by accident, revoke the token immediately.

Restart Claude Code, run `/mcp` — `mulchd` should show green.

### Claude Desktop — global config file

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Desktop does not expand env vars in its config, so the raw token goes in the file. That's
acceptable — this file is per-user, outside any repo, never committed — but treat it like
the credentials file: no screenshots, no pasting into chats. Name entries per project,
since the config is global:

```json
{
  "mcpServers": {
    "mulchd-personal-mulchd": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer prj_..."
      }
    }
  }
}
```

**4. Wire up session instructions**

### Claude Code — `CLAUDE.md`

A pointer only, so instructions can't drift from the skill:

```markdown
## mulchd — Team Knowledge

This project uses mulchd. Follow the session workflow in
`.claude/skills/mulchd/SKILL.md` (session start → proactive recording → session end).
```

### Claude Desktop

No `CLAUDE.md` and no skills folder. Paste the contents of `SKILL.md` (minus the
frontmatter) into the project's custom instructions field in the Desktop UI.

**5. Persist the skill for the next person**

- Working in a git repo → commit `.claude/skills/mulchd/`, `.mcp.json`, and the
  `CLAUDE.md` pointer. They contain no tokens.
- No repo (Desktop users, ad-hoc folders) → nothing to commit; the skill is always
  re-fetchable from `http://localhost:8000/skill`, which is the canonical source.

---

## Token lifecycle

- **Revoke a machine's token:** web UI → project → tokens → revoke, or
  `DELETE $MULCHD_URL/api/projects/personal/mulchd/tokens/ID` with the global token.
  Per-machine tokens mean revoking one machine doesn't touch your others.
- **Rotate the global token:** admin action in the web UI; update the credentials file
  afterwards.
- **Lost laptop / leaked token:** revoke that machine's project tokens immediately; ask
  the admin to rotate your global token if it lived on that machine too.

---

## Keeping the skill up to date

The canonical skill is served by the mulchd server at `http://localhost:8000/skill` (bundle) and
`http://localhost:8000/skill/<FILE>` (individual files), always at the server's current version.
Vendored copies carry their version in `SKILL.md`; re-fetch when the server version is
newer.