# SPDX-FileCopyrightText: 2026 Garrison-code
# SPDX-License-Identifier: AGPL-3.0-only
import io
import json
import unittest
from unittest.mock import patch
import urllib.error

import publish_notify as p

SHA = "a" * 40
IMAGE = {"repository": p.REPOSITORIES[0], "revision": SHA, "build_id": "123-1",
         "digest": "sha256:" + "1" * 64}

class PublisherTests(unittest.TestCase):
    def test_missing_checks_fail_closed(self):
        with patch.object(p, "runs_for", return_value=[]):
            with self.assertRaises(p.Failure):
                p.quality(p.REPOSITORIES[0], SHA, "test-token")

    def test_failed_checks_are_not_publishable(self):
        runs = [{"name": name, "head_branch": "develop", "status": "completed",
                 "conclusion": "failure" if name == "Tests" else "success", "id": i}
                for i, name in enumerate(p.WORKFLOWS[p.REPOSITORIES[0]])]
        with patch.object(p, "runs_for", return_value=runs):
            with self.assertRaises(p.Failure):
                p.quality(p.REPOSITORIES[0], SHA, "test-token")

    def test_skipped_backend_job_is_not_a_successful_build(self):
        runs = [{"name": "Build", "head_branch": "develop", "status": "completed",
                 "conclusion": "success", "id": 9}]
        with patch.object(p, "runs_for", return_value=runs), patch.object(
            p, "jobs_for", return_value=[{"name": "Linux develop tests and build",
                                       "conclusion": "skipped"}]
        ):
            with self.assertRaises(p.Failure):
                p.quality(p.REPOSITORIES[1], SHA, "test-token")

    def test_confirmed_checks_succeed(self):
        runs = [{"name": name, "head_branch": "develop", "status": "completed",
                 "conclusion": "success", "id": i}
                for i, name in enumerate(p.WORKFLOWS[p.REPOSITORIES[0]])]
        with patch.object(p, "runs_for", return_value=runs):
            p.quality(p.REPOSITORIES[0], SHA, "test-token")

    def test_superseded_publication_does_not_notify(self):
        with patch.object(p, "registry", return_value={**IMAGE, "revision": "b" * 40, "build_id": "124-1"}):
            self.assertIsNone(p.published(p.REPOSITORIES[0], SHA, "123-1", IMAGE["digest"]))

    def test_older_registry_metadata_is_retried_until_publication_is_visible(self):
        old = {**IMAGE, "revision": "b" * 40, "build_id": "122-1"}
        with patch.object(p, "registry", side_effect=[old, IMAGE]), patch.object(p.time, "sleep"):
            self.assertEqual(p.published(p.REPOSITORIES[0], SHA, "123-1", IMAGE["digest"]), IMAGE)

    def test_registry_digest_must_match_build_output(self):
        with patch.object(p, "registry", return_value=IMAGE), patch.object(
            p.time, "monotonic", side_effect=[0, 121]
        ):
            with self.assertRaises(p.Failure):
                p.published(p.REPOSITORIES[0], SHA, "123-1", "sha256:" + "2" * 64)

    def test_deployment_dispatch_is_fixed_to_frontend_develop(self):
        with patch.object(p, "github") as call:
            p.dispatch(p.REPOSITORIES[1], SHA, "123", "test-token")
            args = call.call_args.args
            self.assertIn("/pokerogue/actions/workflows/ghcr.yml/dispatches", args[0])
            self.assertEqual(args[2]["ref"], "develop")
            self.assertEqual(args[2]["inputs"]["resume"], "false")
            self.assertEqual(args[2]["inputs"]["mode"], "deploy")

    def test_unapproved_repository_cannot_dispatch(self):
        with patch.object(p, "github") as call:
            with self.assertRaises(p.Failure):
                p.dispatch("someone/else", SHA, "123", "token")
            call.assert_not_called()

    def test_http_failure_does_not_log_response_or_secret(self):
        error = urllib.error.HTTPError("https://api.github.com/x", 401, "unauthorized",
                                       {}, io.BytesIO(b"private-response-secret"))
        with patch.object(p.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(p.Failure) as caught:
                p.http("https://api.github.com/x", "private-token")
            self.assertNotIn("private", str(caught.exception))

    def test_publication_checks_completed_publish_job_not_whole_run(self):
        run = {"head_sha": SHA, "head_branch": "develop", "event": "push",
               "run_attempt": 1, "path": ".github/workflows/ghcr.yml",
               "status": "in_progress"}
        with patch.object(p, "github", return_value=run), patch.object(
            p, "jobs_for", return_value=[{"name": "publish", "conclusion": "success"},
                                       {"name": "notify-develop", "conclusion": None}]
        ):
            self.assertEqual(p.publication(IMAGE, "token"), run)

    def test_registry_resolves_only_linux_amd64_and_does_not_return_pull_token(self):
        class Response(io.BytesIO):
            def __init__(self, data, headers=None):
                super().__init__(json.dumps(data).encode())
                self.headers = headers or {}
        labels = {"org.opencontainers.image.revision": SHA,
                  "org.opencontainers.image.source": "https://github.com/" + p.REPOSITORIES[0],
                  p.BUILD_ID_LABEL: "123-1"}
        replies = [
            Response({"token": "anonymous-pull-token"}),
            Response({"manifests": [{"platform": {"os": "linux", "architecture": "amd64"},
                                     "digest": "sha256:platform"}]},
                     {"Docker-Content-Digest": IMAGE["digest"]}),
            Response({"config": {"digest": "sha256:config"}}),
            Response({"config": {"Labels": labels}}),
        ]
        with patch.object(p.urllib.request, "urlopen", side_effect=replies):
            value = p.registry(p.REPOSITORIES[0])
            self.assertEqual(value["digest"], IMAGE["digest"])
            self.assertNotIn("anonymous-pull-token", json.dumps(value))

if __name__ == "__main__":
    unittest.main()
