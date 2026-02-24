#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# USAGE
# ------------------------------------------------------------
# ./generate_proposal_from_blocks.sh block_a.json block_b.json output_dir [--english Y]
#
# Example:
# ./generate_proposal_from_blocks.sh \
#   block_a.json block_b.json ./out --english Y
# ------------------------------------------------------------

BLOCK_A="$1"
BLOCK_B="$2"
OUT_DIR="$3"

ENGLISH="N"

if [[ $# -ge 5 ]]; then
  if [[ "$4" == "--english" && "$5" == "Y" ]]; then
    ENGLISH="Y"
  fi
fi

if [[ ! -f "$BLOCK_A" ]]; then
  echo "❌ Block A file not found"
  exit 1
fi

if [[ ! -f "$BLOCK_B" ]]; then
  echo "❌ Block B file not found"
  exit 1
fi

mkdir -p "$OUT_DIR"

PROPOSAL_JSON="$OUT_DIR/proposal.json"
PROPOSAL_TXT="$OUT_DIR/proposal.txt"

echo "📦 Generating consolidated proposal..."

# ------------------------------------------------------------
# JSON PROPOSAL
# ------------------------------------------------------------
jq -n \
  --slurpfile A "$BLOCK_A" \
  --slurpfile B "$BLOCK_B" \
  '
  $A[0] as $A
  | $B[0] as $B
  | 
  {
    startup_idea_id: $A.startup_idea_id,

    proposal_summary: {
      tier_1: {
        bdr_summary: $A.pass_1.bdr_summary,
        approved_scope: $A.pass_2.approved_bdr,
        milestone_map: $A.pass_5.final_milestone_map
      },
      tier_2: {
        bdr_summary: $B.pass_1.bdr_summary,
        approved_scope: $B.pass_2.approved_bdr,
        milestone_map: $B.pass_5.final_milestone_map
      }
    },

    economics: {
      tier_1: $A.pass_1.economics_snapshot,
      tier_2: $B.pass_1.economics_snapshot
    },

    final_decision: {
      tier_1: $A.pass_6.hero_decision,
      tier_2: $B.pass_6.hero_decision
    }
  }
  ' > "$PROPOSAL_JSON"

echo "✅ JSON proposal created:"
echo "$PROPOSAL_JSON"

# ------------------------------------------------------------
# ENGLISH PROPOSAL (OPTIONAL)
# ------------------------------------------------------------
if [[ "$ENGLISH" == "Y" ]]; then
  echo "📝 Generating English proposal..."

  jq -rn \
    --slurpfile A "$BLOCK_A" \
    --slurpfile B "$BLOCK_B" \
    '
    $A[0] as $A
    | $B[0] as $B
    |
    "==================================================",
    "FOUNDEROPS PROPOSAL",
    "==================================================",
    "",
    "Startup: " + $A.startup_idea_id,
    "",
    "------------------------------",
    "TIER 1 — PROOF SLICE",
    "------------------------------",
    "",
    "Summary:",
    $A.pass_1.bdr_summary,
    "",
    "Approved Scope:",
    $A.pass_2.approved_bdr,
    "",
    "Milestones:",
    ($A.pass_5.final_milestone_map[] |
      "- " + .milestone + " (Day " + (.day|tostring) + ")"
    ),
    "",
    "------------------------------",
    "TIER 2 — MVP BUILD",
    "------------------------------",
    "",
    "Summary:",
    $B.pass_1.bdr_summary,
    "",
    "Approved Scope:",
    $B.pass_2.approved_bdr,
    "",
    "Milestones:",
    ($B.pass_5.final_milestone_map[] |
      "- " + .milestone + " (Day " + (.day|tostring) + ")"
    ),
    "",
    "------------------------------",
    "ECONOMICS",
    "------------------------------",
    "",
    "Tier 1 Target:",
    ($A.pass_1.economics_snapshot.revenue_goal_12mo // "Not specified"),
    "",
    "Tier 2 Target:",
    ($B.pass_1.economics_snapshot.revenue_goal_12mo // "Not specified"),
    "",
    "------------------------------",
    "FINAL DECISION",
    "------------------------------",
    "",
    "Tier 1 Decision: " + $A.pass_6.hero_decision,
    "Tier 2 Decision: " + $B.pass_6.hero_decision,
    "",
    "=================================================="
    ' > "$PROPOSAL_TXT"

  echo "✅ English proposal created:"
  echo "$PROPOSAL_TXT"
fi
