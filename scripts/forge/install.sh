#!/usr/bin/env bash
# Mechanical Forge installer. Run from the root of the target Git repository.
#
# Usage:
#   install.sh [plugin-root]
#
# The positional plugin root takes precedence over CLAUDE_PLUGIN_ROOT.

set -euo pipefail

if [ "$#" -gt 1 ]; then
    echo "forge install: expected at most one plugin-root argument" >&2
    exit 2
fi

if [ "$#" -eq 1 ]; then
    PLUGIN_ROOT_INPUT="$1"
else
    PLUGIN_ROOT_INPUT="${CLAUDE_PLUGIN_ROOT:-}"
fi

if [ -z "${PLUGIN_ROOT_INPUT}" ]; then
    echo "forge install: plugin root is required as an argument or CLAUDE_PLUGIN_ROOT" >&2
    exit 2
fi

if [ ! -d "${PLUGIN_ROOT_INPUT}" ]; then
    echo "forge install: plugin root is not a directory: ${PLUGIN_ROOT_INPUT}" >&2
    exit 2
fi

PLUGIN_ROOT="$(cd "${PLUGIN_ROOT_INPUT}" && pwd -P)"
TARGET_ROOT="$(pwd -P)"

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
    echo "forge install: current directory is not a Git repository" >&2
    exit 2
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
REPO_ROOT="$(cd "${REPO_ROOT}" && pwd -P)"
if [ "${TARGET_ROOT}" != "${REPO_ROOT}" ]; then
    echo "forge install: run from the repository root (${REPO_ROOT})" >&2
    exit 2
fi

PROJECT_TEMPLATE="${PLUGIN_ROOT}/system/template/forge-project.md"
CODEX_SOURCE="${PLUGIN_ROOT}/system/codex"
GITIGNORE_SOURCE="${PLUGIN_ROOT}/system/template/gitignore-block.txt"
MIGRATION_HELPER="${PLUGIN_ROOT}/scripts/forge/migrate-upstream.py"

if [ ! -f "${PROJECT_TEMPLATE}" ]; then
    echo "forge install: missing project template: ${PROJECT_TEMPLATE}" >&2
    exit 2
fi
if [ ! -d "${CODEX_SOURCE}" ]; then
    echo "forge install: missing Codex layer: ${CODEX_SOURCE}" >&2
    exit 2
fi
if [ ! -f "${GITIGNORE_SOURCE}" ]; then
    echo "forge install: missing gitignore block: ${GITIGNORE_SOURCE}" >&2
    exit 2
fi

MANIFEST_SCHEMA="fresh"
if [ -f "${TARGET_ROOT}/.forge-manifest" ]; then
    if [ ! -f "${MIGRATION_HELPER}" ]; then
        echo "forge install: missing migration helper: ${MIGRATION_HELPER}" >&2
        exit 2
    fi
    MANIFEST_SCHEMA="$(python3 "${MIGRATION_HELPER}" --classify "${TARGET_ROOT}/.forge-manifest")" || exit 2
    case "${MANIFEST_SCHEMA}" in
        plugin|upstream) ;;
        malformed)
            echo "forge install: malformed .forge-manifest" >&2
            exit 2
            ;;
        *)
            echo "forge install: invalid manifest classifier result: ${MANIFEST_SCHEMA}" >&2
            exit 2
            ;;
    esac
fi

INSTALL_DATE="$(date +%Y-%m-%d)"
PROJECT_NAME="$(basename "${TARGET_ROOT}")"
TAKEN_COUNT=0
SKIPPED_COUNT=0
ACTIVE_TMP=""

cleanup() {
    if [ -n "${ACTIVE_TMP}" ] && [ -e "${ACTIVE_TMP}" ]; then
        rm -f "${ACTIVE_TMP}"
    fi
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

record_taken() {
    TAKEN_COUNT=$((TAKEN_COUNT + 1))
    printf '  taken:   %s\n' "$1"
}

record_skipped() {
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    printf '  skipped: %s\n' "$1"
}

new_temp_for() {
    local destination="$1"
    mkdir -p "$(dirname "${destination}")"
    ACTIVE_TMP="$(mktemp "${destination}.forge-tmp.XXXXXX")"
}

render_tokens() {
    local path="$1"
    FORGE_RENDER_INSTALL_DATE="${INSTALL_DATE}" \
    FORGE_RENDER_PROJECT_NAME="${PROJECT_NAME}" \
        perl -pi -e '
            s/\{\{FORGE_INSTALL_DATE\}\}/$ENV{FORGE_RENDER_INSTALL_DATE}/g;
            s/\{\{FORGE_PROJECT_NAME\}\}/$ENV{FORGE_RENDER_PROJECT_NAME}/g;
        ' "${path}"
}

# Move ACTIVE_TMP into place only when its bytes differ from the destination.
install_prepared() {
    local destination="$1"
    local label="$2"
    local state="created"

    if { [ -e "${destination}" ] || [ -L "${destination}" ]; } \
        && [ ! -f "${destination}" ]; then
        echo "forge install: destination is not a regular file: ${destination}" >&2
        exit 2
    fi

    if [ -f "${destination}" ] && cmp -s "${ACTIVE_TMP}" "${destination}"; then
        rm -f "${ACTIVE_TMP}"
        ACTIVE_TMP=""
        record_skipped "${label} (unchanged)"
        return 0
    fi

    if [ -e "${destination}" ]; then
        state="updated"
    fi
    chmod 0644 "${ACTIVE_TMP}"
    mv "${ACTIVE_TMP}" "${destination}"
    ACTIVE_TMP=""
    record_taken "${label} (${state})"
}

# Validate the fresh region scaffold, then carry forward only old region bodies
# whose forge-init sentinel has been removed. Everything outside those bodies
# remains the freshly rendered template.
validate_and_merge_regions() {
    local fresh="$1"
    local previous="${2:-}"

    perl -0777 -e '
        use strict;
        use warnings;

        my ($fresh_path, $previous_path) = @ARGV;

        sub parse_regions {
            my ($document, $label, $order) = @_;
            my $marker_like_count = () =
                $document =~ /<!-- FORGE:REGION\b/g;
            my @markers;
            while ($document =~ /<!-- FORGE:REGION (\S+) (BEGIN|END) -->/g) {
                push @markers, {
                    name  => $1,
                    kind  => $2,
                    start => $-[0],
                    end   => $+[0],
                };
            }
            die "$label has a malformed Forge region marker\n"
                unless $marker_like_count == scalar @markers;

            my %regions;
            my $open;
            for my $marker (@markers) {
                if ($marker->{kind} eq "BEGIN") {
                    die "$label has misnested Forge region markers\n"
                        if defined $open;
                    die "$label has duplicate Forge region $marker->{name}\n"
                        if exists $regions{$marker->{name}};
                    $open = $marker;
                    next;
                }

                die "$label has an unmatched Forge region END marker\n"
                    unless defined $open;
                die "$label has mismatched Forge region names: "
                    . "$open->{name} and $marker->{name}\n"
                    unless $open->{name} eq $marker->{name};
                $regions{$open->{name}} = substr(
                    $document,
                    $open->{end},
                    $marker->{start} - $open->{end},
                );
                push @{$order}, $open->{name} if defined $order;
                undef $open;
            }
            die "$label has an unmatched Forge region BEGIN marker\n"
                if defined $open;
            return \%regions;
        }

        sub dependency_manifest_block {
            my ($body) = @_;
            my $begin = "<!-- FORGE:DEPENDENCY-MANIFEST-PATHS BEGIN -->";
            my $end = "<!-- FORGE:DEPENDENCY-MANIFEST-PATHS END -->";
            my $begin_count = () = $body =~ /\Q$begin\E/g;
            my $end_count = () = $body =~ /\Q$end\E/g;
            my $start = index($body, $begin);
            my $end_start = index($body, $end);
            die "forge: dependency-manifest block malformed — repair forge-project.md\n"
                unless $begin_count == 1
                    && $end_count == 1
                    && $start >= 0
                    && $end_start > $start;
            my $after_end = $end_start + length($end);
            return (substr($body, $start, $after_end - $start), $start, $after_end);
        }

        open my $fresh_fh, "<", $fresh_path
            or die "cannot read $fresh_path: $!\n";
        binmode $fresh_fh;
        my $fresh = <$fresh_fh>;
        close $fresh_fh or die "cannot close $fresh_path: $!\n";

        my @fresh_order;
        my $fresh_regions = parse_regions(
            $fresh,
            "fresh forge-project template",
            \@fresh_order,
        );
        my @required = qw(
            project-overview
            file-categories
            stack-validations
            gate1-test-command
            changelog-policy
            review-prompt-project-focus
            project-triggers
            completeness-project-items
            agent-project-context
            mutation-testing
            invariants
            risk-tiers
            drift-config
            trigger-paths
        );
        my @legacy_required = @required[0 .. 8];
        my %required = map { $_ => 1 } @required;
        for my $name (@required) {
            die "fresh forge-project template is missing region $name\n"
                unless exists $fresh_regions->{$name};
        }
        for my $name (keys %{$fresh_regions}) {
            die "fresh forge-project template has unexpected region $name\n"
                unless exists $required{$name};
        }
        die "fresh forge-project template has regions out of order\n"
            unless join("\0", @fresh_order) eq join("\0", @required);
        my ($fresh_dependency_block) = dependency_manifest_block(
            $fresh_regions->{"risk-tiers"},
        );

        if (length $previous_path) {
            open my $previous_fh, "<", $previous_path
                or die "cannot read $previous_path: $!\n";
            binmode $previous_fh;
            my $previous = <$previous_fh>;
            $previous = "" unless defined $previous;
            close $previous_fh or die "cannot close $previous_path: $!\n";

            my @previous_order;
            my $previous_regions = parse_regions(
                $previous,
                "existing forge-project.md",
                \@previous_order,
            );
            for my $name (keys %{$previous_regions}) {
                die "existing forge-project.md has unexpected region $name\n"
                    unless exists $required{$name};
            }
            my $previous_inventory = join("\0", @previous_order);
            my $current_inventory = join("\0", @required);
            my $legacy_inventory = join("\0", @legacy_required);
            die "existing forge-project.md has missing or reordered regions\n"
                unless $previous_inventory eq $current_inventory
                    || $previous_inventory eq $legacy_inventory;
            my %filled = map {
                $_ => $previous_regions->{$_}
            } grep {
                $previous_regions->{$_} !~ /forge-init:/
            } keys %{$previous_regions};

            if (exists $filled{"risk-tiers"}) {
                my $body = $filled{"risk-tiers"};
                my (undef, $start, $after_end) = dependency_manifest_block($body);
                substr(
                    $body,
                    $start,
                    $after_end - $start,
                    $fresh_dependency_block,
                );
                $filled{"risk-tiers"} = $body;
            }

            $fresh =~ s{(<!-- FORGE:REGION (\S+) BEGIN -->).*?(<!-- FORGE:REGION \2 END -->)}{
                exists $filled{$2} ? $1 . $filled{$2} . $3 : $&
            }gse;
        }

        open my $output_fh, ">", $fresh_path
            or die "cannot write $fresh_path: $!\n";
        binmode $output_fh;
        print {$output_fh} $fresh;
        close $output_fh or die "cannot close $fresh_path: $!\n";
    ' "${fresh}" "${previous}"
}

install_forge_project() {
    local destination="${TARGET_ROOT}/forge-project.md"

    new_temp_for "${destination}"
    cp "${PROJECT_TEMPLATE}" "${ACTIVE_TMP}"
    render_tokens "${ACTIVE_TMP}"
    if [ -f "${destination}" ]; then
        validate_and_merge_regions "${ACTIVE_TMP}" "${destination}"
    else
        validate_and_merge_regions "${ACTIVE_TMP}"
    fi
    install_prepared "${destination}" "forge-project.md"
}

splice_agents() {
    local destination="${TARGET_ROOT}/AGENTS.md"

    new_temp_for "${destination}"
    if [ -f "${destination}" ]; then
        cp -p "${destination}" "${ACTIVE_TMP}"
    else
        : > "${ACTIVE_TMP}"
    fi

    perl -0777 -e '
        use strict;
        use warnings;

        my ($project_path, $agents_path) = @ARGV;
        my $begin = "<!-- FORGE:BEGIN -->";
        my $end = "<!-- FORGE:END -->";

        open my $project_fh, "<", $project_path
            or die "cannot read $project_path: $!\n";
        binmode $project_fh;
        my $project = <$project_fh>;
        close $project_fh or die "cannot close $project_path: $!\n";

        open my $agents_fh, "<", $agents_path
            or die "cannot read $agents_path: $!\n";
        binmode $agents_fh;
        my $agents = <$agents_fh>;
        $agents = "" unless defined $agents;
        close $agents_fh or die "cannot close $agents_path: $!\n";

        my $block = $begin . "\n" . $project;
        $block .= "\n" unless $block =~ /\n\z/;
        $block .= $end;

        my $begin_like_count = () = $agents =~ /<!-- FORGE:BEGIN\b/g;
        my $end_like_count = () = $agents =~ /<!-- FORGE:END\b/g;
        my $begin_count = () = $agents =~ /\Q$begin\E/g;
        my $end_count = () = $agents =~ /\Q$end\E/g;
        die "AGENTS.md has a malformed Forge splice marker\n"
            unless $begin_like_count == $begin_count
                && $end_like_count == $end_count;
        if ($begin_count == 0 && $end_count == 0) {
            $agents .= "\n" if length($agents) && $agents !~ /\n\z/;
            $agents .= $block . "\n";
        } elsif ($begin_count == 1 && $end_count == 1) {
            my $replacements = ($agents =~ s{\Q$begin\E.*?\Q$end\E}{$block}gs);
            die "AGENTS.md Forge splice markers are malformed\n"
                unless $replacements == 1;
        } else {
            die "AGENTS.md must contain zero or one Forge splice marker pair\n";
        }

        open my $output_fh, ">", $agents_path
            or die "cannot write $agents_path: $!\n";
        binmode $output_fh;
        print {$output_fh} $agents;
        close $output_fh or die "cannot close $agents_path: $!\n";
    ' "${TARGET_ROOT}/forge-project.md" "${ACTIVE_TMP}"

    install_prepared "${destination}" "AGENTS.md Forge splice"
}

ensure_claude_import() {
    local destination="${TARGET_ROOT}/CLAUDE.md"

    if [ -f "${destination}" ] && grep -qxF '@forge-project.md' "${destination}"; then
        record_skipped "CLAUDE.md import (already present)"
        return 0
    fi
    if [ -e "${destination}" ] && [ ! -f "${destination}" ]; then
        echo "forge install: destination is not a regular file: ${destination}" >&2
        exit 2
    fi

    new_temp_for "${destination}"
    if [ -f "${destination}" ]; then
        cp -p "${destination}" "${ACTIVE_TMP}"
    else
        : > "${ACTIVE_TMP}"
    fi
    if [ -s "${ACTIVE_TMP}" ] && [ -n "$(tail -c 1 "${ACTIVE_TMP}")" ]; then
        printf '\n' >> "${ACTIVE_TMP}"
    fi
    printf '@forge-project.md\n' >> "${ACTIVE_TMP}"
    install_prepared "${destination}" "CLAUDE.md import"
}

is_forge_managed_codex_file() {
    local path="$1"
    local relative="$2"

    case "${relative}" in
        config.toml)
            grep -qxF '# forge-managed' "${path}" 2>/dev/null
            ;;
        hooks.json)
            grep -qF ": 'forge-managed';" "${path}" 2>/dev/null
            ;;
        *)
            return 1
            ;;
    esac
}

is_upstream_codex_file() {
    local path="$1"
    local relative="$2"
    local normalized=""

    normalized="$(mktemp)"
    tr '\r' '\n' < "${path}" > "${normalized}" || {
        rm -f "${normalized}"
        return 1
    }

    case "${relative}" in
        config.toml)
            if grep -qxF '# forge-managed' "${normalized}" 2>/dev/null; then
                rm -f "${normalized}"
                return 1
            fi
            grep -qxF 'approval_policy = "on-failure"' "${normalized}" 2>/dev/null \
                && grep -qxF 'sandbox_mode = "workspace-write"' "${normalized}" 2>/dev/null \
                && grep -qxF '[agents."code-reviewer"]' "${normalized}" 2>/dev/null \
                && grep -qxF '[agents."review-final"]' "${normalized}" 2>/dev/null \
                && grep -qxF 'config_file = "./agents/review-final.toml"' "${normalized}" 2>/dev/null \
                && grep -qxF '[agents."security-auditor"]' "${normalized}" 2>/dev/null
            ;;
        hooks.json)
            grep -qF 'aggregate-telemetry.sh .tmp/decisions --csv .tmp/telemetry-latest.csv' "${normalized}" 2>/dev/null \
                && grep -qF '.tmp/decisions' "${normalized}" 2>/dev/null \
                && grep -qF '.tmp/telemetry-latest.csv' "${normalized}" 2>/dev/null
            ;;
        *)
            rm -f "${normalized}"
            return 1
            ;;
    esac
    local status=$?
    rm -f "${normalized}"
    return "${status}"
}

install_codex_layer() {
    local source relative destination label

    while IFS= read -r source; do
        relative="${source#"${CODEX_SOURCE}"/}"
        case "${relative}" in
            .devlog/*|*/.devlog/*|CLAUDE.md|*/CLAUDE.md) continue ;;
        esac

        destination="${TARGET_ROOT}/.codex/${relative}"
        label=".codex/${relative}"
        new_temp_for "${destination}"
        cp "${source}" "${ACTIVE_TMP}"
        render_tokens "${ACTIVE_TMP}"

        case "${relative}" in
            config.toml|hooks.json)
                if [ "${MANIFEST_SCHEMA}" = "upstream" ] \
                    && [ -f "${destination}" ] \
                    && is_upstream_codex_file "${destination}" "${relative}"; then
                    backup="${destination}.pre-migration"
                    if [ -f "${backup}" ] && ! cmp -s "${destination}" "${backup}"; then
                        echo "forge install: refusing to overwrite pre-migration backup: ${backup}" >&2
                        exit 2
                    fi
                    if [ ! -f "${backup}" ]; then
                        cp -p "${destination}" "${backup}"
                        record_taken ".codex/${relative}.pre-migration (created)"
                    else
                        record_skipped ".codex/${relative}.pre-migration (unchanged)"
                    fi
                fi
                if [ -f "${destination}" ] \
                    && ! cmp -s "${ACTIVE_TMP}" "${destination}" \
                    && ! is_forge_managed_codex_file "${destination}" "${relative}" \
                    && ! { [ "${MANIFEST_SCHEMA}" = "upstream" ] \
                        && is_upstream_codex_file "${destination}" "${relative}"; }; then
                    destination="${destination}.forge-new"
                    label="${label}.forge-new (preserved non-forge ${relative})"
                    if [ -f "${destination}" ] \
                        && ! cmp -s "${ACTIVE_TMP}" "${destination}" \
                        && ! is_forge_managed_codex_file "${destination}" "${relative}"; then
                        echo "forge install: refusing to overwrite non-forge collision sibling: ${destination}" >&2
                        exit 2
                    fi
                fi
                ;;
        esac

        install_prepared "${destination}" "${label}"
    done < <(LC_ALL=C find "${CODEX_SOURCE}" -type f -print | LC_ALL=C sort)
}

append_gitignore_block() {
    local destination="${TARGET_ROOT}/.gitignore"
    local canonicalized
    if [ -e "${destination}" ] && [ ! -f "${destination}" ]; then
        echo "forge install: destination is not a regular file: ${destination}" >&2
        exit 2
    fi

    new_temp_for "${destination}"
    if [ -f "${destination}" ]; then
        cp -p "${destination}" "${ACTIVE_TMP}"
    else
        : > "${ACTIVE_TMP}"
    fi
    canonicalized="$(mktemp "${destination}.forge-reconcile.XXXXXX")"
    awk '
        NR == FNR {
            required[$0] = 1
            next
        }
        {
            line = $0
            sub(/\r$/, "", line)
            sub(/[[:space:]]+$/, "", line)
            if (line in required) next
            print $0
        }
    ' "${GITIGNORE_SOURCE}" "${ACTIVE_TMP}" > "${canonicalized}"
    mv "${canonicalized}" "${ACTIVE_TMP}"
    if [ -s "${ACTIVE_TMP}" ] && [ -n "$(tail -c 1 "${ACTIVE_TMP}")" ]; then
        printf '\n' >> "${ACTIVE_TMP}"
    fi
    cat "${GITIGNORE_SOURCE}" >> "${ACTIVE_TMP}"
    install_prepared "${destination}" ".gitignore Forge block"
}

ensure_directory() {
    local path="$1"
    local label="$2"

    if [ -d "${path}" ]; then
        record_skipped "${label} (already present)"
        return 0
    fi
    if [ -e "${path}" ]; then
        echo "forge install: directory path is occupied: ${path}" >&2
        exit 2
    fi
    mkdir -p "${path}"
    record_taken "${label} (created)"
}

verify_history_ignore_invariant() {
    if git check-ignore -q -- ".forge/history/"; then
        echo "forge install: .forge/history/ must not be ignored" >&2
        exit 2
    fi

    if ! git check-ignore -q -- ".forge/tmp"; then
        echo "forge install: .forge/tmp/ must be ignored" >&2
        exit 2
    fi
}

printf 'forge install: target=%s plugin=%s\n' "${TARGET_ROOT}" "${PLUGIN_ROOT}"
install_forge_project
splice_agents
ensure_claude_import
install_codex_layer
append_gitignore_block
ensure_directory "${TARGET_ROOT}/.forge/evals/tasks" ".forge/evals/tasks/"
ensure_directory "${TARGET_ROOT}/.forge/history/runs" ".forge/history/runs/"
ensure_directory "${TARGET_ROOT}/.forge/history/drift" ".forge/history/drift/"
ensure_directory "${TARGET_ROOT}/.forge/history/migrations" ".forge/history/migrations/"
ensure_directory "${TARGET_ROOT}/.forge/tmp" ".forge/tmp/"
ensure_directory "${TARGET_ROOT}/.forge/tmp/authorized" ".forge/tmp/authorized/"
ensure_directory "${TARGET_ROOT}/.forge/tmp/drift" ".forge/tmp/drift/"
ensure_directory "${TARGET_ROOT}/.forge/tmp/decisions" ".forge/tmp/decisions/"
verify_history_ignore_invariant

printf 'forge install: summary: %d taken, %d skipped\n' \
    "${TAKEN_COUNT}" "${SKIPPED_COUNT}"
