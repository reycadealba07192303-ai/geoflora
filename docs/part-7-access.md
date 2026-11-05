# Part 7: accounts and controlled access

Completed locally on October 27, 2026 (Philippine time). This builds on the local accounts from [roles and automation](roles-and-automation.md). It is still local authentication on loopback, not a public deployment.

## Roles

| Role | Stored as | Can do |
|---|---|---|
| Contributor | `user` | Identify plants, submit reports, see only their own reports, photos and PDFs |
| Reviewer | `reviewer` | Contributor rights, plus the label review queue, approve/reject with rationale, and read workspace reports and photos for moderation |
| Administrator | `admin` | Reviewer rights, plus Manage accounts, and training worker/job details |

- **First administrator and registration.** Setup creates the first administrator. After that, public registration creates contributors only, and any `role` sent by the client is ignored.
- **Roles are assigned in Manage accounts.** Only an administrator can assign roles.
- **Changes are immediate.** Roles are read from the database on every request, so a promotion or demotion applies to existing sessions at once.
- **Lockout protection.** Administrators cannot change their own role or disable themselves, so the workspace always keeps the administrator who is acting.
- **Existing data needed no migration.** The live database has one administrator and no other accounts.

## Server enforcement

- **Shared helpers.** `canModerate` (reviewer or administrator) and `isAdmin` in `src/lib/auth.ts` replace the inline `role === "admin"` checks:
  - Report list, detail, photo and PDF: owner, or a moderator for workspace-wide reads.
  - `?trainingCandidates=1` and `/api/admin/review` GET/PATCH: moderators.
  - Training `jobs` and `worker` fields: omitted for reviewers.
  - `/api/accounts`: administrators only.
- **Unchanged guards.** All routes keep the loopback and Origin guard. Signed-out requests get 401, wrong roles get 403, and another user's report gets 404.

## Sessions and recovery

- **Sessions.** Each session is a random 32-byte token stored only as a hash. Sessions expire after 8 hours and use HttpOnly, SameSite=Strict cookies. Logout deletes the session.
- **Disabled accounts.** Disabling an account deletes its sessions and blocks sign-in. `currentAccount` also rejects disabled accounts.
- **Password change.** Account settings requires the current password. The change signs out every other session and keeps the current one. Attempts are rate-limited.
- **Chosen recovery workflow: administrator-issued one-time reset code.** There is no email service in this local workspace.
  - In Manage accounts, the administrator selects **Issue reset code**. The 12-character code is shown once and is valid for 30 minutes.
  - Only its SHA-256 hash is stored. A new code replaces any earlier one.
  - The user enters the code under **Forgot your password?** on the sign-in screen. A successful reset signs out every other session and deletes the code.
  - Wrong codes, unknown usernames and disabled accounts all get the same refusal. Attempts share the sign-in rate limit.
- **Fallback when no administrator can sign in.** From the machine running the database, run:

  ```powershell
  .\services\ml\.venv\Scripts\python.exe scripts\issue_reset_code.py <username>
  ```

  It issues the same kind of code. Machine access is the trust boundary.

## Verification

- `scripts/smoke_access.py` passed 57 checks on the isolated `geoflora_access_validation` database through real HTTP. Evidence: [part-7-access-smoke.json](part-7-access-smoke.json). The checks covered:
  - Setup and registration rules, cookie flags and blocked self-elevation.
  - Contributor 403s on accounts, review and training candidates, plus signed-out 401s and the cross-origin refusal.
  - Ownership boundaries for report detail, photo, PDF and list.
  - Reviewer promotion, queue access and moderation photo access, and that reviewers still cannot manage accounts.
  - Review history recording the reviewer, repeat review refused, and demotion removing access immediately.
  - Self-demotion and self-disable refused, and unknown roles rejected.
  - Disable revoking live sessions, re-enable, and reset codes refused for disabled accounts.
  - Reset code: wrong code, unknown user, single use, case- and separator-tolerant entry, session revocation, old password rejected.
  - Password change rules and revocation of other sessions.
  - Administrator recovery through the CLI, and logout.
- `scripts/smoke_access_ui.mjs` passed 12 checks in headless Chrome on the isolated `geoflora_access_ui_validation` database. Evidence: [part-7-access-browser-smoke.json](part-7-access-browser-smoke.json). The checks covered:
  - Administrator setup, promoting a user and issuing a reset code from Manage accounts.
  - Using a reset code to sign in at 390px mobile width.
  - Reviewer navigation, which shows Label review without training controls and has no Manage accounts.
  - The Account settings layout.
  - Screenshots: `storage/logs/ui-preview/accounts-*.png`.
- The existing `scripts/smoke_sightings.py` regression passed. Typecheck and production build passed. The live web on 5173 was rebuilt and restarted.

## Limitations

- **Local authentication only.** There is no HTTPS, email verification, multi-factor authentication or account deletion. Before any shared deployment, Part 12 must add HTTPS so the `Secure` cookie flag is set.
- **Rate limits live in memory.** They are per process and reset when the web server restarts.
- **Reviewer scope is broad.** Reviewers can read all workspace reports, including exact coordinates, because moderation needs them. Public coordinate generalization is Parts 8 and 10.
- **No audit log for account changes.** Review decisions keep their own history, but role and disable changes do not.

## Email verification (October 31, 2026)

New accounts, both contributors and the first administrator, must confirm their email before they can sign in. Creating an account emails a 6-digit code (valid 10 minutes) and opens a "Verify your email" screen; no session exists until the code is entered. Signing in to an unverified account is refused with a prompt for the code. "Resend code" needs the account password and is limited to three per 15 minutes; a new code cancels the previous one. Verification codes and password-reset codes are separate (`issuedBy` `verify-email` vs `email`), so neither works for the other. If the email cannot be sent, the account is not kept, so the person can retry later. Accounts created before verification existed have no `emailVerified` field and are treated as verified. Administrators see "Email not verified" in Manage accounts and can use "Mark verified" when an address is confirmed another way.

Email is sent with Gmail SMTP using `GEOFLORA_SMTP_USER` and an app password in `GEOFLORA_SMTP_PASSWORD` (`apps/web/.env.local`); `GEOFLORA_SMTP_HOST` and `GEOFLORA_SMTP_PORT` select another server. On October 31, 2026 Gmail rejected the stored credentials (`535 5.7.8 Username and Password not accepted`), so registration returns "We could not send the verification email" until a valid app password is set.

Verified with a local test mail server: 15 API checks (no session before verification, wrong/used codes refused, verification code rejected as a reset code, resend needs the password and cancels the old code, administrator mark-verified), account not kept when mail is down, legacy accounts still sign in, and the browser flow from registration to workspace.

