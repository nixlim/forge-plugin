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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

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

TRUSTED_TMP_ROOT="$(cd /tmp && pwd -P)"
if [ "${TARGET_ROOT}" = "/" ] || [ "${TRUSTED_TMP_ROOT}" = "${TARGET_ROOT}" ]; then
    echo "forge install: cannot stage preflight outside the target repository" >&2
    exit 2
fi
case "${TRUSTED_TMP_ROOT}" in
    "${TARGET_ROOT}"/*)
        echo "forge install: cannot stage preflight outside the target repository" >&2
        exit 2
        ;;
esac

PROJECT_TEMPLATE="${PLUGIN_ROOT}/system/template/forge-project.md"
CODEX_SOURCE="${PLUGIN_ROOT}/system/codex"
GITIGNORE_SOURCE="${PLUGIN_ROOT}/system/template/gitignore-block.txt"
MIGRATION_HELPER="${PLUGIN_ROOT}/scripts/forge/migrate-upstream.py"
CODEX_MERGE_HELPER="${SCRIPT_DIR}/codex_layer_merge.py"

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
if [ ! -f "${CODEX_MERGE_HELPER}" ]; then
    echo "forge install: missing Codex merge helper: ${CODEX_MERGE_HELPER}" >&2
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
PENDING_TMP=""
CODEX_STAGE=""
CODEX_CONFIG_ACTION=""
CODEX_HOOKS_ACTION=""
CODEX_REPLACEMENTS="none"

cleanup() {
    if [ -n "${ACTIVE_TMP}" ] && [ -e "${ACTIVE_TMP}" ]; then
        rm -f "${ACTIVE_TMP}"
    fi
    if [ -n "${PENDING_TMP}" ] && [ -e "${PENDING_TMP}" ]; then
        rm -f "${PENDING_TMP}"
    fi
    if [ -n "${CODEX_STAGE}" ] && [ -d "${CODEX_STAGE}" ]; then
        rm -rf -- "${CODEX_STAGE}"
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

# Codex-layer destinations are preflighted as nonsymlink regular files. Keep
# that shape invariant at publication while preserving base installer behavior
# for the repository-root harness files.
install_codex_prepared() {
    local destination="$1"
    local label="$2"

    if [ -L "${destination}" ] \
        || { [ -e "${destination}" ] && [ ! -f "${destination}" ]; }; then
        echo "forge install: destination is not a regular file: ${destination}" >&2
        exit 2
    fi
    install_prepared "${destination}" "${label}"
}

# Publish an idempotent file without ever replacing an existing directory entry.
install_no_clobber_prepared() {
    local destination="$1"
    local label="$2"
    local collision="$3"

    if [ -L "${destination}" ] \
        || { [ -e "${destination}" ] && [ ! -f "${destination}" ]; }; then
        echo "forge install: destination is not a regular file: ${destination}" >&2
        exit 2
    fi
    if [ -f "${destination}" ]; then
        if cmp -s "${ACTIVE_TMP}" "${destination}"; then
            rm -f "${ACTIVE_TMP}"
            ACTIVE_TMP=""
            record_skipped "${label} (unchanged)"
            return
        fi
        echo "${collision}" >&2
        exit 2
    fi

    chmod 0644 "${ACTIVE_TMP}"
    if ln "${ACTIVE_TMP}" "${destination}" 2>/dev/null; then
        rm -f "${ACTIVE_TMP}"
        ACTIVE_TMP=""
        record_taken "${label} (created)"
        return
    fi
    if [ ! -L "${destination}" ] \
        && [ -f "${destination}" ] \
        && cmp -s "${ACTIVE_TMP}" "${destination}"; then
        rm -f "${ACTIVE_TMP}"
        ACTIVE_TMP=""
        record_skipped "${label} (unchanged)"
        return
    fi
    echo "${collision}" >&2
    exit 2
}

# Validate the fresh region scaffold, carry forward the project-spine block and
# filled region bodies, and report a legacy outside-region collision.
validate_and_merge_regions() {
    local fresh="$1"
    local previous="${2:-}"

    perl -0777 -e '
        use strict;
        use warnings;

        my ($fresh_path, $previous_path) = @ARGV;

        sub valid_install_date {
            my ($value) = @_;
            return 0
                unless $value =~ /\A([0-9]{4})-([0-9]{2})-([0-9]{2})\z/;
            my ($year, $month, $day) = (int($1), int($2), int($3));
            return 0
                if $year < 1 || $month < 1 || $month > 12 || $day < 1;
            my @days = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31);
            $days[2] = 29
                if $year % 400 == 0
                    || ($year % 4 == 0 && $year % 100 != 0);
            return $day <= $days[$month];
        }

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

        sub project_spine_block {
            my ($document, $required) = @_;
            my $diagnostic =
                "forge: project spine addenda block malformed — repair forge-project.md\n";
            my $marker_like_count = () =
                $document =~ /<!-- FORGE:PROJECT-SPINE\b/g;
            my @markers;
            while ($document =~ /<!-- FORGE:PROJECT-SPINE (BEGIN|END) -->/g) {
                push @markers, {
                    kind  => $1,
                    start => $-[0],
                    end   => $+[0],
                };
            }
            if ($marker_like_count == 0 && @markers == 0) {
                die $diagnostic
                    if $required
                        || $document =~ /^### Project Spine Addenda\r?$/m;
                return;
            }
            die $diagnostic
                unless $marker_like_count == 2
                    && @markers == 2
                    && $markers[0]->{kind} eq "BEGIN"
                    && $markers[1]->{kind} eq "END"
                    && $markers[1]->{start} > $markers[0]->{end};
            my $inner = substr(
                $document,
                $markers[0]->{end},
                $markers[1]->{start} - $markers[0]->{end},
            );
            die $diagnostic if $inner =~ /<!-- FORGE:REGION\b/;
            my $prefix = substr($document, 0, $markers[0]->{start});
            my $region_begins = () =
                $prefix =~ /<!-- FORGE:REGION \S+ BEGIN -->/g;
            my $region_ends = () =
                $prefix =~ /<!-- FORGE:REGION \S+ END -->/g;
            die $diagnostic unless $region_begins == $region_ends;
            my $after_end = $markers[1]->{end};
            my $before_block = substr($document, 0, $markers[0]->{start});
            my $section_heading = -1;
            while ($before_block =~ /^### Project Spine Addenda\r?$/mg) {
                $section_heading = $-[0];
            }
            my $after_block = substr($document, $after_end);
            die $diagnostic
                unless $section_heading >= 0
                    && $after_block =~ /\A\s*^## Plugin Skills\r?$/m;
            return (
                substr(
                    $document,
                    $markers[0]->{start},
                    $after_end - $markers[0]->{start},
                ),
                $markers[0]->{start},
                $after_end,
            );
        }

        sub without_project_spine_section {
            my ($document, $block_start, $after_block) = @_;
            my $before = substr($document, 0, $block_start);
            my $section_start = -1;
            while ($before =~ /^### Project Spine Addenda\r?$/mg) {
                $section_start = $-[0];
            }
            my $after = substr($document, $after_block);
            my $section_end = $after =~ /\A(\r?\n\r?\n)/
                ? $after_block + length($1)
                : -1;
            die "forge: project spine addenda block malformed — repair forge-project.md\n"
                unless $section_start >= 0 && $section_end > $after_block;
            my $copy = $document;
            substr($copy, $section_start, $section_end - $section_start, "");
            return $copy;
        }

        sub region_skeleton {
            my ($document) = @_;
            $document =~ s{(<!-- FORGE:REGION (\S+) BEGIN -->).*?(<!-- FORGE:REGION \2 END -->)}{$1 . $3}gse;
            return $document;
        }

        open my $fresh_fh, "<", $fresh_path
            or die "cannot read $fresh_path: $!\n";
        binmode $fresh_fh;
        my $fresh = <$fresh_fh>;
        close $fresh_fh or die "cannot close $fresh_path: $!\n";

        my @fresh_project_spine = project_spine_block($fresh, 1);

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
            reviewer-facing-eval-triggers
            guard-denied-commands
        );
        my @guard_predecessor_required = @required[0 .. 14];
        my @predecessor_required = @required[0 .. 13];
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
        my $legacy_divergence = 0;

        if (length $previous_path) {
            open my $previous_fh, "<", $previous_path
                or die "cannot read $previous_path: $!\n";
            binmode $previous_fh;
            my $previous = <$previous_fh>;
            $previous = "" unless defined $previous;
            close $previous_fh or die "cannot close $previous_path: $!\n";

            my ($previous_date) = $previous =~
                /\A[^\r\n]+\r?\n\r?\nInstall date: `([^`\r\n]+)`(?:\r?\n|\z)/;
            if (defined $previous_date && valid_install_date($previous_date)) {
                $fresh =~ s{
                    ^Install\ date:\ `[^`\r\n]+`
                }{"Install date: `" . $previous_date . "`"}mxe;
                @fresh_project_spine = project_spine_block($fresh, 1);
            }

            my @previous_project_spine = project_spine_block($previous, 0);

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
            my $guard_predecessor_inventory = join(
                "\0",
                @guard_predecessor_required,
            );
            my $predecessor_inventory = join("\0", @predecessor_required);
            my $legacy_inventory = join("\0", @legacy_required);
            die "existing forge-project.md has missing or reordered regions\n"
                unless $previous_inventory eq $current_inventory
                    || $previous_inventory eq $guard_predecessor_inventory
                    || $previous_inventory eq $predecessor_inventory
                    || $previous_inventory eq $legacy_inventory;

            if (!@previous_project_spine) {
                my $legacy_fresh = without_project_spine_section(
                    $fresh,
                    $fresh_project_spine[1],
                    $fresh_project_spine[2],
                );
                $legacy_divergence =
                    region_skeleton($previous) ne region_skeleton($legacy_fresh);
            }
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

            # This table is plugin-owned fixed policy.  A noncanonical filled
            # body is refreshed from the template instead of being carried
            # forward, including a well-formed narrowed row.
            if (
                exists $filled{"reviewer-facing-eval-triggers"}
                && $filled{"reviewer-facing-eval-triggers"}
                    ne $fresh_regions->{"reviewer-facing-eval-triggers"}
            ) {
                delete $filled{"reviewer-facing-eval-triggers"};
            }

            if (@previous_project_spine) {
                substr(
                    $fresh,
                    $fresh_project_spine[1],
                    $fresh_project_spine[2] - $fresh_project_spine[1],
                    $previous_project_spine[0],
                );
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
        print "legacy-divergence\n" if $legacy_divergence;
    ' "${fresh}" "${previous}"
}

preflight_legacy_project() {
    local source="$1"
    local destination="${source}.forge-prev"

    if [ -L "${destination}" ] \
        || { [ -e "${destination}" ] && [ ! -f "${destination}" ]; }; then
        echo "forge install: destination is not a regular file: ${destination}" >&2
        exit 2
    fi
    if [ -f "${destination}" ] && ! cmp -s "${source}" "${destination}"; then
        echo "forge install: refusing to overwrite project collision sibling: ${destination}" >&2
        exit 2
    fi
}

preserve_legacy_project() {
    local source="$1"
    local destination="${source}.forge-prev"

    new_temp_for "${destination}"
    cp -p "${source}" "${ACTIVE_TMP}"
    install_no_clobber_prepared \
        "${destination}" \
        "forge-project.md.forge-prev (blocking collision; preserved legacy project text)" \
        "forge install: refusing to overwrite project collision sibling: ${destination}"
}

install_forge_project() {
    local destination="${TARGET_ROOT}/forge-project.md"
    local merge_status=""
    local staged_project=""

    if [ -L "${destination}" ] \
        || { [ -e "${destination}" ] && [ ! -f "${destination}" ]; }; then
        echo "forge install: destination is not a regular file: ${destination}" >&2
        exit 2
    fi

    ACTIVE_TMP="$(mktemp "${TRUSTED_TMP_ROOT}/forge-project.XXXXXX")"
    cp "${PROJECT_TEMPLATE}" "${ACTIVE_TMP}"
    render_tokens "${ACTIVE_TMP}"
    if [ -f "${destination}" ]; then
        merge_status="$(validate_and_merge_regions "${ACTIVE_TMP}" "${destination}")"
    else
        validate_and_merge_regions "${ACTIVE_TMP}"
    fi
    if [ "${merge_status}" = "legacy-divergence" ]; then
        preflight_legacy_project "${destination}"
    fi

    staged_project="${ACTIVE_TMP}"
    PENDING_TMP="${staged_project}"
    ACTIVE_TMP=""
    if [ "${merge_status}" = "legacy-divergence" ]; then
        preserve_legacy_project "${destination}"
    fi
    new_temp_for "${destination}"
    cp "${staged_project}" "${ACTIVE_TMP}"
    rm -f "${staged_project}"
    PENDING_TMP=""
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

is_upstream_codex_file() {
    local path="$1"
    local relative="$2"
    local normalized=""

    normalized="$(mktemp "${TRUSTED_TMP_ROOT}/forge-codex-normalized.XXXXXX")"
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

prepare_codex_layer() {
    local relative destination backup replacements=""

    CODEX_STAGE="$(mktemp -d "${TRUSTED_TMP_ROOT}/forge-codex.XXXXXX")"
    python3 -I "${CODEX_MERGE_HELPER}" stage \
        "${CODEX_SOURCE}" \
        "${CODEX_STAGE}/templates" \
        "${PROJECT_NAME}" \
        "${INSTALL_DATE}" \
        "${CODEX_STAGE}/template-paths"
    mkdir -p "${CODEX_STAGE}/signatures"
    python3 -I "${CODEX_MERGE_HELPER}" snapshot \
        "${TARGET_ROOT}/.codex" \
        "${CODEX_STAGE}/observed"
    for relative in config.toml hooks.json; do
        destination="${TARGET_ROOT}/.codex/${relative}"
        if [ "${MANIFEST_SCHEMA}" = "upstream" ] \
            && [ -f "${CODEX_STAGE}/observed/${relative}" ] \
            && is_upstream_codex_file \
                "${CODEX_STAGE}/observed/${relative}" "${relative}"; then
            replacements="${replacements}${replacements:+,}${relative}"
            cp \
                "${CODEX_STAGE}/observed/${relative}" \
                "${CODEX_STAGE}/signatures/${relative}"
            backup="${destination}.pre-migration"
            if [ -L "${backup}" ] \
                || { [ -e "${backup}" ] && [ ! -f "${backup}" ]; }; then
                echo "forge install: destination is not a regular file: ${backup}" >&2
                exit 2
            fi
            if [ -f "${backup}" ] \
                && ! cmp -s "${CODEX_STAGE}/signatures/${relative}" "${backup}"; then
                echo "forge install: refusing to overwrite pre-migration backup: ${backup}" >&2
                exit 2
            fi
        fi
    done
    replacements="${replacements:-none}"
    CODEX_REPLACEMENTS="${replacements}"

    python3 -I "${CODEX_MERGE_HELPER}" prepare \
        "${CODEX_STAGE}/templates" \
        "${TARGET_ROOT}/.codex" \
        "${CODEX_STAGE}/prepared" \
        "${replacements}"
    for relative in config.toml hooks.json; do
        if [ -f "${CODEX_STAGE}/signatures/${relative}" ] \
            && ! cmp -s \
                "${CODEX_STAGE}/signatures/${relative}" \
                "${CODEX_STAGE}/prepared/preconditions/${relative}"; then
            echo "forge install: Codex input changed after signature classification: ${relative}" >&2
            exit 2
        fi
    done
    CODEX_CONFIG_ACTION="$(sed -n 's/^config\.toml=//p' "${CODEX_STAGE}/prepared/plan")"
    CODEX_HOOKS_ACTION="$(sed -n 's/^hooks\.json=//p' "${CODEX_STAGE}/prepared/plan")"
    case "${CODEX_CONFIG_ACTION}:${CODEX_HOOKS_ACTION}" in
        install:install|install:collision|collision:install|collision:collision) ;;
        *)
            echo "forge install: invalid Codex merge plan" >&2
            exit 2
            ;;
    esac
}

verify_codex_preconditions() {
    local relative="${1:-}"

    if [ -n "${relative}" ]; then
        python3 -I "${CODEX_MERGE_HELPER}" verify \
            "${CODEX_STAGE}/prepared/preconditions" \
            "${TARGET_ROOT}/.codex" \
            "${relative}"
        return
    fi
    python3 -I "${CODEX_MERGE_HELPER}" verify \
        "${CODEX_STAGE}/prepared/preconditions" \
        "${TARGET_ROOT}/.codex"
}

install_codex_layer() {
    local source relative destination label action backup prepared_source

    verify_codex_preconditions

    while IFS= read -r -d '' source; do
        relative="${source#"${CODEX_STAGE}/templates"/}"
        case "${relative}" in
            .devlog/*|*/.devlog/*|CLAUDE.md|*/CLAUDE.md) continue ;;
        esac

        destination="${TARGET_ROOT}/.codex/${relative}"
        label=".codex/${relative}"
        action="install"
        prepared_source="${source}"
        case "${relative}" in
            config.toml)
                prepared_source="${CODEX_STAGE}/prepared/${relative}"
                action="${CODEX_CONFIG_ACTION}"
                ;;
            hooks.json)
                prepared_source="${CODEX_STAGE}/prepared/${relative}"
                action="${CODEX_HOOKS_ACTION}"
                ;;
        esac

        case "${relative}" in
            config.toml|hooks.json)
                verify_codex_preconditions "${relative}"
                case ",${CODEX_REPLACEMENTS}," in
                    *,"${relative}",*)
                    backup="${destination}.pre-migration"
                    if [ -f "${backup}" ] && ! cmp -s "${destination}" "${backup}"; then
                        echo "forge install: refusing to overwrite pre-migration backup: ${backup}" >&2
                        exit 2
                    fi
                    if [ ! -f "${backup}" ]; then
                        new_temp_for "${backup}"
                        cp "${CODEX_STAGE}/signatures/${relative}" "${ACTIVE_TMP}"
                        install_no_clobber_prepared \
                            "${backup}" \
                            ".codex/${relative}.pre-migration" \
                            "forge install: refusing to overwrite pre-migration backup: ${backup}"
                    else
                        record_skipped ".codex/${relative}.pre-migration (unchanged)"
                    fi
                    ;;
                esac
                verify_codex_preconditions "${relative}"
                case ",${CODEX_REPLACEMENTS}," in
                    *,"${relative}",*)
                        backup="${destination}.pre-migration"
                        if [ -L "${backup}" ] \
                            || [ ! -f "${backup}" ] \
                            || ! cmp -s \
                                "${CODEX_STAGE}/signatures/${relative}" \
                                "${backup}"; then
                            echo "forge install: refusing to overwrite pre-migration backup: ${backup}" >&2
                            exit 2
                        fi
                        ;;
                esac
                if [ "${action}" = "collision" ]; then
                    destination="${destination}.forge-new"
                    label="${label}.forge-new (preserved existing ${relative})"
                fi
                ;;
        esac

        new_temp_for "${destination}"
        cp "${prepared_source}" "${ACTIVE_TMP}"
        if [ "${action}" = "collision" ]; then
            install_no_clobber_prepared \
                "${destination}" \
                "${label}" \
                "forge install: refusing to overwrite non-forge collision sibling: ${destination}"
        else
            install_codex_prepared "${destination}" "${label}"
        fi
    done < "${CODEX_STAGE}/template-paths"
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

is_planned_dangling_claude_target() {
    local link_path="$1"

    python3 - \
        "${link_path}" \
        "${TARGET_ROOT}/forge-project.md" \
        "${TARGET_ROOT}/AGENTS.md" <<'PY'
import os
import stat
import sys

link_path = sys.argv[1]
planned = set(sys.argv[2:])
seen = set()

for _hop in range(40):
    if link_path in seen:
        raise SystemExit(1)
    seen.add(link_path)
    try:
        target = os.readlink(link_path)
    except OSError:
        raise SystemExit(1)
    if target.endswith(os.sep):
        raise SystemExit(1)
    if not os.path.isabs(target):
        target = os.path.join(os.path.dirname(link_path), target)
    parent, leaf = os.path.split(target)
    if not leaf:
        raise SystemExit(1)
    try:
        parent = os.path.realpath(parent, strict=True)
    except OSError:
        raise SystemExit(1)
    link_path = os.path.join(parent, leaf)
    try:
        mode = os.lstat(link_path).st_mode
    except FileNotFoundError:
        raise SystemExit(0 if link_path in planned else 1)
    except OSError:
        raise SystemExit(1)
    if not stat.S_ISLNK(mode):
        raise SystemExit(1)

raise SystemExit(1)
PY
}

preflight_harness_destinations() {
    local destination

    for destination in \
        "${TARGET_ROOT}/AGENTS.md" \
        "${TARGET_ROOT}/CLAUDE.md" \
        "${TARGET_ROOT}/.gitignore"; do
        if [ "${destination}" = "${TARGET_ROOT}/CLAUDE.md" ] \
            && [ -L "${destination}" ] \
            && [ ! -e "${destination}" ] \
            && is_planned_dangling_claude_target "${destination}"; then
            continue
        fi
        if { [ -e "${destination}" ] || [ -L "${destination}" ]; } \
            && [ ! -f "${destination}" ]; then
            echo "forge install: destination is not a regular file: ${destination}" >&2
            exit 2
        fi
    done
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
    local history_path
    for history_path in \
        ".forge/history/" \
        ".forge/history/runs/.forge-ignore-check.md" \
        ".forge/history/drift/.forge-ignore-check.md" \
        ".forge/history/migrations/.forge-ignore-check.md" \
        ".forge/history/gotchas.md"; do
        if git check-ignore -q --no-index -- "${history_path}"; then
            echo "forge install: .forge/history/ must not be ignored" >&2
            exit 2
        fi
    done

    local candidate_path
    for candidate_path in \
        ".forge/evals/candidates/.forge-ignore-check" \
        ".forge/evals/candidates/.forge-ignore-check.json" \
        ".forge/evals/candidates/.forge-ignore-check.result" \
        ".forge/evals/candidates/.forge-ignore-check.md"; do
        if git check-ignore -q --no-index -- "${candidate_path}"; then
            echo "forge install: .forge/evals/candidates/ must not be ignored" >&2
            exit 2
        fi
    done

    if ! git check-ignore -q --no-index -- ".forge/tmp"; then
        echo "forge install: .forge/tmp/ must be ignored" >&2
        exit 2
    fi

    if ! git check-ignore -q --no-index -- ".forge/chains/.forge-ignore-check"; then
        echo "forge install: .forge/chains/ must be ignored" >&2
        exit 2
    fi
}

preflight_harness_destinations
prepare_codex_layer
verify_codex_preconditions
printf 'forge install: target=%s plugin=%s\n' "${TARGET_ROOT}" "${PLUGIN_ROOT}"
install_forge_project
splice_agents
ensure_claude_import
install_codex_layer
append_gitignore_block
ensure_directory "${TARGET_ROOT}/.forge/evals/tasks" ".forge/evals/tasks/"
ensure_directory "${TARGET_ROOT}/.forge/history/drift" ".forge/history/drift/"
ensure_directory "${TARGET_ROOT}/.forge/history/migrations" ".forge/history/migrations/"
ensure_directory "${TARGET_ROOT}/.forge/tmp" ".forge/tmp/"
ensure_directory "${TARGET_ROOT}/.forge/tmp/authorized" ".forge/tmp/authorized/"
ensure_directory "${TARGET_ROOT}/.forge/tmp/drift" ".forge/tmp/drift/"
ensure_directory "${TARGET_ROOT}/.forge/tmp/decisions" ".forge/tmp/decisions/"
verify_history_ignore_invariant

printf 'forge install: summary: %d taken, %d skipped\n' \
    "${TAKEN_COUNT}" "${SKIPPED_COUNT}"
