<!-- SPDX-FileCopyrightText: 2026 Garrison-code -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# Backend develop publication and deployment

Review the frontend coordinator and setup guide before enabling this workflow:
https://github.com/Garrison-code/pokerogue/blob/develop/docs/develop-deployment.md

The Linux develop tests and build job really executes in this fork with
Go 1.22 and build tag devsetup. The publisher waits for that job and the Build
workflow to succeed before publishing develop. A successful workflow with
skipped upstream jobs is insufficient.

Docker build arguments BUILD_REVISION and BUILD_ID embed the source commit and
GitHub run ID-attempt. GET /game/build-info (externally /api/game/build-info)
returns just revision/build_id without authentication and with no-store.
The image has matching OCI revision/source labels plus io.garrix.build-id.

After confirming the published develop tag's digest and identity in GHCR, the
workflow can notify the existing frontend coordinator. Notifications are off
unless the repository variable DEV_AUTO_DEPLOY_ENABLED is true.

Required backend repository setup:
- Variable DEV_AUTO_DEPLOY_ENABLED=false until reviewed rollout is complete.
- Secret DEV_DEPLOY_GH_TOKEN: dedicated 90-day fine-grained PAT restricted to
  the two Garrison-code repositories with Actions Read/Write, no Contents write.
- No Coolify, Tailscale or game-account credential is stored in this repository.

Do not enable before both reviewed PRs are merged, the frontend setup is
complete, the database tag is fixed to mariadb:11.8.9, and the first manual
coordinator deployment verifies both metadata endpoints and savedata APIs.

Only develop sends notifications. Existing master/latest publication is not a
production deployment. The worker accepts only the two fixed repositories and
always runs the frontend ghcr.yml workflow at ref develop. It never receives a
Coolify URL or resource UUID from the source notification.

No automatic rollback or repeated restart is attempted on failure. Use the
frontend deployment report and manual resume after investigating. Disable the
repository variable to stop future notifications; this does not cancel an
already accepted deployment.
