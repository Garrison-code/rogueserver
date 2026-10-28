#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Garrison-code
# SPDX-License-Identifier: AGPL-3.0-only
"""Registry confirmation, quality gates and cross-repository dispatch. No dependencies."""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

OWNER = "Garrison-code"
REPOSITORIES = (f"{OWNER}/pokerogue", f"{OWNER}/rogueserver")
WORKFLOWS = {
    REPOSITORIES[0]: ("Linting", "Tests", "Deployment checks"),
    REPOSITORIES[1]: ("Build",),
}
BUILD_ID_LABEL = "io.garrix.build-id"
SHA = re.compile(r"^[0-9a-f]{40}$")
BUILD_ID = re.compile(r"^([0-9]+)-([0-9]+)$")

class Failure(RuntimeError):
    pass

def require(name):
    value = os.environ.get(name, "")
    if not value:
        raise Failure(f"Missing configuration: {name}")
    return value

def http(url, token=None, data=None, method=None):
    headers = {"Accept": "application/json", "User-Agent": "PokeRogue-dev-deployment/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, headers=headers, data=body, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.headers, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        # Never include response bodies: auth/provider failures may contain secrets.
        raise Failure(f"HTTP {error.code} from {urllib.parse.urlsplit(url).hostname}") from None
    except (OSError, ValueError) as error:
        raise Failure(f"{type(error).__name__} contacting {urllib.parse.urlsplit(url).hostname}") from None

def github(path, token, data=None, method=None):
    return http("https://api.github.com" + path, token, data, method)[1]

def output(name, value):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write(f"{name}={value}\n")

def registry(repository, tag="develop"):
    if repository not in REPOSITORIES:
        raise Failure("Repository is not allowed")
    if tag not in ("develop", "latest"):
        raise Failure("Registry tag is not allowed")
    image = repository.lower()
    auth = http("https://ghcr.io/token?" + urllib.parse.urlencode({
        "service": "ghcr.io", "scope": f"repository:{image}:pull",
    }))[1]
    token = auth.get("token") or auth.get("access_token")
    if not token:
        raise Failure("Registry did not return an anonymous pull token")
    def fetch(path):
        request = urllib.request.Request("https://ghcr.io/v2/" + image + path, headers={
            "Authorization": f"Bearer {token}",
            "Accept": ", ".join((
                "application/vnd.oci.image.index.v1+json",
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.docker.distribution.manifest.list.v2+json",
                "application/vnd.docker.distribution.manifest.v2+json",
            )),
            "User-Agent": "PokeRogue-dev-deployment/1.0",
        })
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.headers, json.load(response)
        except (urllib.error.HTTPError, OSError, ValueError):
            raise Failure("Cannot read anonymous GHCR image metadata") from None
    headers, manifest = fetch(f"/manifests/{tag}")
    digest = headers.get("Docker-Content-Digest", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise Failure("Registry did not return a valid tag digest")
    if "manifests" in manifest:
        platforms = [item for item in manifest["manifests"]
                     if item.get("platform", {}).get("architecture") == "amd64"
                     and item.get("platform", {}).get("os") == "linux"]
        if len(platforms) != 1:
            raise Failure("Expected one linux/amd64 image")
        _, manifest = fetch("/manifests/" + platforms[0]["digest"])
    _, config = fetch("/blobs/" + manifest["config"]["digest"])
    labels = config.get("config", {}).get("Labels", {})
    revision = labels.get("org.opencontainers.image.revision", "")
    build_id = labels.get(BUILD_ID_LABEL, "")
    if not SHA.fullmatch(revision) or not BUILD_ID.fullmatch(build_id):
        raise Failure("Image lacks valid revision/build_id labels; deploy metadata images first")
    if labels.get("org.opencontainers.image.source") != f"https://github.com/{repository}":
        raise Failure("Image source label does not match the approved repository")
    return {"repository": repository, "image": f"ghcr.io/{image}:{tag}",
            "digest": digest, "revision": revision, "build_id": build_id}

def runs_for(repository, revision, token):
    query = urllib.parse.urlencode({"head_sha": revision, "event": "push", "per_page": 100})
    return github(f"/repos/{repository}/actions/runs?{query}", token)["workflow_runs"]

def jobs_for(repository, run_id, token):
    result = []
    for page in range(1, 11):
        body = github(f"/repos/{repository}/actions/runs/{run_id}/jobs?per_page=100&page={page}", token)
        result.extend(body["jobs"])
        if len(body["jobs"]) < 100:
            return result
    raise Failure("Too many workflow jobs")

def quality(repository, revision, token, wait=False):
    if repository not in REPOSITORIES or not SHA.fullmatch(revision):
        raise Failure("Invalid quality-gate repository/revision")
    deadline = time.monotonic() + (900 if wait else 0)
    while True:
        runs = runs_for(repository, revision, token)
        pending = []
        for name in WORKFLOWS[repository]:
            candidates = [run for run in runs
                          if run["name"] == name and run["head_branch"] == "develop"]
            if not candidates:
                pending.append(name)
                continue
            run = max(candidates, key=lambda item: item["id"])
            if run["status"] != "completed":
                pending.append(name)
            elif run["conclusion"] != "success":
                raise Failure(f"Required workflow failed: {name}")
            elif repository.endswith("/rogueserver") and not any(
                job["name"] == "Linux develop tests and build"
                and job["conclusion"] == "success"
                for job in jobs_for(repository, run["id"], token)
            ):
                raise Failure("Backend Linux develop tests/build did not actually succeed")
        if not pending:
            return
        if not wait or time.monotonic() >= deadline:
            raise Failure("Required workflows not ready: " + ", ".join(pending))
        time.sleep(15)

def publication(image, token, branch="develop"):
    match = BUILD_ID.fullmatch(image["build_id"])
    run_id, attempt = match.groups()
    repository = image["repository"]
    run = github(f"/repos/{repository}/actions/runs/{run_id}", token)
    if (run["head_sha"] != image["revision"] or run["head_branch"] != branch
            or run["event"] not in ("push", "workflow_dispatch")
            or str(run.get("run_attempt", 1)) != attempt
            or run["path"].split("@")[0] != ".github/workflows/ghcr.yml"):
        raise Failure(f"Image build identity does not match an approved {branch} publication")
    # notify may still be running, so the publish job, not the whole run, is authoritative.
    if not any(job["name"] == "publish" and job["conclusion"] == "success"
               for job in jobs_for(repository, run_id, token)):
        raise Failure("Image publisher has not succeeded")
    return run

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
    github(f"/repos/{REPOSITORIES[0]}/actions/workflows/ghcr.yml/dispatches", token, {
        "ref": "develop",
        "inputs": {"mode": "deploy", "source_repository": repository,
                   "source_sha": revision, "source_run_id": str(run_id), "resume": "false"},
    }, "POST")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("quality", "published", "notify"))
    args = parser.parse_args()
    repository = require("GITHUB_REPOSITORY")
    revision = require("GITHUB_SHA")
    if args.command == "quality":
        # Old push runs can be cancelled while waiting for independent checks.
        head = github(f"/repos/{repository}/branches/develop", require("GH_TOKEN"))["commit"]["sha"]
        if head != revision:
            output("eligible", "false")
            print("Commit superseded before publishing.")
            return
        quality(repository, revision, require("GH_TOKEN"), wait=True)
        output("eligible", "true")
    else:
        image = published(repository, revision, require("BUILD_ID"), require("PUBLISHED_DIGEST"))
        output("ready", "true" if image else "false")
        if image and args.command == "notify":
            dispatch(repository, revision, require("GITHUB_RUN_ID"), require("GH_TOKEN"))
            print("Registry publication confirmed; develop deployment requested.")

if __name__ == "__main__":
    try:
        main()
    except Failure as error:
        print(f"::error::{error}", file=sys.stderr)
        sys.exit(1)
