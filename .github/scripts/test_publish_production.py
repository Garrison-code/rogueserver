# SPDX-FileCopyrightText: 2026 Garrison-code
# SPDX-License-Identifier: AGPL-3.0-only
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

import publish_production as p

SHA = "a" * 40
IMAGE = {"repository": p.REPOSITORIES[0], "revision": SHA, "build_id": "123-1",
         "digest": "sha256:" + "1" * 64}

class ProductionPublisherTests(unittest.TestCase):
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


    def test_dispatch_uses_dedicated_production_workflow_and_beta(self):
        with patch.object(p, "github") as call:
            p.dispatch(p.REPOSITORIES[1], SHA, "123", "token")
            args = call.call_args.args
            self.assertIn("/pokerogue/actions/workflows/deploy-production.yml/dispatches", args[0])
            self.assertEqual(args[2]["ref"], "beta")
            self.assertEqual(args[2]["inputs"]["resume"], "false")
            self.assertEqual(args[2]["inputs"]["mode"], "deploy")

    def test_unknown_source_cannot_dispatch(self):
        with patch.object(p, "github") as call:
            with self.assertRaises(p.Failure):
                p.dispatch("someone/else", SHA, "123", "token")
            call.assert_not_called()

    def test_each_primary_branch_can_publish_but_develop_cannot(self):
        for repo, branch in p.BRANCHES.items():
            image = {**IMAGE, "repository": repo}
            run = {"head_sha": SHA, "head_branch": branch, "event": "push",
                   "run_attempt": 1, "path": ".github/workflows/ghcr.yml"}
            with patch.object(p.common, "github", return_value=run), patch.object(
                p.common, "jobs_for", return_value=[{"name": "publish", "conclusion": "success"}]
            ):
                self.assertEqual(p.publication(image, "token"), run)
                for wrong in ("develop", "codex/unreviewed"):
                    run["head_branch"] = wrong
                    with self.assertRaises(p.Failure):
                        p.publication(image, "token")

    def test_failed_or_skipped_publisher_is_rejected(self):
        run = {"head_sha": SHA, "head_branch": "beta", "event": "push",
               "run_attempt": 1, "path": ".github/workflows/ghcr.yml"}
        for conclusion in ("failure", "skipped", None):
            with patch.object(p.common, "github", return_value=run), patch.object(
                p.common, "jobs_for", return_value=[{"name": "publish", "conclusion": conclusion}]
            ):
                with self.assertRaises(p.Failure):
                    p.publication(IMAGE, "token")

    def test_wrong_revision_attempt_or_workflow_is_rejected(self):
        valid = {"head_sha": SHA, "head_branch": "beta", "event": "push",
                 "run_attempt": 1, "path": ".github/workflows/ghcr.yml"}
        for change in ({"head_sha": "b" * 40}, {"run_attempt": 2},
                       {"path": ".github/workflows/other.yml"}, {"event": "pull_request"}):
            with patch.object(p.common, "github", return_value={**valid, **change}):
                with self.assertRaises(p.Failure):
                    p.publication(IMAGE, "token")

    def test_disabled_notifications_do_not_read_registry_or_dispatch(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": p.REPOSITORIES[0],
                                    "GITHUB_REF": "refs/heads/beta",
                                    "PROD_AUTO_DEPLOY_ENABLED": "false"}, clear=True), patch.object(
            sys, "argv", ["publish_production.py", "notify"]
        ), patch.object(p, "published") as published, patch.object(p, "dispatch") as dispatch:
            p.main()
            published.assert_not_called()
            dispatch.assert_not_called()

    def test_production_entrypoint_rejects_develop_before_any_network(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": p.REPOSITORIES[0],
                                    "GITHUB_REF": "refs/heads/develop"}, clear=True), patch.object(
            sys, "argv", ["publish_production.py", "published"]
        ), patch.object(p, "published") as published:
            with self.assertRaises(p.Failure):
                p.main()
            published.assert_not_called()

    def test_registry_resolves_only_linux_amd64_and_does_not_return_pull_token(self):
        class Response(io.BytesIO):
            def __init__(self, data, headers=None):
                super().__init__(json.dumps(data).encode())
                self.headers = headers or {}
        labels = {"org.opencontainers.image.revision": SHA,
                  "org.opencontainers.image.source": "https://github.com/" + p.REPOSITORIES[0],
                  p.common.BUILD_ID_LABEL: "123-1"}
        replies = [
            Response({"token": "anonymous-pull-token"}),
            Response({"manifests": [{"platform": {"os": "linux", "architecture": "amd64"},
                                     "digest": "sha256:platform"}]},
                     {"Docker-Content-Digest": IMAGE["digest"]}),
            Response({"config": {"digest": "sha256:config"}}),
            Response({"config": {"Labels": labels}}),
        ]
        with patch.object(p.common.urllib.request, "urlopen", side_effect=replies) as calls:
            value = p.registry(p.REPOSITORIES[0])
            self.assertEqual(value["digest"], IMAGE["digest"])
            self.assertEqual(value["image"], "ghcr.io/garrison-code/pokerogue:latest")
            self.assertTrue(any("/manifests/latest" in c.args[0].full_url for c in calls.call_args_list))
            self.assertNotIn("anonymous-pull-token", json.dumps(value))


if __name__ == "__main__":
    unittest.main()
