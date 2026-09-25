from __future__ import annotations

import hashlib
import json

from tests.test_route_config_support import codex_toml, route_config, route_text


class RouteResolutionMixin:
    def committed_routes(self) -> dict[str, str]:
        return {
            "system/codex/agents/implementer.toml": codex_toml("system-impl", "low"),
            "system/codex/agents/review-cheap.toml": codex_toml("system-cheap", "medium"),
            "system/codex/agents/plan.toml": codex_toml("system-plan", "high"),
            "agents/review-final.md": (
                "---\nname: review-final\nmodel: claude-system\neffort: max\n---\nbody\n"
            ),
        }

    def test_committed_defaults_and_review_final_frontmatter_resolve_at_head(self) -> None:
        head = self.commit_paths(self.committed_routes())
        expected = {
            "implementer": ("codex", "system-impl", "low"),
            "review-cheap": ("codex", "system-cheap", "medium"),
            "review-final": ("claude", "claude-system", "max"),
            "plan": ("codex", "system-plan", "high"),
        }
        resolution = route_config.load(self.repo, head=head)
        for role, values in expected.items():
            with self.subTest(role=role):
                route = resolution.for_role(role)
                self.assertEqual((route.provider, route.model, route.effort), values)
                self.assertEqual(route.route_source, "committed-default")

    def test_review_final_uses_only_a_valid_initial_frontmatter_block(self) -> None:
        valid = (
            "---\nname: review-final\nmodel: frontmatter-model\neffort: high\n---\n"
            "Body decoys must be ignored.\nmodel: body-model\neffort: low\n"
        )
        head = self.commit_paths({"agents/review-final.md": valid}, "valid frontmatter")
        route = route_config.resolve(self.repo, "review-final", head)
        self.assertEqual((route.model, route.effort), ("frontmatter-model", "high"))

        malformed = {
            "missing opening fence": (
                "name: review-final\nmodel: claude-model\neffort: high\n---\n"
            ),
            "missing closing fence": (
                "---\nname: review-final\nmodel: claude-model\neffort: high\n"
            ),
            "duplicate frontmatter key": (
                "---\nname: review-final\nmodel: first\nmodel: second\n"
                "effort: high\n---\n"
            ),
        }
        expected = "^forge: committed route refused — malformed agents/review-final.md$"
        for label, content in malformed.items():
            with self.subTest(label=label):
                head = self.commit_paths({"agents/review-final.md": content}, label)
                with self.assertRaisesRegex(route_config.RouteRefusal, expected):
                    route_config.resolve(self.repo, "review-final", head)

    def test_dot_codex_precedes_system_and_fixed_head_ignores_worktree(self) -> None:
        system_head = self.commit_paths(self.committed_routes(), "system")
        override_head = self.commit_paths(
            {
                ".codex/agents/implementer.toml": codex_toml("codex-override", "ultra"),
                ".codex/agents/review-final.toml": codex_toml("codex-final", "high"),
            },
            "override",
        )
        override = self.repo / ".codex/agents/implementer.toml"
        override.write_text(codex_toml("dirty-worktree", "minimal"), encoding="utf-8")
        old = route_config.resolve(self.repo, "implementer", system_head)
        new = route_config.resolve(self.repo, "implementer", override_head)
        final = route_config.resolve(self.repo, "review-final", override_head)
        self.assertEqual((old.model, old.effort), ("system-impl", "low"))
        self.assertEqual((new.model, new.effort), ("codex-override", "ultra"))
        self.assertEqual(
            (final.provider, final.model, final.effort, final.route_source),
            ("codex", "codex-final", "high", "committed-default"),
        )

    def test_review_final_committed_default_chain_recomputes_each_digest(self) -> None:
        head = self.commit_paths(
            {
                ".codex/agents/review-final.toml": codex_toml("dot-final", "high"),
                "system/codex/agents/review-final.toml": codex_toml(
                    "system-final", "medium"
                ),
                "agents/review-final.md": (
                    "---\nname: review-final\nmodel: frontmatter-final\n"
                    "effort: max\n---\nbody\n"
                ),
            },
            "all review-final defaults",
        )
        routes = [route_config.resolve(self.repo, "review-final", head)]
        for path in (
            ".codex/agents/review-final.toml",
            "system/codex/agents/review-final.toml",
            "agents/review-final.md",
        ):
            self.git(self.repo, "rm", "-q", "--", path)
            self.git(self.repo, "commit", "-q", "-m", f"remove {path}")
            routes.append(route_config.resolve(self.repo, "review-final", self.head()))
        expected = (
            ("codex", "dot-final", "high", "committed-default"),
            ("codex", "system-final", "medium", "committed-default"),
            ("claude", "frontmatter-final", "max", "committed-default"),
            ("claude", "fable", "high", "plugin-default"),
        )
        for route, values in zip(routes, expected, strict=True):
            with self.subTest(model=route.model):
                self.assertEqual(
                    (route.provider, route.model, route.effort, route.route_source),
                    values,
                )
                preimage = {
                    "schema": "forge-route/1",
                    "role": "review-final",
                    "provider": route.provider,
                    "model": route.model,
                    "effort": route.effort,
                    "route_source": route.route_source,
                }
                canonical = json.dumps(
                    preimage, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")
                self.assertEqual(
                    route.route_sha256, hashlib.sha256(canonical).hexdigest()
                )

    def test_local_table_precedes_committed_defaults(self) -> None:
        head = self.commit_paths(self.committed_routes())
        self.write_routes(route_text(provider="claude", model="local-model", effort="max"))
        route = route_config.resolve(self.repo, "implementer", head)
        self.assertEqual(
            (route.provider, route.model, route.effort, route.route_source),
            ("claude", "local-model", "max", "local"),
        )
        self.assertEqual(
            route_config.resolve(self.repo, "plan", head).route_source,
            "committed-default",
        )

    def test_plugin_defaults_cover_all_roles_when_committed_paths_are_absent(self) -> None:
        expected_defaults = {
            "implementer": ("codex", "gpt-5.6-sol", "ultra"),
            "review-cheap": ("codex", "gpt-5.6-sol", "high"),
            "review-final": ("claude", "fable", "high"),
            "plan": ("codex", "gpt-5.6-sol", "high"),
        }
        self.assertEqual(route_config.PLUGIN_DEFAULTS, expected_defaults)
        resolution = route_config.load(self.repo, head=self.head())
        for role, expected in expected_defaults.items():
            with self.subTest(role=role):
                route = resolution.for_role(role)
                self.assertEqual((route.provider, route.model, route.effort), expected)
                self.assertEqual(route.route_source, "plugin-default")

    def test_route_digest_uses_independent_dm018_canonical_serializer(self) -> None:
        route = route_config.resolve(self.repo, "implementer", self.head())
        preimage = {
            "schema": "forge-route/1",
            "role": route.role,
            "provider": route.provider,
            "model": route.model,
            "effort": route.effort,
            "route_source": route.route_source,
        }
        canonical = json.dumps(
            preimage,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        self.assertFalse(canonical.endswith(b"\n"))
        self.assertEqual(route.route_sha256, hashlib.sha256(canonical).hexdigest())
        self.assertEqual(
            set(route.as_dict()),
            {"role", "provider", "model", "effort", "route_source", "route_sha256"},
        )

    def test_all_eight_profile_sandbox_cells_are_committed(self) -> None:
        expected = {
            ("codex", "implementer"): "workspace-write",
            ("codex", "review-cheap"): "read-only",
            ("codex", "review-final"): "read-only",
            ("codex", "plan"): "read-only",
            ("claude", "implementer"): "instruction-bounded",
            ("claude", "review-cheap"): "instruction-bounded",
            ("claude", "review-final"): "instruction-bounded",
            ("claude", "plan"): "read-only",
        }
        self.assertEqual(route_config.PROFILE_SANDBOXES, expected)
        for key, sandbox in expected.items():
            self.assertEqual(route_config.profile_sandbox(*key), sandbox)

    def test_resolve_and_show_cli_emit_json_and_invalid_head_refuses(self) -> None:
        head = self.head()
        status, stdout, stderr = self.invoke(
            "resolve",
            "--repo",
            str(self.repo),
            "--role",
            "implementer",
            "--head",
            head,
        )
        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(json.loads(stdout)["role"], "implementer")
        status, stdout, stderr = self.invoke("show", "--repo", str(self.repo), "--head", head)
        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual([item["role"] for item in json.loads(stdout)], list(route_config.ROLES))
        status, stdout, stderr = self.invoke(
            "resolve",
            "--repo",
            str(self.repo),
            "--role",
            "plan",
            "--head",
            "not-a-head",
        )
        self.assertEqual((status, stdout), (1, ""))
        self.assertEqual(stderr, "forge: route resolution refused — invalid head\n")
