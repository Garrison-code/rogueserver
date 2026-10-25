<!--
SPDX-FileCopyrightText: 2026 Garrison-code

SPDX-License-Identifier: CC-BY-NC-SA-4.0
-->

# Container images

GitHub Actions publishes the existing Dockerfile to `ghcr.io/garrison-code/rogueserver`.
This workflow builds images only; it does not trigger Coolify deployments.

| Source branch | Moving tag |
| --- | --- |
| `master` | `latest` |
| `develop` | `develop` |

Every build also publishes `sha-<full commit SHA>`. Use that tag or the image
digest in the Actions run summary to pin a deployment or roll back. Pushes to
other branches and tags do not publish images. Manual runs are supported on
`master` and `develop` only. Both branches use the same Dockerfile and
build defaults; branch names do not change application settings.

## First run and access

The workflow uses the built-in `GITHUB_TOKEN` with `packages: write`;
no personal access token or new repository secret is required for publishing.
If Actions is disabled for this fork, enable it in the repository's Actions tab.
Repository or organization policy must allow the referenced actions and package
publishing.

New GHCR packages default to private, independently of repository visibility.
After the first successful push, choose the package's visibility in its settings.
For anonymous pulls, set it to public. To keep it private, configure Coolify with
a registry credential that can read this package.

Standard GitHub-hosted runners are free for public repositories, and GHCR
container image storage and bandwidth are currently free. This workflow disables
build-record artifact uploads and uses the standard Actions build cache.
See [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
and [Packages billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages).

## Coolify handoff

- Image: `ghcr.io/garrison-code/rogueserver`
- Tag: `latest` for the main environment, `develop` for the development environment
- Platform: `linux/amd64` (change the workflow before using an ARM64 host)
- Container port: `8001`

The Dockerfile retains its existing `BUILD_TAGS=devsetup` default. The
`develop` image does not implicitly enable the separate upstream `beta`
build tag. Configure database credentials, other runtime settings, and persistent
storage in Coolify as for the existing service. Keep development and production
databases and data volumes separate.

Pushing an image does not update a running container. Coolify must pull the image
and recreate the container; a restart alone does not switch images. Automatic
deployment through the tailnet will be configured separately.
