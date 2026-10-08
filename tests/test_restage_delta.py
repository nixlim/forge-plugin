"""CLI proofs for Revision 22 in-chain restaging and candidate delta evidence."""

from __future__ import annotations

import json
import os
import subprocess
from types import SimpleNamespace
from unittest import mock

from tests import test_cli_chain as chain_tests
from tests._cli_loader import package_module
from tests.test_cli_chain import CLI_TEST_BOOTSTRAP, ForgeCLIFixture


class _RestageFixture(ForgeCLIFixture):
    def _restage(self, chain_id: str, *paths: str, expected: int = 0):
        return self.cli(
            "commit", "restage", "--paths", *paths, "--chain-id", chain_id,
            expected=expected,
        )[1]


class RestagePathTests(_RestageFixture):
    def test_commit_skill_describes_restage(self) -> None:
        skill = (chain_tests.ROOT / "skills/commit/SKILL.md").read_text(encoding="utf-8")
        prose = " ".join(skill.split())
        self.assertIn("naming every revised repository path under `commit start`'s path rules; "
                      "the CLI records the old and new candidate identities and their exact "
                      "tree delta.", prose)
        self.assertIn("Every gate and the review run again after a restage; nothing carries "
                      "forward.", prose)
        self.assertIn("The named paths form the whole restaged candidate; any omitted staged "
                      "path is restored to HEAD.", prose)
        self.assertIn("returning to older tree bytes restores no superseded authority", prose)

    def test_start_literals_render_the_value_and_restage_shares_them(self) -> None:
        cases = (
            ("../outside", 'named path is outside the repository: "../outside"'),
            ('../quote"name', 'named path is outside the repository: "../quote\\"name"'),
            ("missing.txt", 'named path does not exist: "missing.txt"'),
            ("", "named path is outside the repository: (un-echoed)"),
        )
        for path, message in cases:
            with self.subTest(verb="start", path=path):
                result = self.cli("commit", "start", "--paths", path, expected=1)[1]
                self.assertEqual(result["reason_code"], "path-missing")
                self.assertEqual(result["message"], message)
        self.change("src/app.py", "VALUE = 2\n")
        chain_id = str(self.start("src/app.py")["chain_id"])
        before_index = self.git_bytes("diff", "--cached", "--binary")
        before_events = self.events(chain_id)
        for path, message in cases:
            with self.subTest(verb="restage", path=path):
                result = self._restage(chain_id, path, expected=1)
                self.assertEqual(result["reason_code"], "path-missing")
                self.assertEqual(result["message"], message)
                self.assertEqual(self.git_bytes("diff", "--cached", "--binary"), before_index)
                self.assertEqual(self.events(chain_id), before_events)

    def test_control_character_or_invalid_encoding_is_not_echoed(self) -> None:
        core = package_module("chain_core")
        self.assertEqual(core.echo_pathspec('a"b'), '"a\\"b"')
        for value in ("a\n", "a\rb", "a\tb", "\udcff"):
            with self.subTest(value=value):
                self.assertEqual(core.echo_pathspec(value), "(un-echoed)")
        for path in ("bad\npath", "\udcff"):
            with self.subTest(path=path):
                result = self.cli("commit", "start", "--paths", path, expected=1)[1]
                self.assertEqual(result["message"], "named path does not exist: (un-echoed)")

    def test_ignored_untracked_path_refuses_at_start_and_restage(self) -> None:
        self.change("src/app.py", "VALUE = 2\n")
        (self.repo / "ignored.txt").write_text("new\n", encoding="utf-8")
        with (self.repo / ".git/info/exclude").open("a", encoding="utf-8") as stream:
            stream.write("ignored.txt\n")
        message = 'named path does not exist: "ignored.txt"'
        before_index = self.git_bytes("diff", "--cached", "--binary")
        result, refusal = self.cli(
            "commit", "start", "--paths", "src/app.py", "ignored.txt", expected=1
        )
        self.assertEqual(result.stderr, "")
        self.assertEqual(refusal["message"], message)
        self.assertEqual(refusal["remediation"], "name a non-ignored repository path")
        self.assertEqual(self.git_bytes("diff", "--cached", "--binary"), before_index)
        chain_id = str(self.start("src/app.py")["chain_id"])
        before_index = self.git_bytes("diff", "--cached", "--binary")
        before_events = self.events(chain_id)
        refusal = self._restage(chain_id, "src/app.py", "ignored.txt", expected=1)
        self.assert_refusal_contract(refusal, "path-missing")
        self.assertEqual(refusal["message"], message)
        self.assertEqual(self.git_bytes("diff", "--cached", "--binary"), before_index)
        self.assertEqual(self.events(chain_id), before_events)
        repository = package_module("chain_core._repository").Repository(self.repo)
        original_git = repository.git

        def no_ignore_check(args, **kwargs):
            if "check-ignore" in args:
                return subprocess.CompletedProcess(args, 1, b"", b"")
            return original_git(args, **kwargs)

        with mock.patch.object(repository, "git", side_effect=no_ignore_check):
            self.assertEqual(repository.normalize_paths(["ignored.txt"]), ["ignored.txt"])

    def test_review_final_refuses_a_route_equal_to_the_implementer_route(self) -> None:
        route = self.repo / ".codex/agents/review-final.toml"
        route.parent.mkdir(parents=True)
        route.write_text(
            'model = "gpt-5.6-sol"\nmodel_reasoning_effort = "high"\n', encoding="utf-8"
        )
        self.git("add", ".codex/agents/review-final.toml")
        self.git("commit", "--quiet", "-m", "fixture equal final route")
        self.change("src/app.py", "VALUE = 2\n")
        chain_id = str(self.start("src/app.py", declare_tier="hard")["chain_id"])
        self.cli("verify", "--chain-id", chain_id, expected=0)
        before = self.events(chain_id)
        refused = self.cli("review", "request", "--chain-id", chain_id, expected=1)[1]
        self.assert_refusal_contract(refused, "state-precondition")
        self.assertEqual(
            refused["message"],
            "forge: review request refused — review-final route equals the implementer route",
        )
        self.assertEqual(refused["observed"], "codex/gpt-5.6-sol")
        self.assertIsNone(self.state(chain_id)["review"]["request"])
        self.assertEqual(self.events(chain_id), before)
        disabled = CLI_TEST_BOOTSTRAP.replace(
            "raise SystemExit(module.main(cli_argv))",
            "import forge_cli.engine._review_launch as launch\n"
            "launch.require_distinct_final_route = lambda *_args, **_kwargs: None\n"
            "raise SystemExit(module.main(cli_argv))",
        )
        with mock.patch.object(chain_tests, "CLI_TEST_BOOTSTRAP", disabled):
            self.cli("review", "request", "--chain-id", chain_id, expected=0)
        self.assertIsNotNone(self.state(chain_id)["review"]["request"])

    def test_restage_classifies_the_full_current_candidate(self) -> None:
        self.change("AGENTS.md", "# Control\n")
        self.change("src/app.py", "VALUE = 2\n")
        chain_id = str(self.cli(
            "commit", "start", "--paths", "AGENTS.md", "src/app.py", expected=0
        )[1]["chain_id"])
        tier = self.state(chain_id)["tier"]
        self.assertEqual((tier["control"], tier["effective"]), (True, "hard"))
        self.change("src/app.py", "VALUE = 3\n")
        self._restage(chain_id, "src/app.py")
        tier = self.state(chain_id)["tier"]
        self.assertEqual((tier["control"], tier["effective"]), (False, "standard"))


class RestageDeltaTests(_RestageFixture):
    def test_restage_event_records_identities_and_raw_tree_delta(self) -> None:
        self.change("src/app.py", "VALUE = 2\n")
        chain_id = str(self.start("src/app.py")["chain_id"])
        original = self.state(chain_id)["candidate"]
        self.change("assets/new.txt", "new\n")
        (self.repo / "docs/guide.md").unlink()
        os.chmod(self.repo / "scripts/tool.py", 0o755)
        (self.repo / "assets/blob.bin").rename(self.repo / "assets/renamed.bin")
        self._restage(
            chain_id, "assets/new.txt", "docs/guide.md", "scripts/tool.py",
            "assets/blob.bin", "assets/renamed.bin",
        )
        current = self.state(chain_id)["candidate"]
        detail = [event["payload"]["details"] for event in self.events(chain_id)
                  if event["payload"]["event"] == "candidate_restaged"][-1]
        self.assertEqual(detail["old_candidate_identity"], original)
        self.assertEqual(detail["new_candidate_identity"], current)
        self.assertEqual(detail["old_tree"], original["tree_oid"])
        self.assertEqual(detail["new_tree"], current["tree_oid"])
        entries = {item["path"]: item for item in detail["delta"]}
        self.assertEqual(entries["assets/new.txt"]["status"], "A")
        self.assertEqual(entries["docs/guide.md"]["status"], "D")
        self.assertEqual(entries["scripts/tool.py"]["old_mode"], "100644")
        self.assertEqual(entries["scripts/tool.py"]["new_mode"], "100755")
        self.assertEqual(entries["assets/renamed.bin"]["old_path"], "assets/blob.bin")
        self.assertTrue(entries["assets/renamed.bin"]["status"].startswith("R"))

    def test_mutating_gate_event_records_candidate_tree_delta(self) -> None:
        (self.repo / "forge-project.md").write_text(
            chain_tests.policy_with_changelog(), encoding="utf-8"
        )
        (self.repo / "CHANGELOG.md").write_text("# Changes\n", encoding="utf-8")
        self.git("add", "--", "forge-project.md", "CHANGELOG.md")
        self.git("commit", "--quiet", "-m", "configure changelog gate")
        self.change("src/app.py", "VALUE = 2\n")
        chain_id = str(self.start("src/app.py")["chain_id"])
        old = self.state(chain_id)["candidate"]
        self.cli("gate", "run", "changelog", "--chain-id", chain_id, expected=0)
        current = self.state(chain_id)["candidate"]
        details = [
            event["payload"]["details"] for event in self.events(chain_id)
            if event["payload"]["event"] == "mutating_gate_restaged"
        ][-1]
        self.assertEqual(details["old_candidate_identity"], old)
        self.assertEqual(details["new_candidate_identity"], current)
        self.assertEqual(details["old_tree"], old["tree_oid"])
        self.assertEqual(details["new_tree"], current["tree_oid"])
        self.assertIn("CHANGELOG.md", {entry["path"] for entry in details["delta"]})

    def test_tree_delta_uses_bounded_candidate_git(self) -> None:
        candidate = package_module("candidate")
        candidate_ops = package_module("engine._candidate_ops")
        repository_type = package_module("chain_core._repository").Repository
        self.change("src/app.py", "VALUE = 2\n")
        chain_id = str(self.start("src/app.py")["chain_id"])
        old_tree = str(self.state(chain_id)["candidate"]["tree_oid"])
        self.change("src/app.py", "VALUE = 3\n")
        self._restage(chain_id, "src/app.py")
        new_tree = str(self.state(chain_id)["candidate"]["tree_oid"])
        repository = repository_type(self.repo)
        with (
            mock.patch.object(repository, "git", side_effect=AssertionError("unbounded Git")),
            mock.patch.object(candidate, "git_output", wraps=candidate.git_output) as bounded,
        ):
            delta = candidate_ops._tree_delta(SimpleNamespace(repo=repository), old_tree, new_tree)
        self.assertEqual([(entry["status"], entry["path"]) for entry in delta],
                         [("M", "src/app.py")])
        bounded.assert_called_once()
        self.assertEqual(bounded.call_args.kwargs["stdout_limit"],
                         candidate.ENUMERATION_MAX_BYTES)

    def test_prior_eval_pass_reruns_even_when_delta_misses_trigger(self) -> None:
        self.change("scripts/tool.py", "CONTROL = 2\n")
        chain_id = str(self.start("scripts/tool.py")["chain_id"])
        self.cli("verify", "--chain-id", chain_id, expected=0)
        self.assertEqual(self.state(chain_id)["steps"]["strict-evals"][-1]["result"], "passed")
        self.change("docs/guide.md", "# Revised\n")
        self._restage(chain_id, "scripts/tool.py", "docs/guide.md")
        steps = self.state(chain_id)["steps"]
        for gate in ("strict-evals", "gate-1", "secret-scan"):
            self.assertNotIn(gate, steps)

    def test_prior_candidate_and_exact_delta_enter_review_package(self) -> None:
        self.change("src/app.py", "VALUE = 2\n")
        chain_id = str(self.start("src/app.py")["chain_id"])
        old = self.state(chain_id)["candidate"]
        self.cli("verify", "--chain-id", chain_id, expected=0)
        self.cli("review", "request", "--chain-id", chain_id,
                 expected=0, review_mode="block")
        self.wait_for_review_completion(self.state(chain_id)["review"]["request"])
        self.cli("review", "collect", "--chain-id", chain_id, expected=0)
        self.change("src/app.py", "VALUE = 3\n")
        self.change("assets/new.txt", "new\n")
        self._restage(chain_id, "src/app.py", "assets/new.txt")
        self.change("src/app.py", "VALUE = 4\n")
        self._restage(chain_id, "src/app.py", "assets/new.txt")
        self.cli("verify", "--chain-id", chain_id, expected=0)
        self.cli("review", "request", "--chain-id", chain_id, expected=0)
        request = self.state(chain_id)["review"]["request"]
        package = (self.repo / request["package"]).read_bytes()
        self.assertIn(
            b"prior-candidate: "
            + json.dumps(old, sort_keys=True, separators=(",", ":")).encode(),
            package,
        )
        self.assertIn(
            b"candidate-delta: "
            + json.dumps([{"status": "A", "path": "assets/new.txt", "old_path": None,
                           "old_mode": "000000", "new_mode": "100644"},
                          {"status": "M", "path": "src/app.py", "old_path": None,
                           "old_mode": "100644", "new_mode": "100644"}],
                         sort_keys=True, separators=(",", ":")).encode(),
            package,
        )

    def test_return_to_reviewed_tree_still_names_that_review(self) -> None:
        self.change("src/app.py", "VALUE = 2\n")
        chain_id = str(self.start("src/app.py")["chain_id"])
        reviewed = self.state(chain_id)["candidate"]
        self.cli("verify", "--chain-id", chain_id, expected=0)
        self.cli("review", "request", "--chain-id", chain_id,
                 expected=0, review_mode="block")
        self.wait_for_review_completion(self.state(chain_id)["review"]["request"])
        self.cli("review", "collect", "--chain-id", chain_id, expected=0)
        self._restage(chain_id, "src/app.py")
        self.cli("verify", "--chain-id", chain_id, expected=0)
        self.cli("review", "request", "--chain-id", chain_id, expected=0)
        request = self.state(chain_id)["review"]["request"]
        package = (self.repo / request["package"]).read_bytes()
        self.assertIn(b"prior-candidate: " + json.dumps(
            reviewed, sort_keys=True, separators=(",", ":")
        ).encode(), package)
        self.assertIn(b"candidate-delta: []\n", package)

    def test_candidate_bound_skips_are_void_and_do_not_revive_on_old_tree(self) -> None:
        self.change("src/app.py", "VALUE = 2\n")
        chain_id = str(self.start("src/app.py")["chain_id"])
        self.cli(
            "commit", "skip", "gate-1", "--reason", "fixture",
            "--chain-id", chain_id, expected=0,
        )
        self.change("src/app.py", "VALUE = 3\n")
        self._restage(chain_id, "src/app.py")
        self.assertNotIn("user_skips", self.state(chain_id)["steps"])
        self.change("src/app.py", "VALUE = 2\n")
        self._restage(chain_id, "src/app.py")
        steps = self.state(chain_id)["steps"]
        self.assertNotIn("user_skips", steps)
        self.assertNotIn("gate-1", steps)

    def test_fresh_eval_skip_is_candidate_bound(self) -> None:
        path = self.repo / "system/codex/prompts/new.md"
        path.parent.mkdir(parents=True)
        path.write_text("route prompt\n", encoding="utf-8")
        self.change("scripts/tool.py", "CONTROL = 2\n")
        chain_id = str(self.cli(
            "commit", "start", "--paths", "scripts/tool.py", "system/codex/prompts/new.md",
            expected=0,
        )[1]["chain_id"])
        self.cli(
            "commit", "skip", "fresh-reviewer-evals", "--reason", "fixture",
            "--chain-id", chain_id, expected=0,
        )
        self.assertIn("fresh-reviewer-evals", self.state(chain_id)["steps"]["user_skips"])
        path.write_text("route prompt revised\n", encoding="utf-8")
        self._restage(chain_id, "scripts/tool.py", "system/codex/prompts/new.md")
        self.assertNotIn("user_skips", self.state(chain_id)["steps"])
