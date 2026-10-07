"""Revision 22 chain-only authority and immutable legacy-history contracts."""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import os
import subprocess
import sys
import tempfile
from itertools import product
from pathlib import Path
from unittest import mock

from tests._cli_loader import CLI_PATH, package_module, patch_chain_core
from tests.test_chain_compatibility import CLI, ChainParsingTests, ChainProcessFixture


def separated_run_options(verb, arguments):
    words = verb.split()
    for equals, option_at, separator_at in product(
        (False, True), range(len(words)), range(len(words))
    ):
        if option_at <= separator_at:
            flags = ["--run-id=legacy"] if equals else ["--run-id", "legacy"]
            yield [*words[:option_at], *flags, *words[option_at:separator_at],
                   "--", *words[separator_at:], *arguments]


class RetiredChainOptionsTests(ChainParsingTests):
    def test_refusal_verbs_are_exactly_the_parser_leaf_verbs_except_launch(self):
        def verbs(parser, prefix=()):
            commands = next((action for action in parser._actions
                             if isinstance(action, argparse._SubParsersAction)), None)
            if commands is None:
                return {" ".join(prefix)}
            return {verb for name, child in commands.choices.items()
                    for verb in verbs(child, (*prefix, name))}

        required = {
            "commit start": ["--paths", "README.md"],
            "commit restage": ["--paths", "README.md"],
            "commit approve": ["--candidate", "candidate"],
            "commit skip": ["gate-1", "--reason", "reason"],
            "commit finalize": ["--message", "message"],
            "merge start": ["--worktree", "/absent"],
            "merge approve": ["--candidate", "candidate"],
            "merge gate run": ["gate-1"],
            "gate run": ["gate-1"],
            "review attach": ["--verdict-file", "/absent"],
            "review disposition": ["--finding", "1", "--severity", "MINOR",
                                   "--resolution", "resolved"],
            "chain tombstone": ["--reason", "reason"],
            "common-lock hold": ["--owner-kind", "merge", "--operation", "finalize",
                                 "--ready-fd", "1"],
        }
        with mock.patch.object(CLI.runtime, "MERGE_LIFECYCLE_ACTIVE", True):
            for verb in verbs(CLI.build_parser()) - {"launch"}:
                arguments = required.get(verb, [])
                for argv in ([*verb.split(), *arguments, "--run-id=legacy"],
                             *separated_run_options(verb, arguments)):
                    with self.subTest(verb=verb, argv=argv):
                        self.assert_revision9_refusal(
                            argv, reason="state-precondition",
                            message=f"forge: {verb} refused — --run-id and --task are not admitted",
                        )

    def test_other_chain_paths_use_the_same_run_option_literal(self):
        for verb, arguments in (
            ("status", []), ("verify", []), ("commit abort", []),
            ("commit restage", ["--paths", "README.md"]),
            ("merge verify", []), ("merge recover", []), ("merge gate run", ["gate-1"]),
        ):
            with (
                self.subTest(arguments=arguments),
                mock.patch.object(CLI.runtime, "MERGE_LIFECYCLE_ACTIVE", True),
            ):
                self.assert_revision9_refusal(
                    ["--run-id", "legacy", "--chain-id", "c-2026-10-06T120000Z-dead",
                     *verb.split(), *arguments],
                    reason="state-precondition",
                    message=f"forge: {verb} refused — --run-id and --task are not admitted",
                )

    def test_start_refuses_run_and_task_before_discovery(self):
        for verb, flags in product(("commit", "merge"), (
            ["--run-id", "legacy"],
            ["--task", "task-01"],
            ["--run-id", "legacy", "--task", "task-01"],
        )):
            arguments = (
                [verb, "start", "--paths", "README.md"]
                if verb == "commit"
                else [verb, "start", "--worktree", "/absent"]
            )
            with (self.subTest(verb=verb, flags=flags),
                  mock.patch.object(CLI.runtime, "MERGE_LIFECYCLE_ACTIVE", True)):
                self.assert_revision9_refusal(
                    [*arguments, *flags],
                    reason="state-precondition",
                    message=(f"forge: {verb} start refused — "
                             "--run-id and --task are not admitted"),
                )

    def test_pre_discovery_run_option_emitter_is_load_bearing(self):
        options = package_module("engine._cli_options")
        self.test_other_chain_paths_use_the_same_run_option_literal()
        with mock.patch.object(options, "_refuse_retired_chain_options", return_value=None):
            with self.assertRaises(AssertionError):
                self.assert_revision9_refusal(
                    ["commit", "start", "--paths", "README.md", "--task=legacy"],
                    reason="state-precondition",
                    message="forge: commit start refused — --run-id and --task are not admitted",
                )
            with self.assertRaises(AssertionError):
                self.assert_revision9_refusal(
                    ["--run-id", "legacy", "--", "status"], reason="state-precondition",
                    message="forge: status refused — --run-id and --task are not admitted",
                )

    def test_retired_verbs_and_archive_options_leave_the_parser(self):
        for arguments in (
            ["journal", "ingest-chain"],
            ["journal", "batch-recover"],
            ["commit", "abort-disposition"],
            ["commit", "start", "--paths", "README.md", "--archive-run-id", "legacy"],
            ["commit", "start", "--paths", "README.md", "--backfill"],
        ):
            with self.subTest(arguments=arguments):
                code, result = self.invoke_before_repository(arguments)
                self.assertEqual(code, 1)
                self.assertEqual(result["reason_code"], "state-precondition")
                self.assertTrue(result["message"].startswith("invalid CLI invocation:"))

    @mock.patch.object(CLI.runtime, "MERGE_LIFECYCLE_ACTIVE", True)
    def test_unknown_verbs_use_invalid_invocation_with_retired_options(self):
        for verb, run_id in product((
            [], ["commit"], ["merge", "gate"],
            ["recover"], ["merge", "status"], ["commit", "unknown"], ["unknown"],
            ["merge", "gate", "unknown"], ["merge", "gate", "unknown\nverb"],
        ), ("r1", "../bad\x1b[2J")):
            with self.subTest(verb=verb, run_id=run_id):
                code, result = self.invoke_before_repository(["--run-id", run_id, *verb])
                self.assertEqual(code, 1)
                self.assertEqual(result["reason_code"], "state-precondition")
                with self.assertRaises(CLI.Refusal) as expected:
                    CLI.build_parser().parse_args(verb)
                self.assertEqual(result["message"], expected.exception.message)
                self.assertNotIn("--run-id and --task are not admitted", result["message"])

    def test_start_task_option_is_hidden_and_only_refuses(self):
        with mock.patch.object(CLI.runtime, "MERGE_LIFECYCLE_ACTIVE", True):
            for verb, arguments in (
                ("commit", ["--paths", "README.md"]),
                ("merge", ["--worktree", "/absent"]),
            ):
                for option in ("--task", "--tas", "--t"):
                    with self.subTest(verb=verb, option=option):
                        self.assert_revision9_refusal(
                            [verb, "start", *arguments, option, "t1"],
                            reason="state-precondition",
                            message=(f"forge: {verb} start refused — "
                                     "--run-id and --task are not admitted"),
                        )
                parser = CLI.build_parser()
                commands = next(a for a in parser._actions
                                if isinstance(a, argparse._SubParsersAction))
                starts = next(a for a in commands.choices[verb]._actions
                              if isinstance(a, argparse._SubParsersAction))
                self.assertNotIn("--task", starts.choices["start"].format_help().split(
                    "\nglobal options", 1)[0])

    def test_launch_rejects_abbreviated_task_and_run_options(self):
        arguments = ["launch", "--role", "plan", "--worktree", "/absent", "--brief", "/brief"]
        for option in ("--t", "--tas", "--run", "--run-i"):
            with self.subTest(option=option):
                code, result = self.invoke_before_repository([
                    "--repo", "/absent", "--run-id", "r1", *arguments, option, "t1",
                ])
                self.assertEqual(code, 1)
                self.assertTrue(result["message"].startswith("invalid CLI invocation:"))

    @mock.patch.object(CLI.runtime, "MERGE_LIFECYCLE_ACTIVE", True)
    def test_kept_parsers_retain_abbreviations(self):
        parser = CLI.build_parser()
        self.assertEqual(parser.parse_args(["commit", "start", "--pat", "README.md"]).paths,
                         ["README.md"])
        self.assertEqual(parser.parse_args(["merge", "start", "--work", "/absent"]).worktree,
                         "/absent")
        attached = parser.parse_args(["review", "attach", "--verdict-f", "/verdict"])
        self.assertEqual(attached.verdict_file, "/verdict")
        commands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
        self.assertFalse(commands.choices["launch"].allow_abbrev)

    def test_printable_invalid_invocation_diagnostics_remain_verbatim(self):
        cases = (
            (["commit"], "the following arguments are required: commit_command"),
            (["commit", "start", "--paths", "README.md", "--backfill-approval",
              "printable 'quotes' — café"],
             "unrecognized arguments: --backfill-approval printable 'quotes' — café"),
        )
        for arguments, message in cases:
            with self.subTest(arguments=arguments):
                code, result = self.invoke_before_repository(arguments)
                self.assertEqual(code, 1)
                self.assertEqual(result["message"], f"invalid CLI invocation: {message}")
                self.assertEqual(result["observed"], message)

    def test_hostile_retired_option_value_escapes_only_control_characters(self):
        hostile = "x\x1b[2Jevil\nforge: approved\t\r\x7f\x85"
        message = (r"unrecognized arguments: --backfill-approval "
                   r"x\x1b[2Jevil\x0aforge: approved\x09\x0d\x7f\x85")
        with self.assertRaises(CLI.Refusal) as caught:
            CLI.build_parser().parse_args([
                "commit", "start", "--paths", "README.md", "--backfill-approval", hostile
            ])
        self.assertEqual(caught.exception.message, f"invalid CLI invocation: {message}")
        self.assertEqual(caught.exception.observed, message)
        for json_flag in ([], ["--json"]):
            with self.subTest(json=json_flag):
                result = subprocess.run(
                    [sys.executable, str(CLI_PATH), *json_flag, "commit", "start",
                     "--paths", "README.md", "--backfill-approval", hostile],
                    capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr, b"")
                self.assertNotIn(b"\x1b", result.stdout)
                self.assertNotIn(b"\nforge: approved", result.stdout)
                rendered = (json.loads(result.stdout)["message"] if json_flag
                            else result.stdout.decode())
                self.assertIn(f"invalid CLI invocation: {message}", rendered)

    def test_launch_invalid_run_id_is_redacted(self):
        hostile = b"../bad\x1b[2Jpwn\nforge: approved\x07\xff"
        with tempfile.TemporaryDirectory(prefix="forge-hostile-run-") as directory:
            for json_flag in ([], ["--json"]):
                with self.subTest(json=json_flag):
                    result = subprocess.run(
                        [sys.executable, str(CLI_PATH), *json_flag,
                         "launch", "--run-id", hostile],
                        cwd=directory, capture_output=True, check=False,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stderr, b"")
                    self.assertIn(b"invalid --run-id grammar", result.stdout)
                    self.assertIn(b"state-precondition", result.stdout)
                    self.assertNotIn(b"pwn", result.stdout)
                    self.assertNotIn(b"\x1b", result.stdout)
                    self.assertEqual(list(Path(directory).rglob("*.json*")), [])

    def test_launch_run_grammar_is_load_bearing_before_discovery(self):
        argv = ["--repo", "/absent", "--run-id", "../../outside", "--",
                "launch", "collect", "--execution", "execution-01"]
        self.assert_revision9_refusal(
            argv, reason="state-precondition", message="invalid --run-id grammar",
        )
        with mock.patch.object(package_module("chain_core"), "RUN_ID_RE") as grammar:
            grammar.fullmatch.return_value = True
            with self.assertRaises(AssertionError):
                self.invoke_before_repository(argv)

    def test_hostile_verb_bytes_never_reach_cli_output(self):
        hostile = b"\x1b[2Jpwn\nforge: approved\x07\xff"
        with tempfile.TemporaryDirectory(prefix="forge-hostile-verb-") as directory:
            for prefix, json_flag in product(([], ["commit"], ["merge"]), ([], ["--json"])):
                with self.subTest(prefix=prefix, json=json_flag):
                    result = subprocess.run(
                        [sys.executable, str(CLI_PATH), *json_flag,
                         "--run-id", "r1", *prefix, hostile],
                        cwd=directory, capture_output=True, check=False,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertIn(b"invalid CLI invocation:", result.stdout)
                    self.assertEqual(result.stderr, b"")
                    for unsafe in (b"\x1b", b"\x07", b"\xff", b"\nforge: approved"):
                        self.assertNotIn(unsafe, result.stdout + result.stderr)
                    if not json_flag and prefix != ["merge"]:
                        escaped = b"\\x1b[2Jpwn\\nforge: approved\\x07\\udcff"
                        self.assertIn(escaped, result.stdout)
                    self.assertEqual(list(Path(directory).rglob("*.json*")), [])


class RetiredChainOptionsStorageTests(ChainProcessFixture):
    def test_start_combined_run_task_refusal_creates_no_chain(self):
        for verb, arguments in (
            ("commit", ["--paths", "README.md"]),
            ("merge", ["--worktree", str(self.repo)]),
        ):
            with (self.subTest(verb=verb),
                  mock.patch.object(CLI.runtime, "MERGE_LIFECYCLE_ACTIVE", True)):
                code, result = self.invoke_cli(
                    verb, "start", *arguments, "--run-id=legacy", "--task=task-01",
                )
                self.assertEqual((code, result["reason_code"]), (1, "state-precondition"))
                self.assertEqual(
                    result["message"],
                    f"forge: {verb} start refused — --run-id and --task are not admitted",
                )
                self.assertEqual(list((self.repo / ".forge/chains").rglob("*.json*")), [])

    def test_launch_separators_refuse_before_outside_journal_access(self):
        runs = self.repo / ".codex-orchestrator/runs"
        runs.mkdir(parents=True)
        outside = self.repo / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_bytes(b"outside sentinel must remain untouched\n")
        journal = outside / "journal.jsonl"
        for present, command, equals in product((False, True), (None, "collect", "cancel"),
                                                 (False, True)):
            with self.subTest(journal=present, command=command, equals=equals):
                if present and not journal.exists():
                    journal.write_bytes(b"unreadable outside journal sentinel\n")
                    journal.chmod(0)
                before = {p: p.stat() for p in outside.iterdir()}
                arguments = (["--role", "plan", "--task", "task-01", "--worktree",
                              str(self.repo), "--brief", str(sentinel)] if command is None
                             else [command, "--execution", "execution-01"])
                flags = (["--run-id=../../outside"] if equals else
                         ["--run-id", "../../outside"])
                with mock.patch.object(os, "open", wraps=os.open) as opened:
                    code, result = self.invoke_cli(*flags, "--", "launch", *arguments)
                opened.assert_not_called()
                self.assertEqual((code, result["reason_code"]), (1, "state-precondition"))
                self.assertEqual(result["message"], "invalid --run-id grammar")
                self.assertNotIn("../../outside", json.dumps(result))
                self.assertEqual({p: p.stat() for p in outside.iterdir()}, before)
                self.assertEqual(list(runs.iterdir()), [])
        journal.chmod(0o600)
        self.assertEqual(journal.read_bytes(), b"unreadable outside journal sentinel\n")
        self.assertEqual(sentinel.read_bytes(), b"outside sentinel must remain untouched\n")

    def test_start_prefix_refusals_create_no_chain_or_event_log(self):
        for verb, option, equals, leading in product(
            ("commit", "merge"),
            ("--t", "--ta", "--tas", "--task", "--ru", "--run", "--run-", "--run-i", "--run-id"),
            (False, True), (False, True),
        ):
            with (self.subTest(verb=verb, option=option, equals=equals, leading=leading),
                  mock.patch.object(CLI.runtime, "MERGE_LIFECYCLE_ACTIVE", True)):
                flags = [option + "=t1"] if equals else [option, "t1"]
                start = [verb, "start", "--paths", "README.md"] if verb == "commit" else [
                    verb, "start", "--worktree", str(self.repo),
                ]
                code, result = self.invoke_cli(*(flags + start if leading else start + flags))
                self.assertEqual(code, 1)
                self.assertEqual(result["reason_code"], "state-precondition")
                if option == "--run-id" or (option.startswith("--t") and not leading):
                    self.assertEqual(
                        result["message"],
                        f"forge: {verb} start refused — --run-id and --task are not admitted",
                    )
                else:
                    self.assertTrue(result["message"].startswith("invalid CLI invocation:"))
                self.assertEqual(list((self.repo / ".forge/chains").glob("*.json*")), [])

    def test_separators_refuse_every_run_option_shape_without_chain_or_event_log(self):
        for verb, arguments in (
            ("commit start", ["--paths", "README.md"]),
            ("merge start", ["--worktree", str(self.repo)]),
            ("commit abort", []), ("status", []),
        ):
            for argv in separated_run_options(verb, arguments):
                with (self.subTest(argv=argv),
                      mock.patch.object(CLI.runtime, "MERGE_LIFECYCLE_ACTIVE", True)):
                    code, result = self.invoke_cli(*argv)
                    self.assertEqual(code, 1, result)
                    self.assertEqual(result["reason_code"], "state-precondition")
                    self.assertEqual(
                        result["message"],
                        f"forge: {verb} refused — --run-id and --task are not admitted",
                    )
                    self.assertEqual(list((self.repo / ".forge/chains").rglob("*.json*")), [])


def write_commit_history(store, chain_id, events):
    previous = CLI.ZERO_DIGEST
    for index, event in enumerate(events, 1):
        event["sequence"] = index
        event["prev_digest"] = previous
        unsigned = {name: value for name, value in event.items() if name != "digest"}
        event["digest"] = CLI.sha256_bytes(CLI.canonical_bytes(unsigned))
        previous = event["digest"]
    store.events_path(chain_id).write_bytes(
        b"".join(CLI.canonical_bytes(event) + b"\n" for event in events)
    )
    store.state_path(chain_id).write_bytes(
        CLI.canonical_bytes(events[-1]["payload"]["state"]) + b"\n"
    )


class LegacyCommitReplayTests(ChainProcessFixture):
    def test_partial_legacy_key_sets_freeze_in_reader(self):
        chain_id = self.start_candidate()
        store = CLI.ChainStore(CLI.Repository(self.repo).common_root())
        original = self.events(chain_id)
        for key in ("run_binding", "journal_outbox"):
            with self.subTest(key=key):
                events = copy.deepcopy(original)
                for event in events:
                    event["payload"]["state"][key] = None
                write_commit_history(store, chain_id, events)
                before = (store.state_path(chain_id).read_bytes(),
                          store.events_path(chain_id).read_bytes())
                with self.assertRaisesRegex(
                    CLI.FrozenError, "chain event 1 does not authenticate a commit family"
                ) as caught:
                    store.load(chain_id)
                self.assertEqual(str(caught.exception.__cause__),
                                 "materialized chain state has an invalid top-level key set")
                self.assertEqual(before, (store.state_path(chain_id).read_bytes(),
                                          store.events_path(chain_id).read_bytes()))

    def test_partial_legacy_shape_control_is_load_bearing(self):
        chain_id = self.start_candidate()
        original = self.events(chain_id)[0]["payload"]["state"]
        module = package_module("chain_core._chain_state")
        for key in ("run_binding", "journal_outbox"):
            with self.subTest(key=key):
                state = {**original, key: None}

                def refuses(state=state):
                    with self.assertRaisesRegex(CLI.FrozenError, "invalid top-level key set"):
                        CLI.validate_state(state, chain_id)

                refuses()
                with patch_chain_core("STATE_KEYS", module.STATE_KEYS | {key}):
                    with self.assertRaises(AssertionError):
                        refuses()

    def assert_predicate_rejects(self, store, chain_id, predicate):
        replay = package_module("chain_core._commit_replay")
        before = (store.events_path(chain_id).read_bytes(), store.state_path(chain_id).read_bytes())

        def rejects():
            with self.assertRaises(CLI.FrozenError):
                store.load(chain_id)

        rejects()
        with mock.patch.object(replay, predicate, return_value=True):
            with self.assertRaises(AssertionError):
                rejects()
            self.assertEqual(store.load(chain_id)["chain_id"], chain_id)
        self.assertEqual(
            before,
            (store.events_path(chain_id).read_bytes(), store.state_path(chain_id).read_bytes()),
        )

    def test_produced_commit_requires_a_preceding_matching_identity_event(self):
        chain_id = self.start_candidate(fast=True)
        self.cli("--chain-id", chain_id, "commit", "finalize", "--message", "candidate", expected=0)
        store = CLI.ChainStore(CLI.Repository(self.repo).common_root())
        original = self.events(chain_id)
        for attack in ("missing-event", "different-produced-sha"):
            with self.subTest(attack=attack):
                events = copy.deepcopy(original)
                checked = next(
                    e for e in events if e["payload"]["event"] == "commit_identity_checked"
                )
                if attack == "missing-event":
                    # Smuggle a matching identity into the earlier intent snapshot.
                    # Snapshot equality alone cannot prove an identity-check event existed.
                    intent = next(e for e in events if e["payload"]["event"] == "commit_intent")
                    intent["payload"]["state"]["commit_result"]["identity"] = copy.deepcopy(
                        checked["payload"]["state"]["commit_result"]["identity"]
                    )
                    events.remove(checked)
                else:
                    self.mismatch_produced_identity(events, checked)
                write_commit_history(store, chain_id, events)
                self.assert_predicate_rejects(store, chain_id, "_produced_identity_precedes")

    @staticmethod
    def mismatch_produced_identity(events, checked):
        for event in events:
            if event["payload"]["event"] in {"commit_identity_checked", "authorization_consumed"}:
                identity = event["payload"]["state"]["commit_result"]["identity"]
                identity["produced_sha"] = "f" * 40
        checked["payload"]["details"]["produced_sha"] = "f" * 40

    def test_legacy_events_cannot_change_authority_or_appear_on_new_chains(self):
        chain_id = self.start_candidate()
        store = CLI.ChainStore(CLI.Repository(self.repo).common_root())
        original = self.events(chain_id)
        for name, legacy in product(
            ("journal_receipted", "abort_disposition_recorded"), (False, True)
        ):
            with self.subTest(event=name, legacy=legacy):
                events = copy.deepcopy(original)
                if legacy:
                    for event in events:
                        event["payload"]["state"].update(run_binding=None, journal_outbox=None)
                event = copy.deepcopy(events[-1])
                event["payload"].update(event=name, details={})
                if legacy:
                    event["payload"]["state"]["authorization"] = {"forged": True}
                events.append(event)
                write_commit_history(store, chain_id, events)
                self.assert_predicate_rejects(store, chain_id, "_legacy_fact_valid")

    def legacy_chain(self):
        chain_id = self.start_candidate()
        store = CLI.ChainStore(CLI.Repository(self.repo).common_root())
        events = [
            json.loads(line) for line in store.events_path(chain_id).read_bytes().splitlines()
        ]
        for event in events:
            event["payload"]["state"].update(
                run_binding={"retired": "unavailable run directory"},
                journal_outbox={"retired": "missing batch"},
            )
            event["payload"]["details"].update(
                journal_batch={"retired": True}, source_event_digest="0" * 64
            )
        # Both legacy record names are inert. They cannot introduce an authorization.
        for name in ("abort_disposition_recorded", "journal_receipted"):
            event = copy.deepcopy(events[-1])
            event["payload"]["event"] = name
            event["payload"]["details"] = {"journal_batch": {}, "source_event_digest": "1" * 64}
            events.append(event)
        write_commit_history(store, chain_id, events)
        return store, chain_id, events

    def test_legacy_binding_and_receipts_load_without_journal_or_rewrite(self):
        store, chain_id, _events = self.legacy_chain()
        before = (store.events_path(chain_id).read_bytes(), store.state_path(chain_id).read_bytes())
        with mock.patch.object(sys, "path", [str(CLI_PATH.parents[1]), *sys.path]):
            journal = importlib.import_module("codex_orchestrator.journal")
        with (
            mock.patch.object(journal, "read_journal", side_effect=AssertionError("journal read")),
            mock.patch.object(
                journal, "_open_journal", side_effect=AssertionError("journal write")
            ),
        ):
            loaded = store.load(chain_id)
            code, result = self.invoke_cli("--chain-id", chain_id, "status")
        self.assertEqual(code, 0, result)
        self.assertEqual(loaded["run_binding"], {"retired": "unavailable run directory"})
        self.assertEqual(
            before,
            (store.events_path(chain_id).read_bytes(), store.state_path(chain_id).read_bytes()),
        )

    def test_legacy_binding_does_not_restrict_restage_paths(self):
        store, chain_id, _events = self.legacy_chain()
        path = "new\npath.txt"
        (self.repo / path).write_text("new candidate\n", encoding="utf-8")
        with mock.patch.object(sys, "path", [str(CLI_PATH.parents[1]), *sys.path]):
            journal = importlib.import_module("codex_orchestrator.journal")
        with (
            mock.patch.object(journal, "read_journal", side_effect=AssertionError("journal read")),
            mock.patch.object(
                journal, "_open_journal", side_effect=AssertionError("journal write")
            ),
        ):
            code, result = self.invoke_cli(
                "--chain-id", chain_id, "commit", "restage", "--paths", path
            )
        self.assertEqual(code, 0, result)
        state = store.load(chain_id)
        self.assertEqual(state["paths"], [path])
        self.assertEqual(state["run_binding"], {"retired": "unavailable run directory"})
        self.assertEqual(state["approval"], {})
        self.assertEqual(state["authorization"], {})
        self.assertIsNone(state["review"]["verdict"])

    def test_legacy_event_digest_remains_load_bearing(self):
        store, chain_id, events = self.legacy_chain()
        events[-1]["payload"]["details"]["source_event_digest"] = "2" * 64
        store.events_path(chain_id).write_bytes(
            b"".join(CLI.canonical_bytes(event) + b"\n" for event in events)
        )
        with self.assertRaisesRegex(CLI.FrozenError, "digest is invalid"):
            store.load(chain_id)

    def test_new_chain_omits_legacy_keys_and_never_emits_carriers(self):
        chain_id = self.start_candidate(fast=True)
        self.cli("--chain-id", chain_id, "commit", "finalize", "--message", "candidate", expected=0)
        for event in self.events(chain_id):
            payload = event["payload"]
            self.assertFalse({"run_binding", "journal_outbox"} & set(payload["state"]))
            self.assertNotIn(payload["event"], {"journal_receipted", "abort_disposition_recorded"})
            self.assertFalse({"journal_batch", "source_event_digest"} & set(payload["details"]))

    def test_new_chain_writer_refuses_legacy_members(self):
        source_id = self.start_candidate()
        store = CLI.ChainStore(CLI.Repository(self.repo).common_root())
        state = copy.deepcopy(self.events(source_id)[0]["payload"]["state"])
        state["chain_id"] = "c-2026-10-06T120000Z-dead"
        for key in ("run_binding", "journal_outbox"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "retired state members"):
                store.create({**state, key: None}, "chain_started", {})
        self.assertFalse(store.events_path(state["chain_id"]).exists())

    def test_legacy_history_does_not_authorize_new_retired_events(self):
        store, chain_id, _events = self.legacy_chain()
        state = store.load(chain_id)
        before = store.events_path(chain_id).read_bytes()
        for event, details in (
            ("journal_receipted", {}),
            ("abort_disposition_recorded", {}),
            ("chain_aborted", {"journal_batch": {}}),
            ("chain_aborted", {"source_event_digest": "0" * 64}),
        ):
            with self.subTest(event=event, details=details), self.assertRaises(ValueError):
                store.persist(state, event, details)
        self.assertEqual(store.events_path(chain_id).read_bytes(), before)
