#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Garrison-code
# SPDX-License-Identifier: AGPL-3.0-only
"""Confirm latest publication and dispatch the isolated production coordinator."""
import argparse
import os
import sys
import time

import publish_notify as common

REPOSITORIES = common.REPOSITORIES
BRANCHES = {REPOSITORIES[0]: "beta", REPOSITORIES[1]: "master"}
Failure = common.Failure
SHA = common.SHA
require = common.require
http = common.http
github = common.github
output = common.output

def registry(repository):
    return common.registry(repository, tag="latest")

def publication(image, token):
    repository = image["repository"]
    if repository not in BRANCHES:
        raise Failure("Repository is not allowed")
    return common.publication(image, token, branch=BRANCHES[repository])

def published(repository, revision, build_id, digest):
    deadline = time.monotonic() + 120
    while True:
        try:
            image = registry(repository)
            if image["revision"] == revision and image["build_id"] == build_id:
                if image["digest"] != digest:
                    raise Failure("Published digest differs from the registry tag")
                return image
            # Older registry metadata can briefly remain visible after a push.
            actual = tuple(map(int, image["build_id"].split("-")))
            expected = tuple(map(int, build_id.split("-")))
            if actual > expected:
                print("Publication superseded; skipping this notification.")
                return None
            if actual == expected:
                raise Failure("Registry build ID matches but its revision does not")
            if time.monotonic() >= deadline:
                raise Failure("Published tag did not become visible within two minutes")
            time.sleep(10)
        except Failure:
            if time.monotonic() >= deadline:
                raise
            time.sleep(10)

def dispatch(repository, revision, run_id, token):
    if repository not in REPOSITORIES or not SHA.fullmatch(revision) or not str(run_id).isdigit():
        raise Failure("Invalid deployment notification")
    github(f"/repos/{REPOSITORIES[0]}/actions/workflows/deploy-production.yml/dispatches", token, {
        "ref": "beta",
        "inputs": {"mode": "deploy", "source_repository": repository,
                   "source_sha": revision, "source_run_id": str(run_id), "resume": "false"},
    }, "POST")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("published", "notify"))
    args = parser.parse_args()
    repository = require("GITHUB_REPOSITORY")
    if repository not in BRANCHES or os.environ.get("GITHUB_REF") != "refs/heads/" + BRANCHES[repository]:
        raise Failure("Production publishing is limited to frontend beta and backend master")
    if args.command == "notify" and os.environ.get("PROD_AUTO_DEPLOY_ENABLED") != "true":
        output("ready", "false")
        print("Production automatic deployment is disabled.")
        return
    revision = require("GITHUB_SHA")
    image = published(repository, revision, require("BUILD_ID"), require("PUBLISHED_DIGEST"))
    output("ready", "true" if image else "false")
    if image and args.command == "notify":
        publication(image, require("GH_TOKEN"))
        dispatch(repository, revision, require("GITHUB_RUN_ID"), require("GH_TOKEN"))
        print("Registry publication confirmed; production deployment requested.")

if __name__ == "__main__":
    try:
        main()
    except Failure as error:
        print(f"::error::{error}", file=sys.stderr)
        sys.exit(1)
