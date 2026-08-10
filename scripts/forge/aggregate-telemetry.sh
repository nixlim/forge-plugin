#!/usr/bin/env bash
# Aggregate activity-time, cost, and parallelism telemetry from decision logs.
#
# Usage:
#   aggregate-telemetry.sh [DECISIONS_DIR] [--csv OUT.csv]
# Defaults: DECISIONS_DIR=.forge/tmp/decisions
# Exits 0 when no telemetry is found. In a non-Forge working directory it exits
# 0 without producing output.
# forge: modified from upstream — state is re-rooted to .forge/tmp and non-Forge repos are silent
set -euo pipefail

# The Stop hook is global to the plugin. It must be invisible in repositories
# where Forge has not been initialized.
[[ -f .forge-manifest ]] || exit 0

DECISIONS_DIR=".forge/tmp/decisions"
CSV=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --csv)
            CSV="${2:-}"
            shift
            [[ $# -gt 0 ]] && shift
            ;;
        --help|-h)
            sed -n '2,8p' "$0"
            exit 0
            ;;
        *)
            DECISIONS_DIR="$1"
            shift
            ;;
    esac
done

if [[ ! -d "$DECISIONS_DIR" ]]; then
    echo "No decisions directory at '$DECISIONS_DIR' — nothing to aggregate."
    exit 0
fi

shopt -s nullglob
files=("$DECISIONS_DIR"/*.md)
if [[ ${#files[@]} -eq 0 ]]; then
    echo "No decision-log files in '$DECISIONS_DIR' — nothing to aggregate."
    exit 0
fi

# Extract fenced telemetry blocks, prefixing each with a file separator, then
# aggregate. Unknown keys are intentionally ignored.
extract() {
    local file
    for file in "${files[@]}"; do
        awk -v file="$file" '
            /^```telemetry[[:space:]]*$/ { print "@@FILE " file; inblock=1; next }
            inblock && /^```[[:space:]]*$/ { inblock=0; next }
            inblock { print }
        ' "$file"
    done
}

extract | awk -v csv="$CSV" '
    function flush_unit(   f, i, n, parts, cat) {
        if (!have_unit) return
        units++
        f = (feature=="" ? "(unattributed)" : feature)
        feat_units[f]++
        feat_elapsed[f]+=elapsed
        feat_cp[f]+=cp
        feat_tokens[f]+=tokens
        feat_cost[f]+=cost
        rec[units]=sprintf("%s\t%s\t%s\t%d\t%d\t%d\t%.2f\t%d\t%d", \
            (unit==""?"?":unit), f, (model==""?"?":model), elapsed, cp, tokens, cost, riters, rework)
        if (riters>0) { riter_sum+=riters; riter_n++ }
        tot_elapsed+=elapsed
        tot_cp+=cp
        tot_tokens+=tokens
        tot_cost+=cost
        tot_rework+=rework
        if (ocp != "") {
            n=split(ocp, parts, /[ ,]+/)
            for (i=1;i<=n;i++) {
                cat=parts[i]
                gsub(/^[[:space:]]+|[[:space:]]+$/,"",cat)
                if (cat!="" && (cat in ustage)) {
                    cp_stage_tot[cat]+=ustage[cat]
                    cp_stage_grand+=ustage[cat]
                }
            }
        }
    }
    function reset_unit( reset_key) {
        have_unit=0
        unit=""
        feature=""
        model=""
        elapsed=0
        cp=0
        tokens=0
        cost=0
        riters=0
        rework=0
        ocp=""
        for (reset_key in ustage) delete ustage[reset_key]
    }
    BEGIN { reset_unit() }
    /^@@FILE / { flush_unit(); reset_unit(); have_unit=1; next }
    {
        line=$0
        sub(/[[:space:]]*#.*$/, "", line)
        if (line ~ /^[[:space:]]*$/) next
        key=line
        sub(/:.*$/, "", key)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
        val=line
        sub(/^[^:]*:/, "", val)
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", val)
        if (key=="unit") unit=val
        else if (key=="feature") feature=val
        else if (key=="model") model=val
        else if (key=="tokens") tokens=val+0
        else if (key=="cost_usd") cost=val+0
        else if (key=="elapsed_s") elapsed=val+0
        else if (key=="critical_path_s") cp=val+0
        else if (key=="review_iterations") riters=val+0
        else if (key=="rework_s") rework=val+0
        else if (key=="on_critical_path") ocp=val
        else if (key ~ /^stage\./) {
            c=key
            sub(/^stage\./,"",c)
            sub(/_s$/,"",c)
            stage_tot[c]+=val+0
            stage_grand+=val+0
            ustage[c]=val+0
        }
        else if (key ~ /^serialisation\./) {
            c=key
            sub(/^serialisation\./,"",c)
            sub(/_s$/,"",c)
            serial_tot[c]+=val+0
            serial_grand+=val+0
        }
    }
    END {
        flush_unit()
        if (units==0) {
            print "No telemetry blocks found in decision logs — nothing to aggregate."
            exit 0
        }

        printf "AI-SDLC delivery telemetry — %d unit(s)\n", units
        print  "============================================================"

        print  "\nPer-unit (seconds, tokens, $cost):"
        printf "  %-24s %-14s %-8s %8s %8s %9s %7s %5s %6s\n", "UNIT","FEATURE","MODEL","ELAPSED","CRITPATH","TOKENS","COST","ITER","REWORK"
        for (i=1;i<=units;i++) {
            split(rec[i],r,"\t")
            printf "  %-24s %-14s %-8s %8d %8d %9d %7.2f %5d %6d\n", r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],r[9]
        }

        print  "\nActivity-time by category (COST lens — largest total time first):"
        n=0
        for (c in stage_tot) arr[++n]=c
        for (a=1;a<=n;a++) for (b=a+1;b<=n;b++) if (stage_tot[arr[b]]>stage_tot[arr[a]]) { t=arr[a];arr[a]=arr[b];arr[b]=t }
        for (a=1;a<=n;a++) {
            c=arr[a]
            printf "  %-22s %8d s  %5.1f%%\n", c, stage_tot[c], (stage_grand>0?100*stage_tot[c]/stage_grand:0)
        }
        if (n==0) print "  (none recorded)"

        print  "\nSerialisation causes (why parallelism was lost — largest first):"
        m=0
        for (c in serial_tot) sar[++m]=c
        for (a=1;a<=m;a++) for (b=a+1;b<=m;b++) if (serial_tot[sar[b]]>serial_tot[sar[a]]) { t=sar[a];sar[a]=sar[b];sar[b]=t }
        for (a=1;a<=m;a++) {
            c=sar[a]
            printf "  %-22s %8d s  %5.1f%%\n", c, serial_tot[c], (serial_grand>0?100*serial_tot[c]/serial_grand:0)
        }
        if (m==0) print "  (none recorded — no forced serialisation, or unmeasured)"

        print  "\nCritical-path stage breakdown (DURATION lens — optimise these to ship faster):"
        cn=0
        for (c in cp_stage_tot) carr[++cn]=c
        for (a=1;a<=cn;a++) for (b=a+1;b<=cn;b++) if (cp_stage_tot[carr[b]]>cp_stage_tot[carr[a]]) { t=carr[a];carr[a]=carr[b];carr[b]=t }
        for (a=1;a<=cn;a++) {
            c=carr[a]
            printf "  %-22s %8d s  %5.1f%%\n", c, cp_stage_tot[c], (cp_stage_grand>0?100*cp_stage_tot[c]/cp_stage_grand:0)
        }
        if (cn==0) print "  (no on_critical_path data recorded)"

        print  "\nPer-feature roll-up (cost & duration per delivered feature/fix):"
        printf "  %-18s %6s %10s %10s %9s %8s\n", "FEATURE","UNITS","ELAPSED","CRITPATH","TOKENS","COST"
        for (f in feat_units) {
            printf "  %-18s %6d %10d %10d %9d %8.2f\n", f, feat_units[f], feat_elapsed[f], feat_cp[f], feat_tokens[f], feat_cost[f]
        }

        printf "\nTotals: elapsed=%ds  critical-path=%ds  tokens=%d  cost=$%.2f  rework=%ds", tot_elapsed, tot_cp, tot_tokens, tot_cost, tot_rework
        if (riter_n>0) printf "  mean-review-iters=%.1f", riter_sum/riter_n
        print ""
        printf "Duration analysis: total work (serial baseline)=%ds  on-critical-path stage time=%ds  measured duration tax (forced serialisation)=%ds\n", tot_elapsed, cp_stage_grand, serial_grand
        print  "  (theoretical-best across units needs the cross-unit dependency DAG, not in the per-unit schema)"

        if (csv!="") {
            print "unit,feature,model,elapsed_s,critical_path_s,tokens,cost_usd,review_iterations,rework_s" > csv
            for (i=1;i<=units;i++) {
                split(rec[i],r,"\t")
                printf "%s,%s,%s,%d,%d,%d,%.2f,%d,%d\n", r[1],r[2],r[3],r[4],r[5],r[6],r[7],r[8],r[9] >> csv
            }
        }
    }
'

[[ -n "$CSV" ]] && echo "Per-unit CSV written to $CSV"
exit 0
