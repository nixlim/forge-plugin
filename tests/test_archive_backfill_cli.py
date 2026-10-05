"""Focused regression tests for retrospective archive CLI validation."""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import subprocess
import textwrap
import unittest
from pathlib import Path
from types import FunctionType, SimpleNamespace
from unittest import mock

from tests import test_archive_backfill as support
from tests._cli_loader import package_module, patch_engine

ARCHIVE = support.ARCHIVE
CLOSING = support.CLOSING
CHAIN_CORE = package_module("chain_core")
CHAIN_STATE = package_module("chain_core._chain_state")
ENGINE = package_module("engine")
ENGINE_ARCHIVE = package_module("engine._archive")
CLI_OPTIONS = support.CLI_OPTIONS
CLI_DISPATCH = support.CLI_DISPATCH
CLI_PARSER = support.CLI_PARSER
CLI_LIFECYCLE = support.CLI_LIFECYCLE

BACKFILL_REFUSAL = support.APPROVAL_REFUSAL
MALFORMED_METADATA_REFUSAL = "forge: archive refused — malformed archive chain metadata"
ARCHIVE_BYTES, ARCHIVE_DIGEST = b"archive\n", hashlib.sha256(b"archive\n").hexdigest()
NORMAL_HEAD, LEGACY_HEAD, ARCHIVING_HEAD = "1" * 40, "2" * 40, "3" * 40


def mutated_function(function: FunctionType, anchor: str, replacement: str) -> FunctionType:
    """Compile one exact in-memory mutant with the function's live globals."""

    source = textwrap.dedent(inspect.getsource(function))
    if source.count(anchor) != 1:
        raise AssertionError(f"mutation anchor drifted for {function.__name__}")
    namespace = dict(function.__globals__)
    exec(compile(source.replace(anchor, replacement, 1), function.__code__.co_filename, "exec"), namespace)  # noqa: S102, E501
    mutant = namespace[function.__name__]
    if isinstance(mutant, property):
        mutant = mutant.fget
    if not isinstance(mutant, FunctionType):
        raise AssertionError(f"mutation did not define {function.__name__}")
    return mutant


def archive_metadata(**updates: object) -> dict[str, object]:
    metadata: dict[str, object] = {"run_id": "run-backfill-metadata", "path": ".forge/history/runs/run-backfill-metadata.md", "closing_head": NORMAL_HEAD, "legacy_recovered_head": None, "legacy_approval": None, "post_close_validation": "/fixture/post-close-validation.json", "dispense_targets": [], "dispense_reason": None, "rendered_sha256": ARCHIVE_DIGEST}  # noqa: E501
    metadata.update(updates)
    return metadata


def valid_metadata_cases() -> tuple[tuple[str, dict[str, object]], ...]:
    normal_11 = archive_metadata(archiving_head=None, backfill_approval=None)
    legacy_9 = archive_metadata(closing_head=None, legacy_recovered_head=LEGACY_HEAD, legacy_approval="recovery-run:decision-01")  # noqa: E501
    legacy_11 = {**legacy_9, "archiving_head": None, "backfill_approval": None}
    backfill = archive_metadata(archiving_head=ARCHIVING_HEAD, backfill_approval="approval-run:decision-01")  # noqa: E501
    return (("nine-key-normal", archive_metadata()), ("nine-key-legacy", legacy_9), ("eleven-key-normal-null-additions", normal_11), ("eleven-key-legacy-null-additions", legacy_11), ("eleven-key-backfill", backfill))  # noqa: E501


def malformed_metadata_cases() -> tuple[tuple[str, dict[str, object]], ...]:
    backfill = archive_metadata(archiving_head=ARCHIVING_HEAD, backfill_approval="approval-run:decision-01")  # noqa: E501
    legacy_backfill = {**backfill, "legacy_recovered_head": LEGACY_HEAD, "legacy_approval": "recovery-run:decision-01"}  # noqa: E501
    ten_keys = archive_metadata(archiving_head=None)
    return (("backfill-null-archiving-head", {**backfill, "archiving_head": None}), ("normal-with-nonnull-addition", archive_metadata(archiving_head=ARCHIVING_HEAD, backfill_approval=None)), ("backfill-combined-with-legacy", legacy_backfill), ("ten-key-shape", ten_keys), ("legacy-with-backfill-addition", archive_metadata(closing_head=None, legacy_recovered_head=LEGACY_HEAD, legacy_approval="recovery-run:decision-01", archiving_head=ARCHIVING_HEAD, backfill_approval=None)), ("empty-backfill-approval", {**backfill, "backfill_approval": ""}), ("normal-invalid-closing-head", archive_metadata(closing_head="bad")), ("legacy-invalid-recovered-head", archive_metadata(closing_head=None, legacy_recovered_head="bad", legacy_approval="recovery-run:decision-01")), ("legacy-nonstring-approval", archive_metadata(closing_head=None, legacy_recovered_head=LEGACY_HEAD, legacy_approval=7)), ("backfill-invalid-closing-head", {**backfill, "closing_head": "bad"}), ("backfill-nonstring-approval", {**backfill, "backfill_approval": 7}))  # noqa: E501


class ArchiveMetadataValidationTests(unittest.TestCase):
    def test_all_metadata_modes_are_accepted_by_the_shared_validator(self) -> None:
        self.assertIs(CHAIN_STATE._archive_metadata_mode_is_valid, ENGINE_ARCHIVE._archive_metadata_mode_is_valid)  # noqa: E501
        validators = (CHAIN_STATE._archive_metadata_mode_is_valid, ENGINE_ARCHIVE._archive_metadata_mode_is_valid)  # noqa: E501
        for name, metadata in valid_metadata_cases():
            for validator in validators:
                with self.subTest(name=name, module=validator.__module__):
                    self.assertTrue(validator(metadata))

    def test_each_malformed_shape_refuses_exactly_and_disable_leg_escapes(self) -> None:
        state_template = {"chain_id": "c-2026-10-05T120000Z-cafe", "state": "verifying"}  # noqa: E501
        repository = SimpleNamespace(root=Path("/fixture/repository"), git=mock.Mock(return_value=subprocess.CompletedProcess([], 1, b"", b"")))  # noqa: E501
        context = SimpleNamespace(repo=repository)

        def validator_mutant(_metadata):
            return True

        for name, metadata in malformed_metadata_cases():
            state = {**state_template, "staging": {"archive": metadata}}
            with self.subTest(name=name):
                self.assertFalse(CHAIN_STATE._archive_metadata_mode_is_valid(metadata))
                self.assertFalse(ENGINE_ARCHIVE._archive_metadata_mode_is_valid(metadata))
                with self.assertRaises(ENGINE_ARCHIVE.Refusal) as raised:
                    ENGINE_ARCHIVE._archive_recheck(context, state, "authorization", require_staged=False)  # noqa: E501
                self.assertEqual(raised.exception.message, MALFORMED_METADATA_REFUSAL)
                self.assertTrue(validator_mutant(metadata))
                with self._recheck_dependencies(), mock.patch.object(ENGINE_ARCHIVE, "_archive_metadata_mode_is_valid", validator_mutant):  # noqa: E501
                    ENGINE_ARCHIVE._archive_recheck(context, state, "authorization", require_staged=False)  # noqa: E501
        with self.assertRaises(ENGINE_ARCHIVE.Refusal): ENGINE_ARCHIVE._archive_recheck(context, {**state_template, "staging": {"archive": 7}}, "authorization", require_staged=False)  # noqa: E701, E501

    def test_validate_state_refuses_malformed_archive_shape_with_disable_leg(self) -> None:
        metadata = archive_metadata(archiving_head=None)
        state = ENGINE._new_state("c-2026-10-05T120000Z-cafe", SimpleNamespace(root=Path("/fixture/repository")), NORMAL_HEAD, SimpleNamespace(sha=LEGACY_HEAD, digest="4" * 64), [str(metadata["path"])], None)  # noqa: E501
        state["staging"]["archive"] = metadata

        with self.assertRaises(CHAIN_STATE.FrozenError) as raised:
            CHAIN_STATE.validate_state(state)
        self.assertEqual(raised.exception.message, "chain archive metadata is malformed")  # noqa: E501
        mutant = mutated_function(CHAIN_STATE.validate_state, "            or not _archive_metadata_mode_is_valid(archive)\n", "")  # noqa: E501
        self.assertIs(mutant(state), state)

    def test_legacy_metadata_requires_null_backfill_additions(self) -> None:
        metadata = dict(valid_metadata_cases()[3][1])
        metadata["archiving_head"] = ARCHIVING_HEAD
        self.assertFalse(CHAIN_STATE._archive_metadata_mode_is_valid(metadata))
        mutant = mutated_function(CHAIN_STATE._archive_metadata_mode_is_valid, "        and bool(archive.get(\"legacy_approval\"))\n        and additions_are_null\n", "        and bool(archive.get(\"legacy_approval\"))\n")  # noqa: E501
        self.assertTrue(mutant(metadata))

    def test_null_backfill_addition_does_not_select_backfill_mode(self) -> None:
        mutant = mutated_function(ENGINE_ARCHIVE._archive_metadata_is_backfill, 'return metadata.get("backfill_approval") is not None', 'return "backfill_approval" in metadata')  # noqa: E501
        for name, metadata in valid_metadata_cases()[2:4]:
            with self.subTest(name=name):
                self.assertFalse(ENGINE_ARCHIVE._archive_metadata_is_backfill(metadata))
                self.assertTrue(mutant(metadata))

    @staticmethod
    @contextlib.contextmanager
    def _recheck_dependencies():
        with mock.patch.object(ENGINE_ARCHIVE.chain_core, "_validated_commitment_path", return_value=Path("/fixture/candidate")), mock.patch.object(ENGINE_ARCHIVE, "_render_archive_bytes", return_value=ARCHIVE_BYTES), mock.patch.object(ENGINE_ARCHIVE, "_read_archive_candidate", return_value=ARCHIVE_BYTES):  # noqa: E501
            yield


class OrdinaryCommitStartBackfillFlagTests(unittest.TestCase):
    def setUp(self) -> None:
        self.arguments = CLI_PARSER.build_parser().parse_args(["commit", "start", "--paths", "tracked.txt", "--backfill-closing-head", NORMAL_HEAD, "--backfill-approval", "approval-run:decision-01"])  # noqa: E501
        self.options = CHAIN_CORE.CLIOptions()

    def test_pre_discovery_validator_refuses_and_its_disable_mutant_admits(self) -> None:
        with self.assertRaises(CLI_OPTIONS.Refusal) as raised:
            CLI_OPTIONS._validate_revision9_cross_options(self.options, self.arguments)
        self.assertEqual(raised.exception.message, BACKFILL_REFUSAL)
        mutant = mutated_function(CLI_OPTIONS._validate_revision9_cross_options, "    if args.archive_run_id is None and (\n        any(backfill_pair)\n    ):\n", "    if False:\n")  # noqa: E501
        mutant(self.options, self.arguments)

    def test_dispatch_refuses_and_its_independent_disable_mutant_starts(self) -> None:
        sentinel = object()
        command_engine = SimpleNamespace(ctx=SimpleNamespace(options=self.options), start=mock.Mock(return_value=sentinel))  # noqa: E501
        with self.assertRaises(CLI_DISPATCH.Refusal) as raised:
            CLI_DISPATCH._dispatch_commit_start(command_engine, self.arguments)
        self.assertEqual(raised.exception.message, BACKFILL_REFUSAL)
        command_engine.start.assert_not_called()

        mutant = mutated_function(CLI_DISPATCH._dispatch_commit_start, "    if args.archive_run_id is None and any(backfill_pair):\n", "    if False:\n")  # noqa: E501
        self.assertIs(mutant(command_engine, self.arguments), sentinel)
        command_engine.start.assert_called_once()

    def test_shared_closing_validator_call_sites_have_disable_legs(self) -> None:
        arguments = CLI_PARSER.build_parser().parse_args(["commit", "start", "--archive-run-id", "run-archive", "--closing-head", NORMAL_HEAD, "--legacy-recovered-head", LEGACY_HEAD, "--legacy-approval", "approval-run:decision-01"])  # noqa: E501
        for function, parameters in ((CLI_OPTIONS._validate_revision9_cross_options, (self.options, arguments)), (CLI_DISPATCH._dispatch_commit_start, (None, arguments))):  # noqa: E501
            command_engine = SimpleNamespace(ctx=SimpleNamespace(options=CHAIN_CORE.CLIOptions()), start=mock.Mock(return_value="started"))  # noqa: E501
            if parameters[0] is None: parameters = (command_engine, arguments)  # noqa: E701
            with self.subTest(function=function.__module__), self.assertRaises(CLI_OPTIONS.Refusal):  # noqa: E501
                function(*parameters)
            mutant = mutated_function(function, "    legacy_pair, backfill_pair = _validate_commit_start_closing_options(args)\n", "    legacy_pair = (True, True)\n    backfill_pair = (False, False)\n")  # noqa: E501
            if function is CLI_OPTIONS._validate_revision9_cross_options:
                mutant(*parameters)
            else:
                self.assertEqual(mutant(*parameters), "started")

    def test_shared_closing_validator_guards_have_disable_legs(self) -> None:
        cases = (
            (["--closing-head", NORMAL_HEAD, "--backfill-closing-head", LEGACY_HEAD, "--backfill-approval", "run:decision"], "    if any(backfill_pair) and (\n        args.closing_head is not None or any(legacy_pair)\n    ):\n"),  # noqa: E501
            (["--backfill-closing-head", LEGACY_HEAD], "    if backfill_pair[0] != backfill_pair[1]:\n"),  # noqa: E501
            (["--closing-head", NORMAL_HEAD, "--legacy-recovered-head", LEGACY_HEAD, "--legacy-approval", "run:decision"], "    if args.closing_head is not None and any(legacy_pair):\n"),  # noqa: E501
        )
        for options, anchor in cases:
            arguments = CLI_PARSER.build_parser().parse_args(["commit", "start", "--archive-run-id", "run-archive", *options])  # noqa: E501
            with self.subTest(options=options), self.assertRaises(CLI_OPTIONS.Refusal):
                CLI_OPTIONS._validate_commit_start_closing_options(arguments)
            mutant = mutated_function(CLI_OPTIONS._validate_commit_start_closing_options, anchor, "    if False:\n")  # noqa: E501
            self.assertEqual(len(mutant(arguments)), 2)

    def test_ordinary_closing_head_guards_have_disable_legs(self) -> None:
        arguments = CLI_PARSER.build_parser().parse_args(["commit", "start", "--paths", "tracked.txt", "--closing-head", NORMAL_HEAD])  # noqa: E501
        command_engine = SimpleNamespace(ctx=SimpleNamespace(options=CHAIN_CORE.CLIOptions()), start=mock.Mock(return_value="started"))  # noqa: E501
        cases = ((CLI_OPTIONS._validate_revision9_cross_options, (self.options, arguments)), (CLI_DISPATCH._dispatch_commit_start, (command_engine, arguments)))  # noqa: E501
        for function, parameters in cases:
            with self.subTest(function=function.__module__), self.assertRaises(CLI_OPTIONS.Refusal):  # noqa: E501
                function(*parameters)
            mutant = mutated_function(function, "        args.closing_head is not None\n", "        False\n")  # noqa: E501
            result = mutant(*parameters)
            if function is CLI_DISPATCH._dispatch_commit_start:
                self.assertEqual(result, "started")

    def test_dispatch_forwards_explicit_closing_head_with_disable_leg(self) -> None:
        arguments = CLI_PARSER.build_parser().parse_args(["commit", "start", "--archive-run-id", "run-archive", "--closing-head", NORMAL_HEAD])  # noqa: E501
        command_engine = SimpleNamespace(ctx=SimpleNamespace(options=CHAIN_CORE.CLIOptions()), start=mock.Mock(return_value="started"))  # noqa: E501
        CLI_DISPATCH._dispatch_commit_start(command_engine, arguments)
        self.assertEqual(command_engine.start.call_args.kwargs["closing_head"], NORMAL_HEAD)
        command_engine.start.reset_mock()
        mutant = mutated_function(CLI_DISPATCH._dispatch_commit_start, "        closing_head=args.closing_head,\n", "        closing_head=None,\n")  # noqa: E501
        mutant(command_engine, arguments)
        self.assertIsNone(command_engine.start.call_args.kwargs["closing_head"])


class ArchiveParserGuardAuditTests(unittest.TestCase):
    def test_backfill_values_that_look_like_options_are_preserved(self) -> None:
        for option, value in (
            ("--backfill-closing-head", "--json"),
            ("--backfill-approval", "--repo=literal"),
        ):
            expected = [f"{option}={value}"]
            with self.subTest(option=option):
                _options, remaining = CLI_PARSER._extract_global_options([option, value])
                self.assertEqual(remaining, expected)
                mutant = mutated_function(
                    CLI_PARSER._extract_global_options,
                    f'        "{option}",\n',
                    "",
                )
                _mutant_options, mutant_remaining = mutant([option, value])
                self.assertNotEqual(mutant_remaining, expected)

    def test_new_closing_flags_select_v2_without_archive_id(self) -> None:
        def schema(function, arguments):
            rendered = mock.Mock()
            with patch_engine("render", rendered):
                function(arguments)
            return rendered.call_args.args[0].schema

        for option in ("--closing-head", "--backfill-closing-head", "--backfill-approval"):
            arguments = ["commit", "start", option]
            with self.subTest(option=option):
                mutant = mutated_function(CLI_DISPATCH.main, f'                    "{option}",\n', "")  # noqa: E501
                self.assertEqual(schema(CLI_DISPATCH.main, arguments), CLI_DISPATCH.REVISION9_OUTPUT_SCHEMA)  # noqa: E501
                self.assertNotEqual(schema(mutant, arguments), CLI_DISPATCH.REVISION9_OUTPUT_SCHEMA)  # noqa: E501
        startswith_mutant = mutated_function(CLI_DISPATCH.main, '                token == name or token.startswith(f"{name}=")\n', "                token == name\n")  # noqa: E501
        for option, value in (("--closing-head", NORMAL_HEAD), ("--backfill-closing-head", NORMAL_HEAD), ("--backfill-approval", "run:decision")):  # noqa: E501
            arguments = ["commit", "start", f"{option}={value}", "--paths"]
            with self.subTest(equals=option):
                self.assertEqual(schema(CLI_DISPATCH.main, arguments), CLI_DISPATCH.REVISION9_OUTPUT_SCHEMA)  # noqa: E501
                self.assertNotEqual(schema(startswith_mutant, arguments), CLI_DISPATCH.REVISION9_OUTPUT_SCHEMA)  # noqa: E501


class ArchiveReasonGrammarTests(support.GitBackfillFixture):
    def closing_services(self) -> object:
        return CLOSING.ClosingServices(self.run_git, lambda _path: ([], b""), lambda records, kind: next(record for record in records if record.get("type") == kind), lambda _code: None, frozenset({"legacy-approval"}))  # noqa: E501

    def resolution(self, reason: str) -> str:
        return (
            f"backfill-archive: {self.run_dir.name} closing HEAD {self.closing}; "
            f"archive HEAD {self.archive_head}; judgment passed; {reason}"
        )

    def backfill_mode(self, reason: str, *, disable_reason_check: bool = False):
        evidence = SimpleNamespace(decision={"resolution": self.resolution(reason)})
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(CLOSING, "_approval_evidence", return_value=evidence))  # noqa: E501
            if disable_reason_check:
                stack.enter_context(mock.patch.object(CLOSING, "_backfill_reason_is_valid", return_value=True))  # noqa: E501
            return CLOSING.backfill_closing_mode(self.repo, self.run_dir, self.records(), self.closing, "approval-run:decision-01", self.closing_services())  # noqa: E501

    def test_legacy_reason_preserves_parent_whitespace_padding_behavior(self) -> None:
        reason = "  operator approved recovery  "
        resolution = f"legacy-archive-recovery: {self.run_dir.name} recovered closing HEAD {self.closing}; {reason}"  # noqa: E501
        evidence = SimpleNamespace(decision={"resolution": resolution})
        request = CLOSING.LegacyRequest(self.records(), self.closing, "approval-run:decision-01", True)  # noqa: E501
        with mock.patch.object(CLOSING, "_approval_evidence", return_value=evidence):
            mode = CLOSING.legacy_closing_mode(self.repo, self.run_dir, request, self.closing_services())  # noqa: E501
        self.assertEqual(mode.legacy_approval, "approval-run:decision-01")

        strict_mutant = mutated_function(CLOSING.legacy_closing_mode, '        if not reason.strip() or "\\r" in reason or "\\n" in reason:\n', "        if (\n            not reason.strip()\n            or reason != reason.strip()\n            or \"\\r\" in reason\n            or \"\\n\" in reason\n        ):\n")  # noqa: E501
        strict_mutant.__globals__["_approval_evidence"] = mock.Mock(return_value=evidence)
        with mock.patch.object(CLOSING, "_approval_evidence", return_value=evidence), self.assertRaises(CLOSING.ArchiveRefusal) as raised:  # noqa: E501
            strict_mutant(self.repo, self.run_dir, request, self.closing_services())  # noqa: E501
        self.assertEqual(raised.exception.message, CLOSING.LEGACY_APPROVAL_REFUSAL)
        for invalid, anchor in (("   ", "not reason.strip() or "), ("approved\rforged", ' or "\\r" in reason')):  # noqa: E501
            invalid_evidence = SimpleNamespace(decision={"resolution": f"legacy-archive-recovery: {self.run_dir.name} recovered closing HEAD {self.closing}; {invalid}"})  # noqa: E501
            with mock.patch.object(CLOSING, "_approval_evidence", return_value=invalid_evidence): self.assert_refusal(CLOSING.LEGACY_APPROVAL_REFUSAL, lambda: CLOSING.legacy_closing_mode(self.repo, self.run_dir, request, self.closing_services()))  # noqa: E701, E501
            invalid_mutant = mutated_function(CLOSING.legacy_closing_mode, anchor, ""); invalid_mutant.__globals__["_approval_evidence"] = mock.Mock(return_value=invalid_evidence)  # noqa: E702, E501
            self.assertIsInstance(invalid_mutant(self.repo, self.run_dir, request, self.closing_services()), CLOSING.ClosingMode)  # noqa: E501
        prefix = f"legacy-archive-recovery: {self.run_dir.name} recovered closing HEAD {self.closing}; "  # noqa: E501
        for invalid, anchor, escaped in ((object(), "isinstance(resolution, str) and ", AttributeError), ("x" * len(prefix) + "forged", " and resolution.startswith(prefix)", type(None))):  # noqa: E501
            invalid_evidence = SimpleNamespace(decision={"resolution": invalid}); mutant = mutated_function(CLOSING.legacy_closing_mode, anchor, "")  # noqa: E702, E501
            with mock.patch.object(CLOSING, "_approval_evidence", return_value=invalid_evidence): self.assert_refusal(CLOSING.LEGACY_APPROVAL_REFUSAL, lambda: CLOSING.legacy_closing_mode(self.repo, self.run_dir, request, self.closing_services()))  # noqa: E701, E501
            mutant.__globals__["_approval_evidence"] = mock.Mock(return_value=invalid_evidence)
            if escaped is type(None): self.assertIsInstance(mutant(self.repo, self.run_dir, request, self.closing_services()), CLOSING.ClosingMode)  # noqa: E701, E501
            else:
                with self.assertRaises(escaped): mutant(self.repo, self.run_dir, request, self.closing_services())  # noqa: E701, E501

    def test_backfill_padded_reason_is_preserved(self) -> None:
        reason = "  operator approved backfill  "
        mode = self.backfill_mode(reason)
        self.assertEqual(mode.backfill_reason, reason)

    def test_backfill_whitespace_only_reason_refuses_and_disable_leg_admits(self) -> None:
        reason = "   "
        with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
            self.backfill_mode(reason)
        self.assertEqual(raised.exception.message, BACKFILL_REFUSAL)
        disabled = self.backfill_mode(reason, disable_reason_check=True)
        self.assertEqual(disabled.backfill_reason, reason)

    def test_backfill_reason_must_be_nonempty(self) -> None:
        with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
            self.backfill_mode("")
        self.assertEqual(raised.exception.message, BACKFILL_REFUSAL)

    def test_every_forbidden_control_scalar_refuses_and_disable_leg_admits(self) -> None:
        codepoints = (
            *range(0x00, 0x20),
            0x7F,
            *range(0x80, 0xA0),
            0x2028,
            0x2029,
        )
        for codepoint in codepoints:
            reason = f"approved{chr(codepoint)}forged provenance"
            with self.subTest(codepoint=f"U+{codepoint:04X}"):
                with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
                    self.backfill_mode(reason)
                self.assertEqual(raised.exception.message, BACKFILL_REFUSAL)
                disabled = self.backfill_mode(reason, disable_reason_check=True)
                self.assertEqual(disabled.backfill_reason, reason)


class ArchiveClosingMetadataTests(unittest.TestCase):
    def test_malformed_backfill_oid_refuses_and_disable_leg_admits(self) -> None:
        context = SimpleNamespace(repo=SimpleNamespace(head=mock.Mock(return_value=ARCHIVING_HEAD)))  # noqa: E501
        options = ENGINE_ARCHIVE.ArchiveClosingOptions(backfill_closing_head="not-an-object-id", backfill_approval="approval-run:decision-01")  # noqa: E501
        with self.assertRaises(ENGINE_ARCHIVE.Refusal) as raised:
            ENGINE_ARCHIVE._archive_closing_metadata(context, options)
        self.assertEqual(raised.exception.message, BACKFILL_REFUSAL)

        with mock.patch.object(ENGINE_ARCHIVE, "_archive_oid", return_value=True):
            metadata = ENGINE_ARCHIVE._archive_closing_metadata(context, options)
        self.assertEqual(metadata["closing_head"], "not-an-object-id")
        self.assertEqual(metadata["archiving_head"], ARCHIVING_HEAD)

    def test_every_engine_closing_mode_guard_has_a_disable_leg(self) -> None:
        context = SimpleNamespace(repo=SimpleNamespace(head=mock.Mock(return_value=ARCHIVING_HEAD)))  # noqa: E501
        legacy_refusal = "forge: archive refused — legacy recovery approval missing or mismatched"
        cases = (
            ("backfill-conflict", ENGINE_ARCHIVE.ArchiveClosingOptions(closing_head=ARCHIVING_HEAD, backfill_closing_head=NORMAL_HEAD, backfill_approval="approval-run:decision-01"), support.MODE_CONFLICT, "    if any(backfill_pair) and (\n        options.closing_head is not None or any(legacy_pair)\n    ):\n"),  # noqa: E501
            ("backfill-half-pair", ENGINE_ARCHIVE.ArchiveClosingOptions(backfill_closing_head=NORMAL_HEAD), BACKFILL_REFUSAL, "    if backfill_pair[0] != backfill_pair[1]:\n"),  # noqa: E501
            ("empty-backfill-approval", ENGINE_ARCHIVE.ArchiveClosingOptions(backfill_closing_head=NORMAL_HEAD, backfill_approval=""), BACKFILL_REFUSAL, "            or not options.backfill_approval\n"),  # noqa: E501
            ("invalid-legacy-head", ENGINE_ARCHIVE.ArchiveClosingOptions(legacy_recovered_head="not-an-oid", legacy_approval="approval-run:decision-01"), legacy_refusal, "    if legacy_pair[0] != legacy_pair[1] or (\n        options.legacy_recovered_head is not None\n        and not _archive_oid(options.legacy_recovered_head)\n    ):\n"),  # noqa: E501
            ("normal-legacy-conflict", ENGINE_ARCHIVE.ArchiveClosingOptions(closing_head=ARCHIVING_HEAD, legacy_recovered_head=LEGACY_HEAD, legacy_approval="approval-run:decision-01"), legacy_refusal, "        if options.closing_head is not None or not options.legacy_approval:\n"), ("empty-legacy-approval", ENGINE_ARCHIVE.ArchiveClosingOptions(legacy_recovered_head=LEGACY_HEAD, legacy_approval=""), legacy_refusal, " or not options.legacy_approval"),  # noqa: E501
        )
        for name, options, expected, anchor in cases:
            with self.subTest(name=name), self.assertRaises(ENGINE_ARCHIVE.Refusal) as raised:  # noqa: E501
                ENGINE_ARCHIVE._archive_closing_metadata(context, options)
            self.assertEqual(raised.exception.message, expected)
            replacement = anchor[: len(anchor) - len(anchor.lstrip())] + "if False:\n" if anchor.lstrip().startswith("if ") else anchor.replace("or not options.backfill_approval", "or False").replace("or not options.legacy_approval", "or False")  # noqa: E501
            mutant = mutated_function(ENGINE_ARCHIVE._archive_closing_metadata, anchor, replacement)  # noqa: E501
            self.assertIsInstance(mutant(context, options), dict)

    def test_backfill_classifier_routes_renderer_arguments_with_disable_leg(self) -> None:
        metadata = archive_metadata(archiving_head=ARCHIVING_HEAD, backfill_approval="approval-run:decision-01")  # noqa: E501
        renderer = SimpleNamespace(render_archive_candidate=mock.Mock(return_value=ARCHIVE_BYTES))  # noqa: E501
        context = SimpleNamespace(repo=SimpleNamespace(root=Path("/fixture/repository")), store=SimpleNamespace(common_root=Path("/fixture/common")))  # noqa: E501
        with mock.patch.object(ENGINE_ARCHIVE, "_archive_module", return_value=renderer):
            self.assertEqual(ENGINE_ARCHIVE._render_archive_bytes(context, metadata), ARCHIVE_BYTES)  # noqa: E501
            self.assertEqual(renderer.render_archive_candidate.call_args.kwargs["backfill_closing_head"], NORMAL_HEAD)  # noqa: E501
            mutant = mutated_function(ENGINE_ARCHIVE._render_archive_bytes, "    backfill = _archive_metadata_is_backfill(metadata)\n", "    backfill = False\n")  # noqa: E501
            renderer.render_archive_candidate.reset_mock()
            mutant(context, metadata)
        self.assertIsNone(renderer.render_archive_candidate.call_args.kwargs["backfill_closing_head"])  # noqa: E501

    def test_lifecycle_rejects_non_string_pinned_head_with_disable_leg(self) -> None:
        repository = SimpleNamespace(root=Path("/fixture/repo"), staged_paths=lambda: [], policy=mock.Mock(side_effect=RuntimeError("policy reached")))  # noqa: E501
        store = SimpleNamespace(admission_lock=lambda _root: contextlib.nullcontext())
        command = SimpleNamespace(ctx=SimpleNamespace(repo=repository, store=store), _live_chain=lambda: None)  # noqa: E501
        metadata = {"archiving_head": 7, "backfill_approval": "approval:decision"}
        with support.patch_engine("_run_halt"), support.patch_engine("_prepare_archive_candidate", return_value=(["archive.md"], metadata)):  # noqa: E501
            with self.assertRaises(CHAIN_STATE.FrozenError) as raised:
                CLI_LIFECYCLE.start(command, (), None, archive_run_id="run-backfill")
            self.assertEqual(raised.exception.message, "backfill archive metadata has no pinned repository HEAD")  # noqa: E501
            mutant = mutated_function(CLI_LIFECYCLE.start, "        if pinned_archive_head is not None and not isinstance(\n            pinned_archive_head, str\n        ):\n", "        if False:\n")  # noqa: E501
            with self.assertRaisesRegex(RuntimeError, "policy reached"):
                mutant(command, (), None, archive_run_id="run-backfill")
        repository.policy.assert_called_once_with(7)


class ArchiveCommitStartClosingHeadTests(support.GitBackfillFixture):
    INVALID_REFUSAL = "forge: archive refused — invalid closing HEAD"
    MISMATCH_REFUSAL = (
        "forge: archive refused — closing HEAD does not match repository HEAD"
    )

    def context(self) -> SimpleNamespace:
        return SimpleNamespace(repo=CHAIN_CORE.Repository(self.repo))

    @staticmethod
    def closing_options(closing_head: str) -> object:
        return ENGINE_ARCHIVE.ArchiveClosingOptions(closing_head=closing_head)

    def test_malformed_closing_heads_refuse_exactly_and_format_mutant_fails(self) -> None:
        repository_head = self.archive_head
        object_format = self.git_text("rev-parse", "--show-object-format")
        wrong_length = {"sha1": 64, "sha256": 40}[object_format]
        malformed = {
            "short": repository_head[:7],
            "uppercase": "A" * len(repository_head),
            "non-hex": "g" * len(repository_head),
            "wrong-algorithm-length": "0" * wrong_length,
        }
        context = self.context()
        for name, closing_head in malformed.items():
            with self.subTest(name=name), self.assertRaises(
                ENGINE_ARCHIVE.Refusal
            ) as raised:
                ENGINE_ARCHIVE._archive_closing_metadata(
                    context,
                    self.closing_options(closing_head),
                )
            self.assertEqual(raised.exception.message, self.INVALID_REFUSAL)

        mutant = mutated_function(
            ENGINE_ARCHIVE._archive_closing_metadata,
            "    if normal_closing_head is not None and (\n"
            "        not _archive_oid(normal_closing_head)\n"
            "        or len(normal_closing_head) != len(repository_head)\n"
            "    ):\n",
            "    if False:\n",
        )
        for name, closing_head in malformed.items():
            with self.subTest(mutant=name), self.assertRaises(
                ENGINE_ARCHIVE.Refusal
            ) as raised:
                mutant(context, self.closing_options(closing_head))
            self.assertEqual(raised.exception.message, self.MISMATCH_REFUSAL)

    def test_non_head_refuses_exactly_and_equality_mutant_admits(self) -> None:
        context = self.context()
        options = self.closing_options(self.closing)
        with self.assertRaises(ENGINE_ARCHIVE.Refusal) as raised:
            ENGINE_ARCHIVE._archive_closing_metadata(context, options)
        self.assertEqual(raised.exception.message, self.MISMATCH_REFUSAL)

        mutant = mutated_function(
            ENGINE_ARCHIVE._archive_closing_metadata,
            "    if recorded_closing_head != repository_head:\n",
            "    if False:\n",
        )
        metadata = mutant(context, options)
        self.assertEqual(metadata["closing_head"], self.closing)

    def test_repository_head_is_accepted(self) -> None:
        metadata = ENGINE_ARCHIVE._archive_closing_metadata(
            self.context(),
            self.closing_options(self.archive_head),
        )
        self.assertEqual(metadata["closing_head"], self.archive_head)


class RecordedRepositoryEncodingTests(support.GitBackfillFixture):
    def test_lone_surrogate_refuses_exactly_and_disable_leg_admits(self) -> None:
        recorded = self.repo / ".worktrees" / "retired\udcff-task"
        with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
            ARCHIVE.recorded_repository_provenance(
                self.repo, self.run_dir, str(recorded)
            )
        self.assertEqual(raised.exception.message, support.REPOSITORY_REFUSAL)
        mutant = mutated_function(
            ARCHIVE.recorded_repository_provenance,
            '    try:\n        rendered.encode("utf-8")\n'
            "    except UnicodeError as exc:\n"
            "        raise ArchiveRefusal(refusal) from exc\n",
            "",
        )
        self.assertIn("retired\udcff-task", mutant(self.repo, self.run_dir, str(recorded)))


class BlockedRenderPathTests(support.GitBackfillFixture):
    def blocked_records(self) -> list[dict[str, object]]:
        return self.records(judgment="blocked", chains=())

    def direct_render(self, renderer: FunctionType, closing: object) -> str:
        return renderer(repo=self.repo, run_dir=self.run_dir, records=self.blocked_records(), closing=closing, post_close=dict(support.GATED_PAYLOAD), audit_fragment="## Commitment audit\n", package=ARCHIVE.ChainPackage(None, None, (), ()), bindings=ARCHIVE.binding_history.ResolvedBindings({}, {}), discrepancies=[], documents=())  # noqa: E501

    def candidate_patches(self, resolution: str):
        records = self.blocked_records()
        raw = b"".join(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n" for record in records)  # noqa: E501
        completed = subprocess.CompletedProcess([], 0, b"", b"")
        return records, (mock.patch.object(ARCHIVE, "stable_archive_journal_snapshot", return_value=(records, raw, None)), mock.patch.object(CLOSING, "_approval_evidence", return_value=SimpleNamespace(decision={"resolution": resolution})), mock.patch.object(ARCHIVE, "run_git", return_value=completed))  # noqa: E501

    def render_candidate(self, renderer: FunctionType, *, legacy: bool, resolution: str) -> bytes:  # noqa: E501
        _records, patches = self.candidate_patches(resolution)
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            return renderer(repo=self.repo, run_dir=self.run_dir, closing_head=None if legacy else self.archive_head, legacy_recovered_head=self.closing if legacy else None, legacy_approval="approval-run:decision-01" if legacy else None, backfill_closing_head=None, backfill_approval=None, archiving_head=None, post_close_validation=self.base / "post-close.json", dispense_targets=(), dispense_reason=None, prove_legacy_approval=True)  # noqa: E501

    def legacy_resolution(self) -> str:
        return f"legacy-archive-recovery: {self.run_dir.name} recovered closing HEAD {self.closing}; approved recovery"  # noqa: E501

    def test_render_archive_refuses_blocked_normal_and_legacy_modes(self) -> None:
        modes = (CLOSING.ClosingMode(self.archive_head), CLOSING.ClosingMode(self.closing, legacy_approval="approval-run:decision-01"))  # noqa: E501
        for mode in modes:
            with self.subTest(mode=mode), self.assertRaises(CLOSING.ArchiveRefusal) as raised:  # noqa: E501
                self.direct_render(ARCHIVE.render_archive, mode)
            self.assertEqual(raised.exception.message, support.BLOCKED_REFUSAL)

        mutant = mutated_function(ARCHIVE.render_archive, "    closing_engine.require_passed_without_backfill(" 'closing, closed.get("judgment"))\n', "")  # noqa: E501
        for mode in modes:
            with self.subTest(mutant=mode):
                self.assertIn("## Provenance", self.direct_render(mutant, mode))

    def test_candidate_refuses_blocked_normal_and_valid_legacy_modes(self) -> None:
        resolution = self.legacy_resolution()
        for legacy in (False, True):
            with self.subTest(legacy=legacy), self.assertRaises(CLOSING.ArchiveRefusal) as raised:  # noqa: E501
                self.render_candidate(ARCHIVE._render_archive_candidate, legacy=legacy, resolution=resolution)  # noqa: E501
            self.assertEqual(raised.exception.message, support.BLOCKED_REFUSAL)

    def test_legacy_approval_precedes_and_valid_approval_reaches_blocked_check(self) -> None:
        with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
            self.render_candidate(ARCHIVE._render_archive_candidate, legacy=True, resolution="not a legacy approval")  # noqa: E501
        self.assertEqual(raised.exception.message, CLOSING.LEGACY_APPROVAL_REFUSAL)
        with self.assertRaises(CLOSING.ArchiveRefusal) as blocked:
            self.render_candidate(ARCHIVE._render_archive_candidate, legacy=True, resolution=self.legacy_resolution())  # noqa: E501
        self.assertEqual(blocked.exception.message, support.BLOCKED_REFUSAL)

    def test_candidate_blocked_call_site_disable_leg_renders(self) -> None:
        resolution = self.legacy_resolution()
        _records, patches = self.candidate_patches(resolution)
        downstream = (
            mock.patch.object(ARCHIVE, "read_json_file", return_value=support.GATED_PAYLOAD),
            mock.patch.object(ARCHIVE, "run_audit", return_value="audit\n"),
            mock.patch.object(
                ARCHIVE,
                "recompute_pre_close_validation",
                return_value=support.GATED_PAYLOAD,
            ),
            mock.patch.object(ARCHIVE, "validate_run", return_value=support.GATED_PAYLOAD),
            mock.patch.object(
                ARCHIVE,
                "capture_archive_chain_package",
                return_value=ARCHIVE.ChainPackage(None, None, (), ()),
            ),
            mock.patch.object(
                ARCHIVE,
                "resolve_archive_bindings",
                return_value=ARCHIVE.binding_history.ResolvedBindings({}, {}),
            ),
            mock.patch.object(ARCHIVE, "legacy_discrepancies", return_value=[]),
            mock.patch.object(ARCHIVE, "tombstone_discrepancies", return_value=[]),
            mock.patch.object(ARCHIVE, "basis_documents", return_value=[]),
            mock.patch.object(ARCHIVE, "render_archive", return_value="archive\n"),
            mock.patch.object(ARCHIVE, "recheck_chain_package"),
            mock.patch.object(ARCHIVE, "recheck_captured_ingest_packages"),
            mock.patch.object(ARCHIVE, "recheck_basis_documents"),
            mock.patch.object(ARCHIVE, "recheck_archive_journal_snapshot"),
        )
        with contextlib.ExitStack() as stack:
            for patcher in (*patches, *downstream):
                stack.enter_context(patcher)
            mutant = mutated_function(
                ARCHIVE._render_archive_candidate,
                "    closing_engine.require_passed_without_backfill("
                'closing, closed.get("judgment"))\n',
                "",
            )
            rendered = mutant(
                repo=self.repo,
                run_dir=self.run_dir,
                closing_head=self.archive_head,
                legacy_recovered_head=None,
                legacy_approval=None,
                backfill_closing_head=None,
                backfill_approval=None,
                archiving_head=None,
                post_close_validation=self.base / "post-close.json",
                dispense_targets=(),
                dispense_reason=None,
                prove_legacy_approval=True,
            )
        self.assertEqual(rendered, b"archive\n")

    def test_candidate_identity_call_site_precedes_mode_resolution(self) -> None:
        records = self.blocked_records()
        records[0]["run_id"] = "wrong-run"
        raw = b"".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
            for record in records
        )
        arguments = dict(repo=self.repo, run_dir=self.run_dir, closing_head=self.archive_head, legacy_recovered_head=None, legacy_approval=None, backfill_closing_head=None, backfill_approval=None, archiving_head=None, post_close_validation=self.base / "post-close.json", dispense_targets=(), dispense_reason=None, prove_legacy_approval=True)  # noqa: E501
        with mock.patch.object(
            ARCHIVE, "stable_archive_journal_snapshot", return_value=(records, raw, None)
        ), mock.patch.object(
            CLOSING, "closing_mode_from_options", side_effect=AssertionError("mode reached")
        ):
            with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
                ARCHIVE._render_archive_candidate(**arguments)
            self.assertEqual(raised.exception.message, "forge: archive refused — invalid run journal")  # noqa: E501
            mutant = mutated_function(
                ARCHIVE._render_archive_candidate,
                "    require_valid_run_identity(started, closed, run_dir.name)\n",
                "",
            )
            with self.assertRaisesRegex(AssertionError, "mode reached"):
                mutant(**arguments)


class ArchiveIgnoreProtocolTests(support.GitBackfillFixture):
    def test_real_git_treats_magic_and_dash_prefixed_paths_literally(self) -> None:
        paths = (":(top)hostile", "-hostile")
        (self.repo / ".gitignore").write_text(
            "".join(f"/{path}\n" for path in paths), encoding="utf-8"
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(
                    ARCHIVE._check_archive_ignore(self.repo, path).returncode,
                    0,
                )

        mutant = mutated_function(
            ARCHIVE._check_archive_ignore,
            'os.fsencode("./" + relative)',
            "os.fsencode(relative)",
        )
        self.assertNotEqual(mutant(self.repo, paths[0]).returncode, 0)

    def test_archive_consumes_real_ignore_result_with_disable_leg(self) -> None:
        relative = f".forge/history/runs/{self.run_dir.name}.md"
        (self.repo / ".gitignore").write_text(f"/{relative}\n", encoding="utf-8")
        arguments = ARCHIVE.parser().parse_args(
            [
                "--run-dir", str(self.run_dir), "--closing-head", self.archive_head,
                "--post-close-validation", str(self.base / "post-close.json"),
            ]
        )
        patches = (
            mock.patch.object(ARCHIVE, "repository_root", return_value=self.repo),
            mock.patch.object(ARCHIVE, "resolve_run_dir", return_value=self.run_dir),
            mock.patch.object(ARCHIVE, "untracked_archive_snapshot", return_value=None),
            mock.patch.object(ARCHIVE, "prove_clean"),
            mock.patch.object(ARCHIVE, "render_archive_candidate", return_value=ARCHIVE_BYTES),
            mock.patch.object(ARCHIVE, "write_and_stage"),
        )
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
                ARCHIVE.archive(arguments)
            self.assertEqual(
                raised.exception.message,
                f"forge: archive refused — archive path is ignored: {relative}",
            )
            mutant = mutated_function(
                ARCHIVE.archive,
                "    ignored = _check_archive_ignore(repo, relative)\n",
                "    ignored = subprocess.CompletedProcess([], 1, b\"\", b\"\")\n",
            )
            self.assertEqual(mutant(arguments), relative)


class WriteAndStageGuardAuditTests(support.GitBackfillFixture):
    def test_expected_head_read_failure_is_normalized_with_disable_leg(self) -> None:
        refusal = "forge: archive refused — repository HEAD is not the approved archive HEAD"
        relative = f".forge/history/runs/{self.run_dir.name}.md"
        cases = (
            (mock.Mock(side_effect=CLOSING.ArchiveRefusal("sentinel")), "        except () as exc:\n", CLOSING.ArchiveRefusal, "sentinel"),  # noqa: E501
            (mock.Mock(return_value=b"\xff"), "        except ArchiveRefusal as exc:\n", UnicodeDecodeError, None),  # noqa: E501
        )
        for git_stdout, replacement, escaped_type, escaped_message in cases:
            with self.subTest(escaped=escaped_type.__name__), mock.patch.object(ARCHIVE, "git_stdout", git_stdout):  # noqa: E501
                with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
                    ARCHIVE.write_and_stage(self.repo, relative, "archive\n", expected_head=self.archive_head)  # noqa: E501
            self.assertEqual(raised.exception.message, refusal)
            mutant = mutated_function(ARCHIVE.write_and_stage, "        except (ArchiveRefusal, UnicodeError) as exc:\n", replacement)  # noqa: E501
            mutant.__globals__["git_stdout"] = git_stdout
            with self.assertRaises(escaped_type) as escaped:
                mutant(self.repo, relative, "archive\n", expected_head=self.archive_head)
            if escaped_message is not None:
                self.assertEqual(str(escaped.exception), escaped_message)


class ClosingModuleGuardAuditTests(support.GitBackfillFixture):
    def services(self, returncode: int = 0) -> object:
        return SimpleNamespace(run_git=lambda *_args: subprocess.CompletedProcess([], returncode, b"", b""), only_record=lambda records, kind: [record for record in records if record.get("type") == kind][0], renderer_controls=frozenset({"legacy-approval"}))  # noqa: E501

    def test_refusal_without_cause_does_not_suppress_context(self) -> None:
        try:
            raise ValueError("context")
        except ValueError:
            with self.assertRaises(CLOSING.ArchiveRefusal) as raised:
                CLOSING._refuse("refused")
            mutant = mutated_function(CLOSING._refuse, "    if cause is None:\n        raise ArchiveRefusal(message)\n", "    if False:\n        raise ArchiveRefusal(message)\n")  # noqa: E501
            with self.assertRaises(CLOSING.ArchiveRefusal) as changed:
                mutant("refused")
        self.assertEqual((raised.exception.__suppress_context__, changed.exception.__suppress_context__), (False, True))  # noqa: E501

    def test_direct_closing_option_guards_have_disable_legs(self) -> None:
        legacy = "forge: archive refused — legacy recovery approval missing or mismatched"
        cases = (
            (CLOSING.ClosingOptions(self.archive_head, None, None, self.closing, "run:decision-01", False), support.MODE_CONFLICT, "    if backfill and (normal or legacy):\n", "backfill", 0),  # noqa: E501
            (CLOSING.ClosingOptions(None, None, None, self.closing, None, False), BACKFILL_REFUSAL, "        if options.backfill_closing_head is None or options.backfill_approval is None:\n", "backfill", 0),  # noqa: E501
            (CLOSING.ClosingOptions(self.archive_head, self.closing, "run:decision-01", None, None, False), legacy, "    if normal and legacy:\n", None, 0),  # noqa: E501
            (CLOSING.ClosingOptions("bad", None, None, None, None, False), "forge: archive refused — invalid closing HEAD", "        if not isinstance(head, str) or HEX_HEAD.fullmatch(head) is None:\n", None, 0),  # noqa: E501
            (CLOSING.ClosingOptions(self.closing, None, None, None, None, False), "forge: archive refused — closing HEAD is not a repository commit", "        if services.run_git(repo, \"cat-file\", \"-e\", f\"{head}^{{commit}}\").returncode:\n", None, 1),  # noqa: E501
            (CLOSING.ClosingOptions(None, self.closing, None, None, None, False), legacy, "    if options.legacy_recovered_head is None or options.legacy_approval is None:\n", "legacy", 0),  # noqa: E501
        )
        for options, expected, anchor, backend, returncode in cases:
            services = self.services(returncode)
            with self.subTest(expected=expected), self.assertRaises(CLOSING.ArchiveRefusal) as raised:  # noqa: E501
                CLOSING.closing_mode_from_options(self.repo, self.run_dir, self.records(), options, services)  # noqa: E501
            self.assertEqual(raised.exception.message, expected)
            mutant = mutated_function(CLOSING.closing_mode_from_options, anchor, anchor[: len(anchor) - len(anchor.lstrip())] + "if False:\n")  # noqa: E501
            if backend:
                mutant.__globals__[f"{backend}_closing_mode"] = lambda *_args: CLOSING.ClosingMode(self.closing)  # noqa: E501
            self.assertIsInstance(mutant(self.repo, self.run_dir, self.records(), options, services), CLOSING.ClosingMode)  # noqa: E501

    def test_backend_requires_one_closing_mode_with_disable_leg(self) -> None:
        options = CLOSING.ClosingOptions(None, None, None, None, None, False)
        expected = "forge: archive refused — choose normal or paired legacy closing mode"
        self.assert_refusal(expected, lambda: CLOSING.closing_mode_from_options(self.repo, self.run_dir, self.records(), options, self.services()))  # noqa: E501
        mutant = mutated_function(CLOSING.closing_mode_from_options, '    if not legacy:\n        _refuse("forge: archive refused — choose normal or paired legacy closing mode")\n', "")  # noqa: E501
        self.assert_refusal(CLOSING.LEGACY_APPROVAL_REFUSAL, lambda: mutant(self.repo, self.run_dir, self.records(), options, self.services()))  # noqa: E501

    def test_legacy_backend_guards_and_call_sites_have_disable_legs(self) -> None:
        valid = CLOSING.LegacyRequest(self.records(), self.closing, "approval-run:decision-01", False)  # noqa: E501
        for value, anchor, replacement, escaped in ((7, "not isinstance(recovered_head, str) or ", "", TypeError), ("bad", " or HEX_HEAD.fullmatch(recovered_head) is None", "", type(None))):  # noqa: E501
            request = support.replace(valid, recovered_head=value)
            self.assert_refusal(CLOSING.LEGACY_APPROVAL_REFUSAL, lambda request=request: CLOSING.legacy_closing_mode(self.repo, self.run_dir, request, self.services()))  # noqa: E501
            mutant = mutated_function(CLOSING.legacy_closing_mode, anchor, replacement)
            if escaped is type(None): self.assertIsInstance(mutant(self.repo, self.run_dir, request, self.services()), CLOSING.ClosingMode)  # noqa: E701, E501
            else:
                with self.assertRaises(escaped): mutant(self.repo, self.run_dir, request, self.services())  # noqa: E701, E501
        failing = self.services(1); self.assert_refusal(CLOSING.LEGACY_APPROVAL_REFUSAL, lambda: CLOSING.legacy_closing_mode(self.repo, self.run_dir, valid, failing))  # noqa: E702, E501
        commit_mutant = mutated_function(CLOSING.legacy_closing_mode, '    if services.run_git(repo, "cat-file", "-e", f"{recovered_head}^{{commit}}").returncode:\n        _refuse(LEGACY_APPROVAL_REFUSAL)\n', "")  # noqa: E501
        self.assertIsInstance(commit_mutant(self.repo, self.run_dir, valid, failing), CLOSING.ClosingMode)  # noqa: E501
        target_mutant = mutated_function(CLOSING.legacy_closing_mode, "    _started, _closed = _target_parts(\n        records, target, services, LEGACY_APPROVAL_REFUSAL\n    )\n", "")  # noqa: E501
        with mock.patch.object(CLOSING, "_target_parts", side_effect=CLOSING.ArchiveRefusal("target reached")), self.assertRaisesRegex(CLOSING.ArchiveRefusal, "target reached"): CLOSING.legacy_closing_mode(self.repo, self.run_dir, valid, self.services())  # noqa: E701, E501
        self.assertIsInstance(target_mutant(self.repo, self.run_dir, valid, self.services()), CLOSING.ClosingMode)  # noqa: E501
        with mock.patch.object(CLOSING.journal_engine, "writer_contract_active", return_value=True): self.assert_refusal(CLOSING.LEGACY_APPROVAL_REFUSAL, lambda: CLOSING.legacy_closing_mode(self.repo, self.run_dir, valid, self.services()))  # noqa: E701, E501
        writer_mutant = mutated_function(CLOSING.legacy_closing_mode, "    if journal_engine.writer_contract_active(records):\n", "    if False:\n")  # noqa: E501
        writer_mutant.__globals__["journal_engine"] = SimpleNamespace(writer_contract_active=lambda _records: True); self.assertIsInstance(writer_mutant(self.repo, self.run_dir, valid, self.services()), CLOSING.ClosingMode)  # noqa: E702, E501
        mode = CLOSING.ClosingMode(self.closing, legacy_approval="approval-run:decision-01")
        self.assertEqual(CLOSING.provenance_lines(mode), [f"Legacy recovered closing HEAD: {self.closing}", "", "Legacy recovery approval: approval-run:decision-01", ""])  # noqa: E501
        provenance_mutant = mutated_function(CLOSING.provenance_lines, "    if closing.legacy_approval is not None:\n", "    if False:\n")  # noqa: E501
        self.assertEqual(provenance_mutant(mode), [f"Closing HEAD: {self.closing}", ""])
        wrapper_args = {"repo": self.repo, "target_run_dir": self.run_dir, "recovered_head": self.closing, "approval": "approval-run:decision-01", "prove_approval": False}  # noqa: E501
        with mock.patch.object(ARCHIVE, "stable_journal_snapshot", side_effect=ARCHIVE.ArchiveRefusal("sentinel")):  # noqa: E501
            with self.assertRaises(ARCHIVE.ArchiveRefusal) as raised: ARCHIVE.legacy_closing_mode(**wrapper_args)  # noqa: E701, E501
            self.assertEqual(raised.exception.message, ARCHIVE.LEGACY_APPROVAL_REFUSAL); wrapper_mutant = mutated_function(ARCHIVE.legacy_closing_mode, "    except ArchiveRefusal as exc:\n        raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL) from exc\n", "    except () as exc:\n        raise ArchiveRefusal(LEGACY_APPROVAL_REFUSAL) from exc\n")  # noqa: E702, E501
            with self.assertRaisesRegex(ARCHIVE.ArchiveRefusal, "sentinel"): wrapper_mutant(**wrapper_args)  # noqa: E701, E501
        preview_args = {"repo": self.repo, "run_dir": self.run_dir, "legacy_recovered_head": self.closing, "proposed_legacy_approval": "approval-run:decision-01", "post_close_validation": self.base / "post-close.json"}; preview = mock.Mock(return_value=b"preview")  # noqa: E702, E501
        with mock.patch.object(ARCHIVE, "_render_archive_candidate", preview):
            self.assertEqual(ARCHIVE.preview_legacy_archive_candidate(**preview_args), b"preview"); self.assertEqual(tuple(preview.call_args.kwargs[name] for name in ("backfill_closing_head", "backfill_approval", "archiving_head", "prove_legacy_approval")), (None, None, None, False)); disabled = mutated_function(ARCHIVE.preview_legacy_archive_candidate, "    return _render_archive_candidate(\n", '    return b"disabled" if True else _render_archive_candidate(\n'); disabled.__globals__["_render_archive_candidate"] = preview  # noqa: E702, E501
            self.assertEqual(disabled(**preview_args), b"disabled"); self.assertEqual(preview.call_count, 1)  # noqa: E702, E501

    def test_backfill_head_format_guard_has_disable_leg(self) -> None:
        arguments = (self.repo, self.run_dir, self.records(), "bad", "approval-run:decision-01", self.services())  # noqa: E501
        self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING.backfill_closing_mode(*arguments))  # noqa: E501
        mutant = mutated_function(CLOSING.backfill_closing_mode, "    if not isinstance(closing_head, str) or HEX_HEAD.fullmatch(closing_head) is None:\n        _refuse(BACKFILL_APPROVAL_REFUSAL)\n", "")  # noqa: E501
        mutant.__globals__["_target_parts"] = mock.Mock(side_effect=AssertionError("target reached"))  # noqa: E501
        with self.assertRaisesRegex(AssertionError, "target reached"):
            mutant(*arguments)
        typed = (self.repo, self.run_dir, self.records(), 7, "approval-run:decision-01", self.services())  # noqa: E501
        self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING.backfill_closing_mode(*typed))  # noqa: E501
        with self.assertRaises(TypeError): mutated_function(CLOSING.backfill_closing_mode, "not isinstance(closing_head, str) or ", "")(*typed)  # noqa: E701, E501

    def test_singleton_and_landed_oid_return_guards_have_disable_legs(self) -> None:
        evidence = self.evidence()
        duplicate_open = support.replace(evidence, records=(self.records()[0], *self.records()))  # noqa: E501
        duplicate_close = support.replace(evidence, records=(*self.records(), self.records()[-1]))  # noqa: E501
        for function, argument, anchor, replacement in (
            (CLOSING._opening, duplicate_open, "    return starts[0] if len(starts) == 1 else {}\n", "    return starts[0]\n"),  # noqa: E501
            (CLOSING._closure, duplicate_close, "    return closures[0] if len(closures) == 1 else {}\n", "    return closures[0]\n"),  # noqa: E501
        ):
            self.assertEqual(function(argument), {})
            self.assertTrue(mutated_function(function, anchor, replacement)(argument))
        unknown = SimpleNamespace(state={}, family="other")
        self.assertIsNone(CLOSING._landed_oid(unknown))
        family_mutant = mutated_function(CLOSING._landed_oid, "    else:\n        return None\n", '    else:\n        value = "0" * 40\n')  # noqa: E501
        self.assertEqual(family_mutant(unknown), "0" * 40)
        malformed = SimpleNamespace(state={"commit_result": {"commit_sha": "bad"}}, family="commit")  # noqa: E501
        self.assertIsNone(CLOSING._landed_oid(malformed))
        oid_mutant = mutated_function(CLOSING._landed_oid, "    return value if isinstance(value, str) and HEX_HEAD.fullmatch(value) else None\n", "    return value\n")  # noqa: E501
        self.assertEqual(oid_mutant(malformed), "bad")
        malformed_cases = ((SimpleNamespace(state={"commit_result": 7}, family="commit"), '        value = result.get("commit_sha") if isinstance(result, Mapping) else None\n', '        value = result.get("commit_sha")\n', AttributeError), (SimpleNamespace(state={"integration": 7}, family="merge"), '        push = integration.get("push") if isinstance(integration, Mapping) else None\n', '        push = integration.get("push")\n', AttributeError), (SimpleNamespace(state={"integration": {"push": 7}}, family="merge"), '        value = push.get("landed_head") if isinstance(push, Mapping) else None\n', '        value = push.get("landed_head")\n', AttributeError), (SimpleNamespace(state={"commit_result": {"commit_sha": 7}}, family="commit"), "isinstance(value, str) and ", "", TypeError))  # noqa: E501
        for malformed_result, anchor, replacement, escaped in malformed_cases:
            self.assertIsNone(CLOSING._landed_oid(malformed_result))
            with self.assertRaises(escaped): mutated_function(CLOSING._landed_oid, anchor, replacement)(malformed_result)  # noqa: E701, E501
        missing = support.replace(self.evidence(), package=SimpleNamespace(chains=(), tombstones=()), run_git=mock.Mock(side_effect=AssertionError("git reached")))  # noqa: E501
        self.assert_refusal(support.REFUSALS[5], lambda: CLOSING._enumerate_landed_commits(missing))  # noqa: E501
        enumeration_mutant = mutated_function(CLOSING._enumerate_landed_commits, "        if oid is None or not _git_success(evidence, \"cat-file\", \"-e\", f\"{oid}^{{commit}}\"):\n", "        if not _git_success(evidence, \"cat-file\", \"-e\", f\"{oid}^{{commit}}\"):\n")  # noqa: E501
        with self.assertRaisesRegex(AssertionError, "git reached"): enumeration_mutant(missing)  # noqa: E701, E501

    def test_basis_path_return_and_skip_guards_have_disable_legs(self) -> None:
        outside = SimpleNamespace(path=self.base / "outside")
        self.assertIsNone(CLOSING._repository_relative_path(self.repo, outside))
        resolve_mutant = mutated_function(CLOSING._repository_relative_path, "    except (OSError, RuntimeError, ValueError):\n        return None\n", "    except ():\n        return None\n")  # noqa: E501
        with self.assertRaises(ValueError):
            resolve_mutant(self.repo, outside)
        root = SimpleNamespace(path=self.repo)
        self.assertIsNone(CLOSING._repository_relative_path(self.repo, root))
        empty_mutant = mutated_function(CLOSING._repository_relative_path, "    return relative.as_posix() if relative.parts else None\n", "    return relative.as_posix()\n")  # noqa: E501
        self.assertEqual(empty_mutant(self.repo, root), ".")
        evidence = self.evidence(documents=(SimpleNamespace(label="outside", path=self.base / "outside"),))  # noqa: E501
        tracker = mock.Mock(side_effect=AssertionError("tree lookup reached"))
        with mock.patch.object(CLOSING, "_repository_relative_path", return_value=None), mock.patch.object(CLOSING, "_tree_tracks", tracker):  # noqa: E501
            CLOSING._prove_basis_stability(evidence)
        tracker.assert_not_called()
        skip_mutant = mutated_function(CLOSING._prove_basis_stability, "        if relative is None:\n            continue\n", "")  # noqa: E501
        skip_mutant.__globals__["_repository_relative_path"] = mock.Mock(return_value=None)
        skip_mutant.__globals__["_tree_tracks"] = tracker
        with self.assertRaisesRegex(AssertionError, "tree lookup reached"):
            skip_mutant(evidence)

    def test_git_output_return_guards_have_disable_legs(self) -> None:
        failed = support.replace(self.evidence(), run_git=lambda *_args: subprocess.CompletedProcess([], 1, b"123\n", b""))  # noqa: E501
        self.assertIsNone(CLOSING._commit_time(failed, self.closing))
        time_mutant = mutated_function(CLOSING._commit_time, "    valid = result.returncode == 0 and rendered.isdigit()\n    return int(rendered) if valid else None\n", "    return int(rendered)\n")  # noqa: E501
        self.assertEqual(time_mutant(failed, self.closing), 123)
        nondigit = support.replace(self.evidence(), run_git=lambda *_args: subprocess.CompletedProcess([], 0, b"not-a-time\n", b""))  # noqa: E501
        self.assertIsNone(CLOSING._commit_time(nondigit, self.closing))
        digit_mutant = mutated_function(CLOSING._commit_time, " and rendered.isdigit()", "")
        with self.assertRaises(ValueError): digit_mutant(nondigit, self.closing)  # noqa: E701
        empty = support.replace(self.evidence(), run_git=lambda *_args: subprocess.CompletedProcess([], 0, b"", b""))  # noqa: E501
        self.assertIsNone(CLOSING._first_parent_successor(empty))
        list_mutant = mutated_function(CLOSING._first_parent_successor, "    if result.returncode or not values or HEX_HEAD.fullmatch(values[0]) is None:\n        return None\n", "")  # noqa: E501
        with self.assertRaises(IndexError):
            list_mutant(empty)
        failed_list = support.replace(self.evidence(), run_git=lambda _repo, *args: subprocess.CompletedProcess([], 1 if args[0] == "rev-list" else 0, f"{self.archive_head if args[0] == 'rev-list' else self.closing}\n".encode(), b""))  # noqa: E501
        self.assertIsNone(CLOSING._first_parent_successor(failed_list))
        returncode_mutant = mutated_function(CLOSING._first_parent_successor, "    if result.returncode or not values or HEX_HEAD.fullmatch(values[0]) is None:\n", "    if not values or HEX_HEAD.fullmatch(values[0]) is None:\n")  # noqa: E501
        self.assertEqual(returncode_mutant(failed_list), self.archive_head)
        malformed_list = support.replace(failed_list, run_git=lambda _repo, *args: subprocess.CompletedProcess([], 0, f"{'bad' if args[0] == 'rev-list' else self.closing}\n".encode(), b""))  # noqa: E501
        self.assertIsNone(CLOSING._first_parent_successor(malformed_list))
        format_mutant = mutated_function(CLOSING._first_parent_successor, " or HEX_HEAD.fullmatch(values[0]) is None", "")  # noqa: E501
        self.assertEqual(format_mutant(malformed_list), "bad")
        def parent_failure(_repo, *arguments):
            if arguments[0] == "rev-list":
                return subprocess.CompletedProcess([], 0, f"{self.archive_head}\n".encode(), b"")  # noqa: E501
            raise OSError("parent lookup")
        parent = support.replace(self.evidence(), run_git=parent_failure)
        self.assertIsNone(CLOSING._first_parent_successor(parent))
        parent_mutant = mutated_function(CLOSING._first_parent_successor, '    try:\n        parent = evidence.run_git(\n            evidence.repo, "rev-parse", f"{values[0]}^1"\n        ).stdout.decode("ascii").strip()\n    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):\n        return None\n', '    parent = evidence.run_git(evidence.repo, "rev-parse", f"{values[0]}^1").stdout.decode("ascii").strip()\n')  # noqa: E501
        with self.assertRaisesRegex(OSError, "parent lookup"):
            parent_mutant(parent)

    def test_helper_failure_guards_have_disable_legs(self) -> None:
        evidence = self.evidence()
        throwing = support.replace(evidence, run_git=lambda *_args: (_ for _ in ()).throw(OSError("git")))  # noqa: E501
        self.assertFalse(CLOSING._git_success(throwing, "status"))
        git_mutant = mutated_function(CLOSING._git_success, "    except (OSError, subprocess.SubprocessError, ValueError):\n", "    except ():\n")  # noqa: E501
        with self.assertRaises(OSError):
            git_mutant(throwing, "status")
        for function, argument, anchor in (
            (CLOSING._landed_oid, SimpleNamespace(state=object(), family="commit"), "    if not isinstance(state, Mapping):\n"),  # noqa: E501
            (CLOSING._repository_relative_path, (self.repo, SimpleNamespace(path="basis.md")), "    if not isinstance(path, Path):\n"),  # noqa: E501
        ):
            parameters = argument if isinstance(argument, tuple) else (argument,)
            self.assertIsNone(function(*parameters))
            mutant = mutated_function(function, anchor, anchor[: len(anchor) - len(anchor.lstrip())] + "if False:\n")  # noqa: E501
            with self.assertRaises((AttributeError, TypeError)):
                mutant(*parameters)
        duplicate = support.replace(evidence, records=(*self.records(), self.records()[-1]))
        self.assertIsNone(duplicate.closing_judgment)
        judgment_mutant = mutated_function(CLOSING.BackfillEvidence.closing_judgment.fget, "return closures[0].get(\"judgment\") if len(closures) == 1 else None", "return closures[0].get(\"judgment\") if closures else None")  # noqa: E501
        self.assertEqual(judgment_mutant(duplicate), "passed")

    def test_malformed_starting_and_landing_shapes_short_circuit(self) -> None:
        missing_time = support.replace(self.evidence(), run_git=lambda *_args: subprocess.CompletedProcess([], 1, b"", b""))  # noqa: E501
        self.assert_refusal(support.REFUSALS[8], lambda: CLOSING._prove_closing_time(missing_time))  # noqa: E501
        with self.assertRaises(TypeError): mutated_function(CLOSING._prove_closing_time, " or committed is None", "")(missing_time)  # noqa: E701, E501
        self.assert_refusal(support.REFUSALS[10], lambda: CLOSING._prove_archive_time(missing_time, 0))  # noqa: E501
        with self.assertRaises(TypeError): mutated_function(CLOSING._prove_archive_time, "archived is None or ", "")(missing_time, 0)  # noqa: E701, E501
        for value, anchor, escaped in ((7, "        not isinstance(evidence.archiving_head, str)\n", TypeError), ("bad", "        or HEX_HEAD.fullmatch(evidence.archiving_head) is None\n", AssertionError)):  # noqa: E501
            closing = support.replace(self.evidence().closing, archive_head=value)
            evidence = support.replace(self.evidence(), archiving_head=value, closing=closing, run_git=mock.Mock(side_effect=AssertionError("git reached")))  # noqa: E501
            self.assert_refusal(support.REFUSALS[1], lambda evidence=evidence: CLOSING._prove_archive_head(evidence))  # noqa: E501
            with self.assertRaises(escaped): mutated_function(CLOSING._prove_archive_head, anchor, anchor.replace("not isinstance(evidence.archiving_head, str)", "False").replace("or HEX_HEAD.fullmatch(evidence.archiving_head) is None", "or False"))(evidence)  # noqa: E701, E501
        for value, anchor, escaped in ((7, "        not isinstance(starting, str)\n", TypeError), ("bad", "        or HEX_HEAD.fullmatch(starting) is None\n", AssertionError)):  # noqa: E501
            records = self.records(); records[0]["repo_head"] = value  # noqa: E702
            evidence = support.replace(self.evidence(records=records), run_git=mock.Mock(side_effect=AssertionError("git reached")))  # noqa: E501
            self.assert_refusal(support.REFUSALS[4], lambda evidence=evidence: CLOSING._prove_starting_ancestry(evidence))  # noqa: E501
            with self.assertRaises(escaped): mutated_function(CLOSING._prove_starting_ancestry, anchor, anchor.replace("not isinstance(starting, str)", "False").replace("or HEX_HEAD.fullmatch(starting) is None", "or False"))(evidence)  # noqa: E701, E501
        for field, value, anchor, replacement in (("binding", 7, '        source = binding.get("source_record") if isinstance(binding, Mapping) else None\n', '        source = binding.get("source_record")\n'), ("source_record", 7, '        chain_id = source.get("chain_id") if isinstance(source, Mapping) else None\n', '        chain_id = source.get("chain_id")\n')):  # noqa: E501
            records = self.records(); records[1]["binding"] = value if field == "binding" else {field: value}  # noqa: E702, E501
            self.assertIsNone(CLOSING._landing_chain_ids(self.evidence(records=records)))
            with self.assertRaises(AttributeError): mutated_function(CLOSING._landing_chain_ids, anchor, replacement)(self.evidence(records=records))  # noqa: E701, E501
        for rogue, anchor, replacement in (({"type": "note", "outcome": "chain-landing", "binding": {"source_record": {"chain_id": "rogue"}}}, 'record.get("type") != "decision" or ', ""), ({"type": "decision", "outcome": "other", "binding": {"source_record": {"chain_id": "rogue"}}}, ' or record.get("outcome") != "chain-landing"', "")):  # noqa: E501
            evidence = self.evidence(records=[*self.records(), rogue])
            self.assertNotIn("rogue", CLOSING._landing_chain_ids(evidence))
            self.assertIn("rogue", mutated_function(CLOSING._landing_chain_ids, anchor, replacement)(evidence))  # noqa: E501

    def test_approval_shape_and_owner_recheck_guards_have_disable_legs(self) -> None:
        start = {"type": "run_started", "run_id": "approval-run", "scope": ["basis.md"]}
        decision = {"type": "decision", "id": "decision-01", "outcome": "operator_approval"}
        cases = (
            ([start, dict(start), decision], "        len(starts) != 1\n", "        False\n"),
            ([{**start, "run_id": "other"}, decision], '        or starts[0].get("run_id") != run_id\n', "        or False\n"),  # noqa: E501
            ([{**start, "scope": []}, decision], "        and scope\n", ""),
            ([{**start, "scope": [7]}, decision], "        and all(isinstance(item, str) and item for item in scope)\n", ""),  # noqa: E501
            ([start, decision, dict(decision)], "        or len(decisions) != 1\n", "        or False\n"),  # noqa: E501
            ([start, {**decision, "decision": {}}], '        or "decision" in decisions[0]\n', "        or False\n"),  # noqa: E501
            ([start, {**decision, "type": "note"}], 'record.get("type") == "decision" and ', ""),  # noqa: E501
            ([start, {**decision, "id": "other"}], ' and record.get("id") == decision_id', ""),  # noqa: E501
        )
        for records, anchor, replacement in cases:
            with self.subTest(anchor=anchor), mock.patch.object(CLOSING.journal_engine, "writer_contract_active", return_value=True):  # noqa: E501
                self.assert_refusal(BACKFILL_REFUSAL, lambda records=records: CLOSING._approval_parts(records, "approval-run", "decision-01", BACKFILL_REFUSAL))  # noqa: E501
                parts_mutant = mutated_function(CLOSING._approval_parts, anchor, replacement)
                self.assertIsInstance(parts_mutant(records, "approval-run", "decision-01", BACKFILL_REFUSAL)[2], tuple)  # noqa: E501
        self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING._approval_parts([decision], "approval-run", "decision-01", BACKFILL_REFUSAL))  # noqa: E501
        missing_start = mutated_function(CLOSING._approval_parts, '    scope = starts[0].get("scope") if starts else None\n', '    scope = starts[0].get("scope")\n')  # noqa: E501
        with self.assertRaises(IndexError): missing_start([decision], "approval-run", "decision-01", BACKFILL_REFUSAL)  # noqa: E701, E501
        wrong_type = [{**start, "scope": "basis.md"}, decision]
        with mock.patch.object(CLOSING.journal_engine, "writer_contract_active", return_value=True):
            self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING._approval_parts(wrong_type, "approval-run", "decision-01", BACKFILL_REFUSAL))  # noqa: E501
            type_mutant = mutated_function(CLOSING._approval_parts, "        isinstance(scope, list)\n", "        True\n")  # noqa: E501
            with self.assertRaises(AssertionError):
                type_mutant(wrong_type, "approval-run", "decision-01", BACKFILL_REFUSAL)
        owner = SimpleNamespace(pid=41, host="fixture-host")
        evidence = SimpleNamespace(directory=self.run_dir, raw=b"journal\n", owner_before=("before", owner))  # noqa: E501
        raw_observed: list[str] = []
        with mock.patch.object(CLOSING.journal_engine, "_stable_journal_read", return_value=b"changed\n"), mock.patch.object(CLOSING.journal_engine, "_read_owner_observation", return_value=evidence.owner_before):  # noqa: E501
            CLOSING._recheck_approval(evidence, owner, SimpleNamespace(authoritative_discrepancy=raw_observed.append))  # noqa: E501
            raw_mutant = mutated_function(CLOSING._recheck_approval, '    if journal_engine._stable_journal_read(\n        evidence.directory / "journal.jsonl"\n    ) != evidence.raw:\n        services.authoritative_discrepancy("snapshot_changed")\n', "")  # noqa: E501
            raw_mutant(evidence, owner, SimpleNamespace(authoritative_discrepancy=raw_observed.append))  # noqa: E501
        self.assertEqual(raw_observed, ["snapshot_changed"])
        for owner_after, anchor in (
            (("after", owner), "        or owner_after[0] != evidence.owner_before[0]\n"),
            (("before", SimpleNamespace(pid=42, host="fixture-host")), "        or owner_after[1].pid != current_owner.pid\n"),  # noqa: E501
            (("before", SimpleNamespace(pid=41, host="other")), "        or owner_after[1].host != current_owner.host\n"),  # noqa: E501
        ):
            observed: list[str] = []
            with mock.patch.object(CLOSING.journal_engine, "_stable_journal_read", return_value=evidence.raw), mock.patch.object(CLOSING.journal_engine, "_read_owner_observation", return_value=owner_after):  # noqa: E501
                CLOSING._recheck_approval(evidence, owner, SimpleNamespace(authoritative_discrepancy=observed.append))  # noqa: E501
                mutant = mutated_function(CLOSING._recheck_approval, anchor, "        or False\n")
                mutant(evidence, owner, SimpleNamespace(authoritative_discrepancy=observed.append))  # noqa: E501
            self.assertEqual(observed, ["snapshot_changed"])
        observed = []
        with mock.patch.object(CLOSING.journal_engine, "_stable_journal_read", return_value=evidence.raw), mock.patch.object(CLOSING.journal_engine, "_read_owner_observation", return_value=None):  # noqa: E501
            CLOSING._recheck_approval(evidence, owner, SimpleNamespace(authoritative_discrepancy=observed.append))  # noqa: E501
            missing_mutant = mutated_function(CLOSING._recheck_approval, "        owner_after is None\n", "        False\n")  # noqa: E501
            with self.assertRaises(TypeError):
                missing_mutant(evidence, owner, SimpleNamespace(authoritative_discrepancy=observed.append))  # noqa: E501
        self.assertEqual(observed, ["snapshot_changed"])

    def test_snapshot_and_target_exceptions_are_normalized_with_disable_legs(self) -> None:
        sentinel = CLOSING.ArchiveRefusal("sentinel")
        services = SimpleNamespace(stable_journal_snapshot=mock.Mock(side_effect=sentinel))
        patches = (mock.patch.object(CLOSING, "_approval_identity", return_value=("approval-run", "decision-01")), mock.patch.object(CLOSING, "_approval_directory", return_value=self.run_dir), mock.patch.object(CLOSING, "_owned_approval", return_value=(object(), (b"owner", object()))))  # noqa: E501
        with patches[0], patches[1], patches[2]:
            self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING._approval_evidence(self.repo, self.run_dir, "approval-run:decision-01", BACKFILL_REFUSAL, services))  # noqa: E501
            approval_mutant = mutated_function(CLOSING._approval_evidence, "    except ArchiveRefusal as exc:\n        _refuse(refusal, exc)\n", "    except () as exc:\n        _refuse(refusal, exc)\n")  # noqa: E501
            with self.assertRaisesRegex(CLOSING.ArchiveRefusal, "sentinel"):
                approval_mutant(self.repo, self.run_dir, "approval-run:decision-01", BACKFILL_REFUSAL, services)  # noqa: E501
        target_services = SimpleNamespace(only_record=mock.Mock(side_effect=sentinel))
        self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING._target_parts(self.records(), self.run_dir, target_services, BACKFILL_REFUSAL))  # noqa: E501
        target_mutant = mutated_function(CLOSING._target_parts, "    except ArchiveRefusal as exc:\n        _refuse(refusal, exc)\n", "    except () as exc:\n        _refuse(refusal, exc)\n")  # noqa: E501
        with self.assertRaisesRegex(CLOSING.ArchiveRefusal, "sentinel"):
            target_mutant(self.records(), self.run_dir, target_services, BACKFILL_REFUSAL)
        repository_mutant = mutated_function(CLOSING._approval_repository_matches, "    except (\n        OSError,\n        RuntimeError,\n        ValueError,\n        journal_engine.CoordinationRefusal,\n        recorded_repository.ResolutionError,\n    ) as exc:\n", "    except () as exc:\n")  # noqa: E501
        with mock.patch.object(CLOSING.recorded_repository, "resolve", side_effect=ValueError("repository")):  # noqa: E501
            self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING._approval_repository_matches(self.repo, self.run_dir, {"repo": str(self.repo)}, BACKFILL_REFUSAL))  # noqa: E501
            with self.assertRaisesRegex(ValueError, "repository"): repository_mutant(self.repo, self.run_dir, {"repo": str(self.repo)}, BACKFILL_REFUSAL)  # noqa: E701, E501

    def test_approval_replay_call_has_disable_leg(self) -> None:
        records = self.records()
        services = SimpleNamespace(stable_journal_snapshot=mock.Mock(return_value=(records, b"raw")), authoritative_discrepancy=mock.Mock())  # noqa: E501
        parts = mock.Mock(return_value=(records[0], {"resolution": "approved"}, ("basis.md",)))  # noqa: E501
        patches = (mock.patch.object(CLOSING, "_approval_identity", return_value=("approval-run", "decision-01")), mock.patch.object(CLOSING, "_approval_directory", return_value=self.run_dir), mock.patch.object(CLOSING, "_owned_approval", return_value=(object(), (b"owner", object()))), mock.patch.object(CLOSING, "_approval_parts", new=parts), mock.patch.object(CLOSING, "_approval_repository_matches"), mock.patch.object(CLOSING, "_replay_approval", side_effect=CLOSING.ArchiveRefusal("replay reached")), mock.patch.object(CLOSING, "_recheck_approval"))  # noqa: E501
        with contextlib.ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaisesRegex(CLOSING.ArchiveRefusal, "replay reached"):
                CLOSING._approval_evidence(self.repo, self.run_dir, "approval-run:decision-01", BACKFILL_REFUSAL, services)  # noqa: E501
            mutant = mutated_function(CLOSING._approval_evidence, "    _replay_approval(evidence, repo, refusal)\n", "")  # noqa: E501
            self.assertEqual(mutant(self.repo, self.run_dir, "approval-run:decision-01", BACKFILL_REFUSAL, services).scope, ("basis.md",))  # noqa: E501
            self.assertEqual(parts.call_args.args[2], "decision-01")
            decision_mutant = mutated_function(CLOSING._approval_evidence, "_approval_parts(records, run_id, decision_id, refusal)", '_approval_parts(records, run_id, "other-decision", refusal)')  # noqa: E501
            decision_mutant.__globals__["_replay_approval"] = mock.Mock()
            decision_mutant(self.repo, self.run_dir, "approval-run:decision-01", BACKFILL_REFUSAL, services)  # noqa: E501
            self.assertEqual(parts.call_args.args[2], "other-decision")

        evidence = SimpleNamespace(records=({"type": "note", "_line": 7}, {"type": "note-2", "_line": 8}), run_id="approval-run", scope=("basis.md",))  # noqa: E501
        validator = mock.Mock()
        line_mutant = mutated_function(CLOSING._replay_approval, ' if name != "_line"', "")
        prior_mutant = mutated_function(CLOSING._replay_approval, "prior_records=canonical_records[:index]", "prior_records=()")  # noqa: E501
        with mock.patch.object(CLOSING.journal_engine, "_writer_activation_marker", return_value=False), mock.patch.object(CLOSING.journal_engine, "_validate_proposed_record", validator):  # noqa: E501
            CLOSING._replay_approval(evidence, self.repo, BACKFILL_REFUSAL); line_mutant(evidence, self.repo, BACKFILL_REFUSAL); prior_mutant(evidence, self.repo, BACKFILL_REFUSAL)  # noqa: E702, E501
        calls = validator.call_args_list
        self.assertEqual((calls[0].args[0], calls[2].args[0]), ({"type": "note"}, {"type": "note", "_line": 7}))  # noqa: E501
        self.assertEqual((len(calls[1].kwargs["prior_records"]), calls[5].kwargs["prior_records"]), (1, ()))  # noqa: E501
        for error in (KeyError("record"), TypeError("record"), ValueError("record")):
            anchor = f"        {type(error).__name__},\n"; exception_mutant = mutated_function(CLOSING._replay_approval, anchor, "")  # noqa: E702, E501
            with mock.patch.object(CLOSING.journal_engine, "_writer_activation_marker", return_value=False), mock.patch.object(CLOSING.journal_engine, "_validate_proposed_record", side_effect=error): self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING._replay_approval(evidence, self.repo, BACKFILL_REFUSAL))  # noqa: E701, E501
            with mock.patch.object(CLOSING.journal_engine, "_writer_activation_marker", return_value=False), mock.patch.object(CLOSING.journal_engine, "_validate_proposed_record", side_effect=error), self.assertRaises(type(error)): exception_mutant(evidence, self.repo, BACKFILL_REFUSAL)  # noqa: E701, E501

    def test_approval_token_and_registry_guards_have_disable_legs(self) -> None:
        with self.assertRaises(CLOSING.ArchiveRefusal): CLOSING._approval_identity(object(), BACKFILL_REFUSAL)  # noqa: E701, E501
        token_mutant = mutated_function(CLOSING._approval_identity, "    match = APPROVAL_TOKEN.fullmatch(token) if isinstance(token, str) else None\n", '    match = APPROVAL_TOKEN.fullmatch(token) if isinstance(token, str) else APPROVAL_TOKEN.fullmatch("approval-run:decision-01")\n')  # noqa: E501
        self.assertEqual(token_mutant(object(), BACKFILL_REFUSAL), ("approval-run", "decision-01"))
        checks = (*CLOSING.APPROVAL_BINDING_CHECKS, "unexpected-tail")
        with mock.patch.object(CLOSING, "APPROVAL_BINDING_CHECKS", checks), self.assertRaises(CLOSING.ArchiveRefusal):  # noqa: E501
            CLOSING._require_approval_binding_check(CLOSING.APPROVAL_BINDING_CHECKS[-2], BACKFILL_REFUSAL)  # noqa: E501
        registry_mutant = mutated_function(CLOSING._require_approval_binding_check, "    if position + 1 == len(_REQUIRED_APPROVAL_BINDING_CHECKS) and actual != (\n        _REQUIRED_APPROVAL_BINDING_CHECKS\n    ):\n", "    if False:\n")  # noqa: E501
        registry_mutant.__globals__["APPROVAL_BINDING_CHECKS"] = checks
        registry_mutant(CLOSING.APPROVAL_BINDING_CHECKS[-1], BACKFILL_REFUSAL)
        reordered = (checks[1], checks[0], *checks[2:-1])
        with mock.patch.object(CLOSING, "APPROVAL_BINDING_CHECKS", reordered), self.assertRaises(CLOSING.ArchiveRefusal):  # noqa: E501
            CLOSING._require_approval_binding_check(checks[0], BACKFILL_REFUSAL)
        prefix_mutant = mutated_function(CLOSING._require_approval_binding_check, "    if actual[: position + 1] != _REQUIRED_APPROVAL_BINDING_CHECKS[: position + 1]:\n        _refuse(refusal)\n", "")  # noqa: E501
        prefix_mutant.__globals__["APPROVAL_BINDING_CHECKS"] = reordered; prefix_mutant(checks[0], BACKFILL_REFUSAL)  # noqa: E702, E501

    def test_each_approval_binding_call_site_has_disable_leg(self) -> None:
        directory = self.run_dir.parent / "approval-run"; directory.mkdir()  # noqa: E702
        owner = SimpleNamespace(pid=41, host="fixture-host")
        records = [{"type": "run_started", "run_id": "approval-run", "scope": ["basis.md"]}, {"type": "decision", "id": "decision-01", "outcome": "operator_approval"}]  # noqa: E501
        calls: list[str] = []
        state_root = mock.Mock(return_value=self.repo); repository_resolver = mock.Mock(return_value=(self.repo.resolve(), False))  # noqa: E702, E501
        patches = (mock.patch.object(CLOSING, "_require_approval_binding_check", side_effect=lambda name, _refusal: calls.append(name)), mock.patch.object(CLOSING.journal_engine, "writer_contract_active", return_value=True), mock.patch.object(CLOSING.journal_engine, "_session_owner", return_value=owner), mock.patch.object(CLOSING.journal_engine, "_read_owner_observation", return_value=(b"owner", owner)), mock.patch.object(CLOSING.journal_engine, "_resolve_state_root", new=state_root), mock.patch.object(CLOSING.recorded_repository, "resolve", new=repository_resolver))  # noqa: E501
        operations = ((CLOSING._approval_directory, (self.run_dir, "approval-run", BACKFILL_REFUSAL), ("approval-run-differs",)), (CLOSING._owned_approval, (directory, BACKFILL_REFUSAL), ("session-owner-match",)), (CLOSING._approval_parts, (records, "approval-run", "decision-01", BACKFILL_REFUSAL), ("approval-run-activated", "approval-run-open", "operator-approval-outcome")), (CLOSING._approval_repository_matches, (self.repo, directory, {"repo": str(self.repo)}, BACKFILL_REFUSAL), ("recorded-repository-match",)))  # noqa: E501
        with contextlib.ExitStack() as stack:
            for patcher in patches: stack.enter_context(patcher)  # noqa: E701
            for function, arguments, expected in operations:
                calls.clear(); function(*arguments); self.assertEqual(calls, list(expected))  # noqa: E702
                for name in expected:
                    calls.clear(); mutant = mutated_function(function, f'    _require_approval_binding_check("{name}", refusal)\n', ""); mutant(*arguments)  # noqa: E702, E501
                    self.assertEqual(calls, [item for item in expected if item != name])
            repository = SimpleNamespace(resolve=mock.Mock(return_value=self.repo.resolve()))
            mutations = (("repo.resolve(strict=True)", "repo.resolve(strict=False)", (False, "archive", directory, self.repo.resolve())), ('_resolve_state_root(canonical_repo, "archive")', '_resolve_state_root(canonical_repo, "commit")', (True, "commit", directory, self.repo.resolve())), ("run_dir=directory", "run_dir=directory.parent", (True, "archive", directory.parent, self.repo.resolve())), ("caller_repository=canonical_repo", "caller_repository=None", (True, "archive", directory, None)))  # noqa: E501
            for anchor, replacement, expected in mutations:
                repository.resolve.reset_mock(); state_root.reset_mock(); repository_resolver.reset_mock()  # noqa: E702, E501
                mutated_function(CLOSING._approval_repository_matches, anchor, replacement)(repository, directory, {"repo": str(self.repo)}, BACKFILL_REFUSAL)  # noqa: E501
                observed = (repository.resolve.call_args.kwargs["strict"], state_root.call_args.args[1], repository_resolver.call_args.kwargs["run_dir"], repository_resolver.call_args.kwargs["caller_repository"])  # noqa: E501
                self.assertEqual(observed, expected)

    def test_approval_directory_path_guards_have_disable_legs(self) -> None:
        directory = self.run_dir.parent / "approval-run"; directory.mkdir()  # noqa: E702
        trace: list[bool] = []
        with mock.patch.object(Path, "resolve", autospec=True, side_effect=lambda path, *, strict: (trace.append(strict), path)[1]):  # noqa: E501
            CLOSING._approval_directory(self.run_dir, directory.name, BACKFILL_REFUSAL); self.assertEqual(trace, [True, True])  # noqa: E702, E501
            for anchor, expected in (("        parent = target.parent.resolve(strict=True)\n", [False, True]), ("        directory = (target.parent / run_id).resolve(strict=True)\n", [True, False])):  # noqa: E501
                trace.clear(); mutated_function(CLOSING._approval_directory, anchor, anchor.replace("True", "False"))(self.run_dir, directory.name, BACKFILL_REFUSAL); self.assertEqual(trace, expected)  # noqa: E702, E501
        missing = self.run_dir.parent / "missing-approval"
        self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING._approval_directory(self.run_dir, missing.name, BACKFILL_REFUSAL))  # noqa: E501
        strict_mutant = mutated_function(CLOSING._approval_directory, "        directory = (target.parent / run_id).resolve(strict=True)\n", "        directory = (target.parent / run_id).resolve(strict=False)\n")  # noqa: E501
        self.assertEqual(strict_mutant(self.run_dir, missing.name, BACKFILL_REFUSAL), missing)
        escaped = self.repo / ".codex-orchestrator/escaped"; escaped.mkdir(parents=True)  # noqa: E702
        link = self.run_dir.parent / "approval-link"; link.symlink_to(escaped, target_is_directory=True)  # noqa: E702, E501
        self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING._approval_directory(self.run_dir, link.name, BACKFILL_REFUSAL))  # noqa: E501
        lexical_mutant = mutated_function(CLOSING._approval_directory, "        directory = (target.parent / run_id).resolve(strict=True)\n", "        directory = target.parent / run_id\n")  # noqa: E501
        self.assertEqual(lexical_mutant(self.run_dir, link.name, BACKFILL_REFUSAL), link)
        outside = self.repo / ".codex-orchestrator/foreign"; outside.mkdir(parents=True)  # noqa: E702
        self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING._approval_directory(self.run_dir, str(outside), BACKFILL_REFUSAL))  # noqa: E501
        for replacement in ("", "        directory.relative_to(parent.parent)\n"):
            mutant = mutated_function(CLOSING._approval_directory, "        directory.relative_to(parent)\n", replacement); self.assertEqual(mutant(self.run_dir, str(outside), BACKFILL_REFUSAL), outside)  # noqa: E702, E501
        for error, retained in ((OSError("path"), "RuntimeError, ValueError"), (RuntimeError("path"), "OSError, ValueError"), (ValueError("path"), "OSError, RuntimeError")):  # noqa: E501
            with mock.patch.object(Path, "resolve", side_effect=error): self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING._approval_directory(self.run_dir, directory.name, BACKFILL_REFUSAL))  # noqa: E701, E501
            mutant = mutated_function(CLOSING._approval_directory, "    except (OSError, RuntimeError, ValueError) as exc:\n", f"    except ({retained}) as exc:\n")  # noqa: E501
            with mock.patch.object(Path, "resolve", side_effect=error), self.assertRaises(type(error)): mutant(self.run_dir, directory.name, BACKFILL_REFUSAL)  # noqa: E701, E501

    def test_owned_approval_exception_guard_has_disable_leg(self) -> None:
        owner = SimpleNamespace(pid=41, host="fixture-host"); reader = mock.Mock(return_value=(b"owner", owner))  # noqa: E702, E501
        path_mutant = mutated_function(CLOSING._owned_approval, 'directory / "owner"', "directory")  # noqa: E501
        with mock.patch.object(CLOSING.journal_engine, "_session_owner", return_value=owner), mock.patch.object(CLOSING.journal_engine, "_read_owner_observation", side_effect=reader): CLOSING._owned_approval(self.run_dir, BACKFILL_REFUSAL); path_mutant(self.run_dir, BACKFILL_REFUSAL)  # noqa: E701, E702, E501
        self.assertEqual([call.args[0] for call in reader.call_args_list], [self.run_dir / "owner", self.run_dir])  # noqa: E501
        mutant = mutated_function(CLOSING._owned_approval, "    except (\n        OSError,\n        RuntimeError,\n        ValueError,\n        journal_engine.CoordinationRefusal,\n    ) as exc:\n", "    except () as exc:\n")  # noqa: E501
        for error in (OSError("owner"), RuntimeError("owner"), ValueError("owner"), CLOSING.journal_engine.CoordinationRefusal("owner")):  # noqa: E501
            with mock.patch.object(CLOSING.journal_engine, "_session_owner", side_effect=error): self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING._owned_approval(self.run_dir, BACKFILL_REFUSAL))  # noqa: E701, E501
            with mock.patch.object(CLOSING.journal_engine, "_session_owner", side_effect=error), self.assertRaises(type(error)): mutant(self.run_dir, BACKFILL_REFUSAL)  # noqa: E701, E501

    def test_time_and_empty_basis_failure_guards_have_disable_legs(self) -> None:
        throwing = support.replace(self.evidence(documents=()), run_git=lambda *_args: (_ for _ in ()).throw(OSError("git")))  # noqa: E501
        for function, arguments, anchor in (
            (CLOSING._commit_time, (throwing, self.closing), "    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):\n"),  # noqa: E501
            (CLOSING._first_parent_successor, (throwing,), '        values = result.stdout.decode("ascii").splitlines()\n    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError):\n'),  # noqa: E501
        ):
            self.assertIsNone(function(*arguments))
            mutant = mutated_function(function, anchor, anchor.replace("except (OSError, UnicodeError, ValueError, subprocess.SubprocessError)", "except ()"))  # noqa: E501
            with self.assertRaises(OSError):
                mutant(*arguments)
        with mock.patch.object(CLOSING, "BACKFILL_CONTROLS", tuple(item for item in CLOSING.BACKFILL_CONTROLS if item != "basis-stability")), self.assertRaises(CLOSING.ArchiveRefusal):  # noqa: E501
            CLOSING._prove_basis_stability(self.evidence(documents=()))
        basis_mutant = mutated_function(CLOSING._prove_basis_stability, "    if not evidence.documents:\n        _require_control(\n            \"basis-stability\",\n            \"forge: archive refused — basis document changed after closing HEAD: <label>\",\n        )\n", "")  # noqa: E501
        basis_mutant.__globals__["BACKFILL_CONTROLS"] = tuple(item for item in CLOSING.BACKFILL_CONTROLS if item != "basis-stability")  # noqa: E501
        with mock.patch.object(CLOSING, "BACKFILL_CONTROLS", tuple(item for item in CLOSING.BACKFILL_CONTROLS if item != "basis-stability")):  # noqa: E501
            basis_mutant(self.evidence(documents=()))

    def test_backfill_resolution_target_binding_has_disable_leg(self) -> None:
        resolution = f"backfill-archive: run-other closing HEAD {self.closing}; archive HEAD {self.archive_head}; judgment passed; approved history"  # noqa: E501
        evidence = SimpleNamespace(decision={"resolution": resolution})
        arguments = (self.repo, self.run_dir, self.records(), self.closing, "approval-run:decision-01", self.services())  # noqa: E501
        with mock.patch.object(CLOSING, "_approval_evidence", return_value=evidence), self.assertRaises(CLOSING.ArchiveRefusal):  # noqa: E501
            CLOSING.backfill_closing_mode(*arguments)
        mutant = mutated_function(CLOSING.backfill_closing_mode, '        or match.group("target") != target.name\n', "        or False\n")  # noqa: E501
        mutant.__globals__["_approval_evidence"] = mock.Mock(return_value=evidence)
        self.assertEqual(mutant(*arguments).archive_head, self.archive_head)
        invalid_evidence = SimpleNamespace(decision={"resolution": object()})
        resolution_mutant = mutated_function(CLOSING.backfill_closing_mode, "BACKFILL_RESOLUTION.match(resolution) if isinstance(resolution, str) else None", "BACKFILL_RESOLUTION.match(resolution)")  # noqa: E501
        with mock.patch.object(CLOSING, "_approval_evidence", return_value=invalid_evidence): self.assert_refusal(BACKFILL_REFUSAL, lambda: CLOSING.backfill_closing_mode(*arguments))  # noqa: E701, E501
        resolution_mutant.__globals__["_approval_evidence"] = mock.Mock(return_value=invalid_evidence)  # noqa: E501
        with self.assertRaises(TypeError): resolution_mutant(*arguments)  # noqa: E701
