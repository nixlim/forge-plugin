"""Bead forge-plugin-772y: the Claude effort `xhigh` is admitted end to end."""

from __future__ import annotations

import re
import unittest
from unittest import mock

from tests import test_route_snapshot as snapshot
from tests.test_route_config_support import (
    ROOT,
    RouteConfigSupport,
    route_config,
    route_config_probe,
    route_text,
)

journal = snapshot.journal
route_evidence = snapshot.route_evidence
SPEC_EFFORTS_RE = re.compile(
    r"Codex effort is exactly `([^`]+)`; Claude effort is exactly `([^`]+)`"
)
XHIGH_REVIEW_FINAL = (
    'schema = "forge-routes/1"\n[review-final]\nprovider = "claude"\n'
    'model = "opus-5.5"\neffort = "xhigh"\n'
)


def spec_effort_sets() -> dict[str, frozenset[str]]:
    text = (ROOT / "docs/specs/forge-plugin-spec.md").read_text(encoding="utf-8")
    matches = SPEC_EFFORTS_RE.findall(text)
    if len(matches) != 1:
        raise AssertionError(f"expected one FR-244 effort sentence, found {len(matches)}")
    codex, claude = (frozenset(value.split(" | ")) for value in matches[0])
    return {"codex": codex, "claude": claude}


class XhighGrammarTests(RouteConfigSupport, unittest.TestCase):
    def test_spec_effort_sets_equal_the_committed_grammar(self) -> None:
        def assertion() -> None:
            self.assertEqual(spec_effort_sets(), route_config.EFFORTS)

        assertion()
        self.assertIn("xhigh", spec_effort_sets()["claude"])
        self.assertNotIn("xhigh", spec_effort_sets()["codex"])
        drifted = {**route_config.EFFORTS, "claude": frozenset({"low", "medium", "high", "max"})}
        with mock.patch.object(route_config, "EFFORTS", drifted):
            with self.assertRaises(AssertionError):
                assertion()

    def test_every_role_resolves_claude_xhigh_locally(self) -> None:
        tables = "".join(
            f'[{role}]\nprovider = "claude"\nmodel = "opus-5.5"\neffort = "xhigh"\n'
            for role in route_config.ROLES
        )
        self.write_routes(('schema = "forge-routes/1"\n' + tables).encode())
        for route in self.load().routes:
            with self.subTest(role=route.role):
                self.assertEqual(
                    (route.provider, route.effort, route.route_source),
                    ("claude", "xhigh", "local"),
                )

    def test_committed_review_final_frontmatter_admits_xhigh(self) -> None:
        self.commit_paths(
            {"agents/review-final.md": "---\nmodel: opus-5.5\neffort: xhigh\n---\nbody\n"}
        )
        route = self.load().for_role("review-final")
        self.assertEqual(
            (route.provider, route.model, route.effort, route.route_source),
            ("claude", "opus-5.5", "xhigh", "committed-default"),
        )

    def test_codex_xhigh_still_refuses_the_whole_file(self) -> None:
        def assertion() -> None:
            self.write_routes(route_text(provider="codex", effort="xhigh"))
            self.assert_route_refusal("invalid value for effort in [implementer]")

        assertion()
        admitted = {**route_config.EFFORTS, "codex": route_config.EFFORTS["codex"] | {"xhigh"}}
        with mock.patch.object(route_config, "EFFORTS", admitted):
            with self.assertRaises(AssertionError):
                assertion()

    def test_probe_passes_xhigh_to_the_claude_profile_argv(self) -> None:
        self.write_routes(XHIGH_REVIEW_FINAL.encode())
        with mock.patch.object(route_config_probe, "probe_routes", return_value=[]) as probe:
            status, _stdout, stderr = self.invoke(
                "probe", "--repo", str(self.repo), "--role", "review-final"
            )
        self.assertEqual((status, stderr), (0, ""))
        (spec,) = probe.call_args.args[2]
        self.assertEqual((spec.provider, spec.effort), ("claude", "xhigh"))
        argv = route_config_probe._claude_argv(spec, ROOT)
        index = argv.index("--effort")
        self.assertEqual(argv[index : index + 2], ("--effort", "xhigh"))


class XhighSnapshotTests(snapshot.Revision9BuilderBatchSupport, unittest.TestCase):
    _write_local = snapshot.RouteSnapshotTests._write_local
    _open = snapshot.RouteSnapshotTests._open
    _open_task = snapshot.RouteSnapshotTests._open_task
    _execution = snapshot.RouteSnapshotTests._execution

    def setUp(self) -> None:
        super().setUp()
        self.env.pop("CLAUDE_CODE_SESSION_ID", None)
        self.execution_number = 0

    def test_run_open_freezes_xhigh_and_a_matching_execution_is_accepted(self) -> None:
        self._write_local(XHIGH_REVIEW_FINAL.replace("[review-final]", "[implementer]"))
        run_id = "run-20260927-route-xhigh"
        route = self._open_task(run_id)["route"]["implementer"]
        self.assertEqual((route["provider"], route["effort"]), ("claude", "xhigh"))
        self.assertEqual(route["route_sha256"], route_evidence.route_digest("implementer", route))
        execution = self._execution(run_id, route).records[0]
        self.assertEqual(
            (execution["effort"], execution["sandbox"]), ("xhigh", "instruction-bounded")
        )
        with self.assertRaises(journal.CoordinationRefusal) as caught:
            self._execution(run_id, route, effort="max")
        self.assertEqual(
            "forge: execution refused — route diverges from run snapshot for implementer: effort",
            str(caught.exception),
        )

    def test_opening_snapshot_refuses_codex_xhigh(self) -> None:
        entry = {"provider": "codex", "model": "gpt-5.6-sol", "effort": "xhigh",
                 "route_source": "local"}
        entry["route_sha256"] = route_evidence.route_digest("implementer", entry)
        claude = {**entry, "provider": "claude"}
        claude["route_sha256"] = route_evidence.route_digest("implementer", claude)
        self.assertIsNone(route_evidence._valid_route_entry("implementer", claude))

        def assertion() -> None:
            self.assertEqual(
                "run_started.route.implementer.effort is invalid for provider codex",
                route_evidence._valid_route_entry("implementer", entry),
            )

        assertion()
        admitted = {**route_config.EFFORTS, "codex": route_config.EFFORTS["codex"] | {"xhigh"}}
        with mock.patch.object(route_config, "EFFORTS", admitted):
            with self.assertRaises(AssertionError):
                assertion()


if __name__ == "__main__":
    unittest.main()
