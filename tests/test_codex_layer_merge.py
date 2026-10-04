"""Unit tests for fail-closed Codex layer preparation."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/forge/codex_layer_merge.py"
HOOK_TEMPLATE = (ROOT / "system/codex/hooks.json").read_bytes()
CONFIG_TEMPLATE = (ROOT / "system/codex/config.toml").read_bytes()
MARKER = ": 'forge-managed';"

spec = importlib.util.spec_from_file_location("forge_codex_layer_merge", HELPER)
assert spec is not None and spec.loader is not None
merge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = merge
spec.loader.exec_module(merge)


def command_handler(command: str) -> dict[str, object]:
    return {"type": "command", "command": command, "timeout": 10}


def decoded_hooks(data: bytes) -> dict[str, object]:
    return json.loads(data.decode("utf-8"))


def deeply_nested_foreign_hooks(depth: int = 900) -> bytes:
    nested = b'{"child":' * depth + b"null" + b"}" * depth
    return (
        b'{"hooks":{"Stop":[{"hooks":[{"command":"stale '
        + MARKER.encode()
        + b' handler"}]}],"SessionStart":[{"hooks":[{"command":"project",'
        b'"metadata":'
        + nested
        + b"}]}]}}\n"
    )


class HookMergeTests(unittest.TestCase):
    def foreign_fixture(self) -> bytes:
        existing = decoded_hooks(HOOK_TEMPLATE)
        stop_group = existing["hooks"]["Stop"][0]
        stop_group["hooks"].append(command_handler("project-stop"))
        stop_group["hooks"].append(command_handler(f"stale {MARKER} handler"))
        existing["hooks"]["Stop"].append(
            {"matcher": "owner", "hooks": [command_handler("project-matcher")]}
        )
        existing["hooks"]["SessionStart"] = [
            {"hooks": [command_handler("project-session-start")]}
        ]
        existing["owner"] = {"preserve": True}
        return (json.dumps(existing, indent=2) + "\n").encode()

    def assert_foreign_content_survives(self) -> None:
        output = merge.merge_hooks(HOOK_TEMPLATE, self.foreign_fixture())
        rendered = output.decode("utf-8")
        self.assertIn("project-stop", rendered)
        self.assertIn("project-matcher", rendered)
        self.assertIn("project-session-start", rendered)
        self.assertIn('"owner"', rendered)

    def _assert_unmarked_template_handler_refuses(self) -> None:
        template = b'{"hooks":{"Stop":[{"hooks":[{"command":"project"}]}]}}\n'
        with self.assertRaisesRegex(
            merge.CodexLayerError,
            r"forge install: malformed Codex template: hooks\.json",
        ):
            merge.merge_hooks(template, b'{"hooks":{}}\n')

    def test_foreign_content_survives_owned_replacement_and_rerun(self) -> None:
        output = merge.merge_hooks(HOOK_TEMPLATE, self.foreign_fixture())
        value = decoded_hooks(output)

        self.assertNotIn("stale", output.decode("utf-8"))
        self.assertEqual(value["owner"], {"preserve": True})
        template_commands = [
            item["command"]
            for group in decoded_hooks(HOOK_TEMPLATE)["hooks"]["Stop"]
            for item in group["hooks"]
        ]
        actual_commands = [
            item["command"]
            for group in value["hooks"]["Stop"]
            for item in group["hooks"]
            if MARKER in item["command"]
        ]
        self.assertEqual(actual_commands, template_commands)
        self.assertEqual(merge.merge_hooks(HOOK_TEMPLATE, output), output)

    def test_owned_only_merge_is_byte_identical_to_template(self) -> None:
        existing = decoded_hooks(HOOK_TEMPLATE)
        existing["hooks"]["SessionStart"] = [
            {"hooks": [command_handler(f"stale {MARKER} handler")]}
        ]
        existing_bytes = (json.dumps(existing, indent=2) + "\n").encode("utf-8")

        self.assertEqual(merge.merge_hooks(HOOK_TEMPLATE, existing_bytes), HOOK_TEMPLATE)

    def test_template_unknown_members_and_empty_groups_are_permitted(self) -> None:
        template = b'{"hooks":{"Empty":[{"hooks":[]}]},"metadata":true}\n'

        output = decoded_hooks(merge.merge_hooks(template, b'{"hooks":{}}\n'))

        self.assertEqual(output["hooks"]["Empty"], [{"hooks": []}])
        self.assertTrue(output["metadata"])

    def test_prior_foreign_top_level_members_are_emitted_final_in_prior_order(self) -> None:
        template = b'{"template_meta":0,"hooks":{},"tail":true}\n'
        existing = (
            b'{"hooks":{},"first":1,"template_meta":2,"second":3}\n'
        )

        output = decoded_hooks(merge.merge_hooks(template, existing))

        self.assertEqual(
            list(output),
            ["hooks", "tail", "first", "template_meta", "second"],
        )

    def test_marker_spoof_is_intentionally_treated_as_plugin_owned(self) -> None:
        spoof = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [command_handler(f"project copied {MARKER} marker")]}
                ]
            }
        }
        output = merge.merge_hooks(
            HOOK_TEMPLATE, (json.dumps(spoof) + "\n").encode("utf-8")
        )

        self.assertNotIn("SessionStart", decoded_hooks(output)["hooks"])
        init_skill = (ROOT / "skills/init/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("intentionally treated as Forge-owned and replaced", init_skill)

    def test_marker_outside_a_handler_does_not_claim_foreign_hooks(self) -> None:
        existing = {
            "hooks": {"SessionStart": [{"hooks": [command_handler("project")] }]},
            "note": MARKER,
        }
        parsed = merge.parse_hooks((json.dumps(existing) + "\n").encode("utf-8"))
        self.assertFalse(merge._has_plugin_handlers(parsed))

    def test_metadata_only_residual_group_is_preserved(self) -> None:
        existing = {
            "hooks": {
                "Stop": [
                    {
                        "matcher": "project-metadata",
                        "hooks": [command_handler(f"stale {MARKER} handler")],
                    }
                ]
            }
        }

        output = decoded_hooks(
            merge.merge_hooks(
                HOOK_TEMPLATE, (json.dumps(existing) + "\n").encode("utf-8")
            )
        )

        self.assertEqual(
            output["hooks"]["Stop"][-1],
            {"matcher": "project-metadata", "hooks": []},
        )

    def test_empty_foreign_event_is_preserved(self) -> None:
        existing = b'{"hooks":{"SessionStart":[]}}\n'

        output = decoded_hooks(merge.merge_hooks(HOOK_TEMPLATE, existing))

        self.assertIn("SessionStart", output["hooks"])
        self.assertEqual(output["hooks"]["SessionStart"], [])

    def test_marker_free_event_with_only_empty_group_is_preserved(self) -> None:
        existing = b'{"hooks":{"SessionStart":[{"hooks":[]}]}}\n'

        output = decoded_hooks(merge.merge_hooks(HOOK_TEMPLATE, existing))

        self.assertIn("SessionStart", output["hooks"])
        self.assertEqual(output["hooks"]["SessionStart"], [])

    def test_duplicate_keys_and_invalid_handler_shape_refuse(self) -> None:
        cases = (
            b'{"hooks": {}, "hooks": {}}\n',
            b'{"hooks":{"Stop":[{"hooks":[{"type":"command"}]}]}}\n',
            b'{"hooks": [],}\n',
            b'{"hooks":{"Stop":[{"hooks":[{"command":"ok","timeout":NaN}]}]}}',
            b'{"hooks":{"Stop":[{"hooks":[{"command":"\\ud800"}]}]}}',
            b"\xff",
        )
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaisesRegex(
                    merge.CodexLayerError, r"forge install: malformed \.codex/hooks\.json"
                ):
                    merge.parse_hooks(data)

    def test_large_foreign_json_numbers_are_preserved_losslessly(self) -> None:
        integer = b"9" * 5000
        existing = b'{"hooks":{},"large":' + integer + b',"exponent":1e400}\n'

        output = merge.merge_hooks(HOOK_TEMPLATE, existing)

        self.assertIn(b'"large": ' + integer, output)
        self.assertIn(b'"exponent": 1e400', output)
        self.assertEqual(merge.merge_hooks(HOOK_TEMPLATE, output), output)

    def test_numeric_handler_command_refuses_and_number_type_is_distinct(self) -> None:
        for token in (b"123", b"1e400", b"-2"):
            with self.subTest(token=token):
                malformed = b'{"hooks":{"Stop":[{"hooks":[{"command":' + token + b"}]}]}}"
                with self.assertRaisesRegex(
                    merge.CodexLayerError,
                    r"forge install: malformed \.codex/hooks\.json",
                ):
                    merge.parse_hooks(malformed)
        self.assertNotEqual(
            merge._parse_json(b'{"value":1}', "fixture"),
            merge._parse_json(b'{"value":"1"}', "fixture"),
        )

    def test_oversize_hook_input_refuses(self) -> None:
        prefix = b'{"hooks":{},"padding":"'
        suffix = b'"}'
        boundary = prefix + b"x" * (
            merge.MAX_INPUT_BYTES - len(prefix) - len(suffix)
        ) + suffix
        self.assertEqual(len(boundary), merge.MAX_INPUT_BYTES)
        self.assertEqual(merge.parse_hooks(boundary)["hooks"], {})

        with self.assertRaisesRegex(
            merge.CodexLayerError, r"forge install: malformed \.codex/hooks\.json"
        ):
            merge.parse_hooks(boundary + b" ")

    def test_boundary_input_that_cannot_stay_reinitializable_refuses(self) -> None:
        prefix = (
            b'{"hooks":{"Stop":[{"hooks":[{"command":"stale '
            + MARKER.encode()
            + b'"}]}]},"padding":"'
        )
        suffix = b'"}'
        existing = prefix + b"x" * (
            merge.MAX_INPUT_BYTES - len(prefix) - len(suffix)
        ) + suffix

        self.assertEqual(len(existing), merge.MAX_INPUT_BYTES)
        with self.assertRaisesRegex(
            merge.CodexLayerError, "Codex hooks merge output is oversized"
        ):
            merge.merge_hooks(HOOK_TEMPLATE, existing)

        smaller = existing[: -(len(HOOK_TEMPLATE) + 4096)] + suffix
        output = merge.merge_hooks(HOOK_TEMPLATE, smaller)
        self.assertLessEqual(len(output), merge.MAX_INPUT_BYTES)
        self.assertEqual(merge.merge_hooks(HOOK_TEMPLATE, output), output)

    def test_ownership_control_disable_leg_detects_foreign_loss(self) -> None:
        self.assert_foreign_content_survives()
        with mock.patch.object(merge, "is_plugin_handler", return_value=True):
            with self.assertRaises(AssertionError):
                self.assert_foreign_content_survives()

    def test_template_marker_control_disable_leg_detects_unmarked_handler(self) -> None:
        self._assert_unmarked_template_handler_refuses()
        with mock.patch.object(
            merge, "_validate_hook_template", return_value=None
        ):
            with self.assertRaises(AssertionError):
                self._assert_unmarked_template_handler_refuses()

    def test_merge_verification_disable_leg_detects_foreign_loss(self) -> None:
        foreign = self.foreign_fixture()
        with mock.patch.object(
            merge, "_render_json_document", return_value=HOOK_TEMPLATE
        ):
            with self.assertRaisesRegex(
                merge.CodexLayerError, "hooks merge verification failed"
            ):
                merge.merge_hooks(HOOK_TEMPLATE, foreign)

        with (
            mock.patch.object(
                merge, "_render_json_document", return_value=HOOK_TEMPLATE
            ),
            mock.patch.object(merge, "_verify_hook_output", return_value=None),
        ):
            corrupted = merge.merge_hooks(HOOK_TEMPLATE, foreign)
        with self.assertRaises(AssertionError):
            self.assertIn("project-stop", corrupted.decode("utf-8"))

    def test_merge_verification_rejects_object_order_corruption(self) -> None:
        expected = merge.parse_hooks(
            b'{"hooks":{"First":[],"Second":[]},"before":1,"after":2}'
        )
        reordered = b'{"after":2,"before":1,"hooks":{"Second":[],"First":[]}}'

        with self.assertRaisesRegex(
            merge.CodexLayerError, "hooks merge verification failed"
        ):
            merge._verify_hook_output(reordered, expected)


class ConfigCollisionTests(unittest.TestCase):
    def assert_foreign_config_collides(self) -> None:
        foreign = CONFIG_TEMPLATE + (
            b'\n[agents."project-agent"]\nconfig_file = "./agents/project.toml"\n'
        )
        self.assertTrue(merge.config_requires_collision(foreign, CONFIG_TEMPLATE))

    def test_owned_value_changes_refresh_but_foreign_keys_collide(self) -> None:
        owned_only = CONFIG_TEMPLATE.replace(b'on-failure', b'never', 1)
        foreign_root = CONFIG_TEMPLATE + b'\n[features]\nhooks = true\n'
        foreign_agent = CONFIG_TEMPLATE + (
            b'\n[agents."project-agent"]\nconfig_file = "./agents/project.toml"\n'
        )

        self.assertFalse(merge.config_requires_collision(owned_only, CONFIG_TEMPLATE))
        self.assertTrue(merge.config_requires_collision(foreign_root, CONFIG_TEMPLATE))
        self.assertTrue(merge.config_requires_collision(foreign_agent, CONFIG_TEMPLATE))

    def test_foreign_comments_collide_but_owned_prefix_spoofs_refresh(self) -> None:
        foreign = CONFIG_TEMPLATE + b"\n# project comment\n"
        owned_spoofs = CONFIG_TEMPLATE + (
            "\n# forge-managed copied by project\n"
            "# forge: modified from upstream — copied by project\n"
        ).encode()
        hash_in_owned_value = CONFIG_TEMPLATE.replace(
            b'approval_policy = "on-failure"',
            b'approval_policy = "project#value"',
        )

        self.assertTrue(merge.config_requires_collision(foreign, CONFIG_TEMPLATE))
        self.assertFalse(
            merge.config_requires_collision(owned_spoofs, CONFIG_TEMPLATE)
        )
        self.assertFalse(
            merge.config_requires_collision(hash_in_owned_value, CONFIG_TEMPLATE)
        )
        for marker in (
            b"  # forge-managed copied by project  ",
            "# forge: modified from upstream — copied by project".encode(),
        ):
            with self.subTest(marker=marker):
                spoof_only = CONFIG_TEMPLATE.replace(
                    b"# forge: modified from upstream "
                    b"\xe2\x80\x94 reduced the Codex layer to the two FR-038 agents "
                    b"and applied the specified routing limits.\n# forge-managed",
                    marker,
                )
                self.assertTrue(merge._is_managed_config(spoof_only))
                self.assertEqual(
                    merge._prepare_config(
                        CONFIG_TEMPLATE, spoof_only, replace=False
                    ).action,
                    "install",
                )

        string_marker = CONFIG_TEMPLATE.split(b"approval_policy", 1)[1]
        string_marker = b'approval_policy = """value\n# forge-managed\n"""\n' + (
            string_marker.split(b"\n", 1)[1]
        )
        self.assertFalse(merge._is_managed_config(string_marker))
        self.assertEqual(
            merge._prepare_config(CONFIG_TEMPLATE, string_marker, replace=False).action,
            "collision",
        )
        init_skill = (ROOT / "skills/init/SKILL.md").read_text(encoding="utf-8")
        self.assertIn(
            "a project comment\nthat copies either prefix is intentionally treated as "
            "Forge-owned",
            init_skill,
        )

    def test_missing_tomllib_collides(self) -> None:
        with mock.patch.object(merge, "tomllib", None):
            self.assertTrue(
                merge.config_requires_collision(CONFIG_TEMPLATE, CONFIG_TEMPLATE)
            )

    def test_known_agent_type_changes_refresh_unless_they_add_members(self) -> None:
        scalar_for_table = b"""approval_policy = "never"
sandbox_mode = "read-only"
[agents]
implementer = "changed"
"""
        empty_table_for_scalar = CONFIG_TEMPLATE.replace(
            b'config_file = "./agents/implementer.toml"',
            b"config_file = {}",
            1,
        )
        added_member_for_scalar = CONFIG_TEMPLATE.replace(
            b'config_file = "./agents/implementer.toml"',
            b'config_file = { project = "value" }',
            1,
        )
        added_member_under_root_scalar = CONFIG_TEMPLATE.replace(
            b'approval_policy = "on-failure"',
            b'approval_policy = { project = true }',
            1,
        )
        array_table_member = b"""# forge-managed
[agents]
[[agents.implementer]]
project = "foreign"
"""

        self.assertFalse(
            merge.config_requires_collision(scalar_for_table, CONFIG_TEMPLATE)
        )
        self.assertFalse(
            merge.config_requires_collision(empty_table_for_scalar, CONFIG_TEMPLATE)
        )
        self.assertTrue(
            merge.config_requires_collision(added_member_for_scalar, CONFIG_TEMPLATE)
        )
        self.assertFalse(
            merge.config_requires_collision(
                added_member_under_root_scalar, CONFIG_TEMPLATE
            )
        )
        self.assertTrue(
            merge.config_requires_collision(array_table_member, CONFIG_TEMPLATE)
        )

    def test_malformed_managed_toml_refuses(self) -> None:
        malformed = b'# forge-managed\napproval_policy = [\n'
        with self.assertRaisesRegex(
            merge.CodexLayerError, r"forge install: malformed \.codex/config\.toml"
        ):
            merge.config_requires_collision(malformed, CONFIG_TEMPLATE)

    def test_foreign_config_control_disable_leg_detects_silent_loss(self) -> None:
        self.assert_foreign_config_collides()
        with mock.patch.object(merge, "_tree_has_unknown", return_value=False):
            with self.assertRaises(AssertionError):
                self.assert_foreign_config_collides()


class PrepareTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="forge-codex-merge-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.templates = self.root / "templates"
        self.target = self.root / "target"
        self.output = self.root / "output"
        self.templates.mkdir()
        self.target.mkdir()
        (self.templates / "config.toml").write_bytes(CONFIG_TEMPLATE)
        (self.templates / "hooks.json").write_bytes(HOOK_TEMPLATE)

    def test_changed_owned_config_values_are_refreshed_from_template(self) -> None:
        (self.target / "config.toml").write_bytes(
            CONFIG_TEMPLATE.replace(b'on-failure', b'never', 1)
        )

        merge.prepare(self.templates, self.target, self.output, "none")

        self.assertIn(
            "config.toml=install",
            (self.output / "plan").read_text(encoding="ascii"),
        )
        self.assertEqual((self.output / "config.toml").read_bytes(), CONFIG_TEMPLATE)

    def test_foreign_config_collides_while_managed_hooks_merge(self) -> None:
        (self.target / "config.toml").write_bytes(
            CONFIG_TEMPLATE + b'\nmodel = "project"\n'
        )
        hooks = decoded_hooks(HOOK_TEMPLATE)
        hooks["hooks"]["SessionStart"] = [
            {"hooks": [command_handler("project-session")]}
        ]
        (self.target / "hooks.json").write_text(
            json.dumps(hooks) + "\n", encoding="utf-8"
        )

        merge.prepare(self.templates, self.target, self.output, "none")

        self.assertEqual(
            (self.output / "plan").read_text(encoding="ascii"),
            "config.toml=collision\nhooks.json=install\n",
        )
        self.assertEqual((self.output / "config.toml").read_bytes(), CONFIG_TEMPLATE)
        self.assertIn("project-session", (self.output / "hooks.json").read_text())

    def test_missing_tomllib_stages_config_collision(self) -> None:
        (self.target / "config.toml").write_bytes(CONFIG_TEMPLATE)
        with mock.patch.object(merge, "tomllib", None):
            merge.prepare(self.templates, self.target, self.output, "none")

        self.assertIn(
            "config.toml=collision",
            (self.output / "plan").read_text(encoding="ascii"),
        )

        (self.target / "config.toml").write_bytes(
            CONFIG_TEMPLATE.replace(b'on-failure', b'never', 1)
        )
        with mock.patch.object(merge, "tomllib", None):
            merge.prepare(self.templates, self.target, self.output, "none")
        self.assertIn(
            "config.toml=collision",
            (self.output / "plan").read_text(encoding="ascii"),
        )

    def test_replacement_inputs_are_fully_preflighted(self) -> None:
        cases = {
            "config.toml": b"approval_policy = [\n",
            "hooks.json": b'{"hooks":{"Stop":[{"command":"legacy"}]}}\n',
        }
        for filename, contents in cases.items():
            with self.subTest(filename=filename):
                for path in self.target.iterdir():
                    path.unlink()
                (self.target / filename).write_bytes(contents)
                with self.assertRaisesRegex(
                    merge.CodexLayerError,
                    rf"forge install: malformed \.codex/{re.escape(filename)}",
                ):
                    merge.prepare(self.templates, self.target, self.output, filename)

    def test_valid_replacement_inputs_install_fresh_templates(self) -> None:
        hooks = decoded_hooks(HOOK_TEMPLATE)
        hooks["hooks"]["Stop"][0]["hooks"][0]["command"] = (
            "bash legacy/scripts/aggregate-telemetry.sh .tmp/decisions "
            "--csv .tmp/telemetry-latest.csv"
        )
        (self.target / "config.toml").write_bytes(CONFIG_TEMPLATE)
        (self.target / "hooks.json").write_text(
            json.dumps(hooks) + "\n", encoding="utf-8"
        )

        merge.prepare(
            self.templates, self.target, self.output, "config.toml,hooks.json"
        )

        self.assertEqual(
            (self.output / "plan").read_text(encoding="ascii"),
            "config.toml=install\nhooks.json=install\n",
        )
        self.assertEqual((self.output / "config.toml").read_bytes(), CONFIG_TEMPLATE)
        self.assertEqual((self.output / "hooks.json").read_bytes(), HOOK_TEMPLATE)

    def test_missing_tomllib_collides_even_for_replacement_input(self) -> None:
        (self.target / "config.toml").write_bytes(CONFIG_TEMPLATE)

        with mock.patch.object(merge, "tomllib", None):
            merge.prepare(self.templates, self.target, self.output, "config.toml")

        self.assertIn(
            "config.toml=collision",
            (self.output / "plan").read_text(encoding="ascii"),
        )

    def test_missing_tomllib_still_checks_config_byte_contract(self) -> None:
        with mock.patch.object(merge, "tomllib", None):
            self.assertEqual(
                merge._prepare_config(CONFIG_TEMPLATE, None, replace=False).action,
                "install",
            )
            for template, existing, label in (
                (b"\xff", None, "Codex template config.toml"),
                (b"x" * (merge.MAX_INPUT_BYTES + 1), None, "Codex template config.toml"),
                (CONFIG_TEMPLATE, b"\xff", ".codex/config.toml"),
                (
                    CONFIG_TEMPLATE,
                    b"x" * (merge.MAX_INPUT_BYTES + 1),
                    ".codex/config.toml",
                ),
            ):
                with self.subTest(label=label, size=len(template) + len(existing or b"")):
                    with self.assertRaisesRegex(
                        merge.CodexLayerError,
                        rf"forge install: malformed {re.escape(label)}",
                    ):
                        merge._prepare_config(template, existing, replace=False)

    def test_differing_project_sidecar_refuses_during_preflight(self) -> None:
        (self.target / "config.toml").write_bytes(
            CONFIG_TEMPLATE + b'\n[features]\nhooks = true\n'
        )
        (self.target / "config.toml.forge-new").write_bytes(b"project sidecar\n")

        with self.assertRaisesRegex(
            merge.CodexLayerError, "refusing to overwrite non-forge collision sibling"
        ):
            merge.prepare(self.templates, self.target, self.output, "none")
        self.assertFalse(self.output.exists())

    def test_differing_marker_owned_sidecar_also_refuses(self) -> None:
        (self.target / "config.toml").write_bytes(
            CONFIG_TEMPLATE + b'\n[features]\nhooks = true\n'
        )
        (self.target / "config.toml.forge-new").write_bytes(
            CONFIG_TEMPLATE.replace(b'on-failure', b'never', 1)
        )

        with self.assertRaisesRegex(
            merge.CodexLayerError, "refusing to overwrite non-forge collision sibling"
        ):
            merge.prepare(self.templates, self.target, self.output, "none")

    def test_stale_sidecar_refuses_after_main_file_is_resolved(self) -> None:
        (self.target / "config.toml").write_bytes(CONFIG_TEMPLATE)
        (self.target / "config.toml.forge-new").write_bytes(b"stale candidate\n")

        with self.assertRaisesRegex(
            merge.CodexLayerError, "refusing to overwrite non-forge collision sibling"
        ):
            merge.prepare(self.templates, self.target, self.output, "none")

    def test_hook_sidecar_identity_is_bound_to_fresh_template(self) -> None:
        hooks = decoded_hooks(HOOK_TEMPLATE)
        hooks["hooks"]["Stop"][0]["hooks"].append(command_handler("project-stop"))
        (self.target / "hooks.json").write_text(
            json.dumps(hooks) + "\n", encoding="utf-8"
        )
        (self.target / "hooks.json.forge-new").write_bytes(HOOK_TEMPLATE)

        merge.prepare(self.templates, self.target, self.output, "none")
        merged = (self.output / "hooks.json").read_bytes()
        self.assertIn(b"project-stop", merged)

        (self.target / "hooks.json.forge-new").write_bytes(merged)
        with self.assertRaisesRegex(
            merge.CodexLayerError, "refusing to overwrite non-forge collision sibling"
        ):
            merge.prepare(self.templates, self.target, self.output, "none")

    def test_precondition_snapshot_detects_main_and_sidecar_changes(self) -> None:
        merge.prepare(self.templates, self.target, self.output, "none")
        merge.verify_preconditions(self.output / "preconditions", self.target)

        for relative in ("config.toml", "hooks.json.forge-new"):
            with self.subTest(relative=relative):
                path = self.target / relative
                path.write_bytes(b"raced project bytes\n")
                with self.assertRaisesRegex(
                    merge.CodexLayerError, "Codex input changed after preflight"
                ):
                    merge.verify_preconditions(
                        self.output / "preconditions", self.target
                    )
                path.unlink()

    def test_unmarked_malformed_existing_files_refuse_in_preflight(self) -> None:
        cases = {
            "config.toml": b"project = [\n",
            "hooks.json": b'{"hooks": invalid}\n',
        }
        for filename, contents in cases.items():
            with self.subTest(filename=filename):
                for path in self.target.iterdir():
                    path.unlink()
                (self.target / filename).write_bytes(contents)
                with self.assertRaisesRegex(
                    merge.CodexLayerError,
                    rf"forge install: malformed \.codex/{re.escape(filename)}",
                ):
                    merge.prepare(self.templates, self.target, self.output, "none")

    def test_deep_foreign_json_reports_malformed_without_traceback(self) -> None:
        existing = deeply_nested_foreign_hooks()
        parsed = merge.parse_hooks(existing)
        self.assertEqual(
            parsed["hooks"]["SessionStart"][0]["hooks"][0]["command"],
            "project",
        )
        (self.target / "hooks.json").write_bytes(existing)
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            status = merge.main(
                [
                    "prepare",
                    str(self.templates),
                    str(self.target),
                    str(self.output),
                    "none",
                ]
            )

        self.assertEqual(status, 2)
        self.assertEqual(
            stderr.getvalue(), "forge install: malformed .codex/hooks.json\n"
        )
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_symlinked_existing_input_refuses(self) -> None:
        outside = self.root / "outside-hooks.json"
        outside.write_bytes(HOOK_TEMPLATE)
        (self.target / "hooks.json").symlink_to(outside)

        with self.assertRaisesRegex(
            merge.CodexLayerError, "destination is not a regular file"
        ):
            merge.prepare(self.templates, self.target, self.output, "none")

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO files require POSIX")
    def test_fifo_input_refuses_without_blocking_snapshot_or_verify(self) -> None:
        fifo = self.target / "hooks.json"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(
            merge.CodexLayerError, "destination is not a regular file"
        ):
            merge.snapshot_inputs(self.target, self.output)

        fifo.unlink()
        merge.prepare(self.templates, self.target, self.output, "none")
        os.mkfifo(fifo)
        with self.assertRaisesRegex(
            merge.CodexLayerError, "destination is not a regular file"
        ):
            merge.verify_preconditions(self.output / "preconditions", self.target)

    def test_every_template_is_utf8_bounded_and_regular(self) -> None:
        extra = self.templates / "agents/plan.toml"
        extra.parent.mkdir()
        cases = (
            ("invalid UTF-8", b"\xff", r"malformed Codex template agents/plan\.toml"),
            (
                "malformed TOML",
                b"model = [\n",
                r"malformed Codex template agents/plan\.toml",
            ),
            (
                "oversized",
                b"x" * (merge.MAX_INPUT_BYTES + 1),
                r"malformed Codex template agents/plan\.toml",
            ),
        )
        for label, contents, diagnostic in cases:
            with self.subTest(case=label):
                extra.write_bytes(contents)
                with self.assertRaisesRegex(merge.CodexLayerError, diagnostic):
                    merge.prepare(self.templates, self.target, self.output, "none")
                self.assertFalse(self.output.exists())

        extra.unlink()
        outside = self.root / "outside.toml"
        outside.write_text("value = 1\n", encoding="utf-8")
        extra.symlink_to(outside)
        with self.assertRaisesRegex(
            merge.CodexLayerError, "Codex template is not a regular file"
        ):
            merge.prepare(self.templates, self.target, self.output, "none")


if __name__ == "__main__":
    unittest.main()
