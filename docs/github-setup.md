# Pushing this repository to GitHub with a personal access token

This guide sets up a computer to push to
[STEPHEN-NYARANGA/s2s-postprocessing-ecmwf](https://github.com/STEPHEN-NYARANGA/s2s-postprocessing-ecmwf)
over HTTPS with a GitHub personal access token (PAT). GitHub stopped accepting account
passwords for `git push` in 2021, so a token takes the password's place.

The token is a secret, like a password. Never put it in a file in this repository, in
`config.toml`, in a commit message, in a remote URL or in a chat. Paste it only into the
prompts described below.

## Plan

| Step | Where | What | Once or every time |
|---|---|---|---|
| 1 | github.com | Create a fine-grained token for this repository only | Once (renew when it expires) |
| 2 | Terminal | Install Git and set your name and email | Once per computer |
| 3 | Terminal | Clone the repository, or connect an existing folder | Once per computer |
| 4 | Terminal | First push: paste the token when asked; Git remembers it | Once per computer |
| 5 | Terminal | Commit and push changes | Every change |
| 6 | github.com | Revoke or renew the token | When it expires or leaks |

## 1. Create the token

1. Sign in to GitHub and open **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens** (https://github.com/settings/personal-access-tokens), then
   **Generate new token**.
2. **Token name**: for example `s2s-postprocessing-ecmwf laptop`.
3. **Expiration**: choose a date after the end of the competition period (DJF 2026 ends with
   the 4 February 2027 initialisation), for example 90 days or a custom date in March 2027.
4. **Repository access**: **Only select repositories** → `s2s-postprocessing-ecmwf`.
5. **Permissions → Repository permissions → Contents**: **Read and write**. (Metadata:
   Read-only is added automatically.) Nothing else is needed.
6. **Generate token** and copy it straight away. GitHub shows it only once; it starts with
   `github_pat_`.

## 2. Install Git and set your identity (once per computer)

Windows: install Git for Windows from https://git-scm.com/download/win (keep the default
**Git Credential Manager** option). macOS: `xcode-select --install`. Linux: your package manager.

```bash
git config --global user.name "Stephen Nyaranga"
git config --global user.email "you@example.org"     # the email on your GitHub account
git config --global init.defaultBranch main
```

## 3. Get the code onto the computer

New computer, nothing there yet:

```bash
git clone https://github.com/STEPHEN-NYARANGA/s2s-postprocessing-ecmwf.git
cd s2s-postprocessing-ecmwf
```

A folder that already has the code but is not yet a Git repository:

```bash
cd s2s-postprocessing-ecmwf
git init -b main
git remote add origin https://github.com/STEPHEN-NYARANGA/s2s-postprocessing-ecmwf.git
git fetch origin
git reset --mixed origin/main     # adopt GitHub's history; your files are left as they are
git status                        # shows how your files differ from GitHub
```

Check the remote. It must be the plain `https://github.com/...` address, with no token in it:

```bash
git remote -v
```

## 4. First push: give Git the token

```bash
git push -u origin main
```

- **Windows (Git Credential Manager)**: a GitHub sign-in window opens. Choose **Token** and
  paste the token, or sign in with the browser. The credential is stored in Windows Credential
  Manager, so later pushes do not ask again.
- **macOS / Linux**: Git asks for a username and a password. Username: `STEPHEN-NYARANGA`.
  Password: paste the token (nothing appears while pasting; that is normal). To make Git
  remember it, run once beforehand:

  ```bash
  git config --global credential.helper osxkeychain   # macOS
  git config --global credential.helper store         # Linux (plain-text file ~/.git-credentials)
  ```

Alternative with the GitHub CLI (`gh`), which also sets up Git for you:

```bash
gh auth login --hostname github.com --git-protocol https --with-token   # then paste the token, Enter, Ctrl+D (Ctrl+Z then Enter on Windows)
gh auth setup-git
gh auth status
```

## 5. Everyday use

```bash
git pull                      # get changes made elsewhere first
python tests/test_end_to_end.py   # the offline test should still pass
git status                    # check what changed; data/ and outputs/ are ignored on purpose
git add -A
git commit -m "Short description of the change"
git push
```

What is never pushed (see `.gitignore`): `data/`, `outputs/`, `*.nc`, the virtual environment,
`.env` and anything with `password` in its name. The AI Weather Quest password stays in the
`AIWQ_PASSWORD` environment variable.

## 6. When the token expires or leaks

- **Expired**: `git push` fails with "Authentication failed" or 403. Create a new token (step 1),
  then remove the stored one so Git asks again:
  - Windows: **Control Panel → Credential Manager → Windows Credentials** → remove
    `git:https://github.com`, or run `git credential-manager erase` and enter
    `protocol=https` and `host=github.com` on two lines followed by a blank line.
  - macOS: Keychain Access → search `github.com` → delete.
  - Linux: delete the `github.com` line from `~/.git-credentials`.

  Then push again and paste the new token.
- **Leaked** (pasted somewhere public, committed by mistake): revoke it at once at
  https://github.com/settings/personal-access-tokens, then create a new one. If it was committed,
  revoking is what matters; rewriting history does not un-leak it.

## Troubleshooting

| Message | Meaning and fix |
|---|---|
| `remote: Permission to ... denied` / 403 | The token lacks **Contents: Read and write** on this repository, or has expired. |
| `Authentication failed` | Wrong or expired token stored; clear it (section 6) and push again. |
| `rejected ... (fetch first)` | GitHub has commits you do not have: `git pull --rebase`, then `git push`. |
| `src refspec main does not match any` | Nothing committed yet: `git add -A` and `git commit` first. |
| `fatal: not a git repository` | Run the commands inside the `s2s-postprocessing-ecmwf` folder (section 3). |
