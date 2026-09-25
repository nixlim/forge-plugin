from __future__ import annotations

from unittest import mock

from tests.test_route_config_support import route_config, route_text


class RouteGrammarMixin:
    def test_normative_line_regexes_are_pinned_and_each_form_is_accepted(self) -> None:
        self.assertEqual(route_config.BLANK_RE.pattern, r"^[ \t]*$")
        self.assertEqual(route_config.COMMENT_RE.pattern, r"^[ \t]*#[^\r\n]*$")
        self.assertEqual(
            route_config.SCHEMA_RE.pattern,
            r'^[ \t]*schema[ \t]*=[ \t]*"forge-routes/1"[ \t]*(?:#[^\r\n]*)?$',
        )
        self.assertEqual(
            route_config.TABLE_RE.pattern,
            r"^[ \t]*\[(implementer|review-cheap|review-final|plan)\]"
            r"[ \t]*(?:#[^\r\n]*)?$",
        )
        self.assertEqual(
            route_config.ASSIGNMENT_RE.pattern,
            r'^[ \t]*(provider|model|effort)[ \t]*=[ \t]*"([^"\\\r\n]*)"'
            r"[ \t]*(?:#[^\r\n]*)?$",
        )
        self.assertEqual(
            route_config.MODEL_RE.pattern,
            r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}(\[1m\])?$",
        )
        self.assertEqual(route_config.PROVIDERS, frozenset({"codex", "claude"}))
        self.assertEqual(
            route_config.EFFORTS,
            {
                "codex": frozenset({"minimal", "low", "medium", "high", "ultra"}),
                "claude": frozenset({"low", "medium", "high", "max"}),
            },
        )
        data = b"""\t
# comment
\tschema\t=\t"forge-routes/1"\t# schema
[implementer] # table
provider = "codex"
model = "gpt-5.6-sol"
effort = "ultra"
[review-cheap]
provider = "codex"
model = "gpt-5.6-sol"
effort = "high"
[review-final]
provider = "claude"
model = "fable"
effort = "high"
[plan]
provider = "claude"
model = "fable[1m]"
effort = "max" # assignment
"""
        self.write_routes(data)
        resolution = self.load()
        self.assertTrue(resolution.local_present)
        self.assertEqual([route.route_source for route in resolution.routes], ["local"] * 4)

    def test_malformed_physical_lines_and_forbidden_bytes_are_refused(self) -> None:
        cases = {
            "NUL": (b'schema = "forge-routes/1"\x00\n', "contains NUL"),
            "CR": (b'schema = "forge-routes/1"\r\n', "contains CR"),
            "escape": (
                route_text().replace(b'gpt-5.6-sol', b'gpt\\-5.6-sol'),
                "malformed line 4",
            ),
            "multiline": (
                route_text().replace(b'model = "gpt-5.6-sol"', b'model = """gpt"""'),
                "malformed line 4",
            ),
            "unknown-table": (
                b'schema = "forge-routes/1"\n[other]\n',
                "malformed line 2",
            ),
            "unknown-key": (
                b'schema = "forge-routes/1"\n[implementer]\nsandbox = "read-only"\n',
                "malformed line 3",
            ),
            "invalid-utf8": (b'schema = "forge-routes/1"\n\xff\n', "malformed line 2"),
        }
        for label, (data, cause) in cases.items():
            with self.subTest(label=label):
                self.write_routes(data)
                self.assert_route_refusal(cause)

    def test_schema_table_and_assignment_cardinality_diagnostics(self) -> None:
        cases = {
            "missing-schema": (b"# only a comment\n", "missing schema"),
            "duplicate-schema": (
                b'schema = "forge-routes/1"\nschema = "forge-routes/1"\n',
                "duplicate schema",
            ),
            "table-before-schema": (
                b'[implementer]\nschema = "forge-routes/1"\n',
                "schema must precede table [implementer]",
            ),
            "duplicate-table": (
                b'schema = "forge-routes/1"\n[implementer]\n[implementer]\n',
                "duplicate table implementer",
            ),
            "outside-table": (
                b'schema = "forge-routes/1"\nprovider = "codex"\n',
                "assignment outside a table: provider",
            ),
            "assignment-before-schema": (
                b'provider = "codex"\nschema = "forge-routes/1"\n',
                "assignment outside a table: provider",
            ),
            "duplicate-key": (
                route_text().replace(
                    b'provider = "codex"\n',
                    b'provider = "codex"\nprovider = "codex"\n',
                ),
                "duplicate key provider in [implementer]",
            ),
        }
        for label, (data, cause) in cases.items():
            with self.subTest(label=label):
                self.write_routes(data)
                self.assert_route_refusal(cause)

    def test_each_partial_table_names_its_first_missing_key(self) -> None:
        cases = {
            "provider": b'model = "gpt-5.6-sol"\neffort = "high"\n',
            "model": b'provider = "codex"\neffort = "high"\n',
            "effort": b'provider = "codex"\nmodel = "gpt-5.6-sol"\n',
        }
        prefix = b'schema = "forge-routes/1"\n[review-cheap]\n'
        for missing, assignments in cases.items():
            with self.subTest(missing=missing):
                self.write_routes(prefix + assignments)
                self.assert_route_refusal(f"missing key {missing} in [review-cheap]")

    def test_provider_model_and_effort_values_are_validated_in_their_table(self) -> None:
        cases = {
            "provider": (route_text(provider="openai"), "provider"),
            "inherit": (route_text(model="inherit"), "model"),
            "bad-model": (route_text(model="bad model"), "model"),
            "codex-effort": (route_text(effort="max"), "effort"),
            "claude-effort": (
                route_text(provider="claude", model="fable", effort="ultra"),
                "effort",
            ),
        }
        for label, (data, key) in cases.items():
            with self.subTest(label=label):
                self.write_routes(data)
                self.assert_route_refusal(f"invalid value for {key} in [implementer]")

    def test_model_boundaries_suffix_and_provider_effort_sets(self) -> None:
        valid_models = ("a", "a" * 128, "a" * 128 + "[1m]")
        for model in valid_models:
            with self.subTest(model_length=len(model)):
                self.write_routes(route_text(model=model))
                self.assertEqual(self.load().for_role("implementer").model, model)
        self.write_routes(route_text(model="a" * 129))
        self.assert_route_refusal("invalid value for model in [implementer]")
        efforts = {
            "codex": ("minimal", "low", "medium", "high", "ultra"),
            "claude": ("low", "medium", "high", "max"),
        }
        for provider, values in efforts.items():
            for effort in values:
                with self.subTest(provider=provider, effort=effort):
                    model = "gpt-5.6-sol" if provider == "codex" else "fable"
                    self.write_routes(route_text(provider=provider, model=model, effort=effort))
                    self.assertEqual(self.load().for_role("implementer").effort, effort)

    def test_grammar_disable_control_is_load_bearing(self) -> None:
        self.write_routes(b'schema = "forge-routes/1"\nnot valid\n')

        def assert_control() -> None:
            self.assert_route_refusal("malformed line 2")

        assert_control()
        with mock.patch.object(route_config, "_parse_routes", return_value={}):
            with self.assertRaises(AssertionError):
                assert_control()
