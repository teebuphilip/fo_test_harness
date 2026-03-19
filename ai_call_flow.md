# AI Call Flow (Claude + ChatGPT)

This document focuses on how `fo_test_harness.py` sends and retrieves AI calls, with emphasis on Claude build calls and the multipart recovery mechanism, plus the feature QA call to ChatGPT.

## 1. Claude Build/Fix Calls (Send)

Inputs to Claude:
- Governance ZIP contents are read and concatenated into a single prompt block.
- The intake JSON and iteration context are appended as the dynamic block.
- Prompt caching is enabled for the governance block to reduce repeat-token cost.

How the request is sent:
- Endpoint: `https://api.anthropic.com/v1/messages`
- Headers include `anthropic-beta: prompt-caching-2024-07-31` and API key.
- The request body uses the messages array. When caching is enabled, the first message block is marked as cacheable.
- Timeout and retry logic handle 429/500/529 with exponential backoff.

Models and limits:
- Claude model is set by `Config.CLAUDE_MODEL`.
- Output tokens are capped by `CLAUDE_MAX_TOKENS` and tuned per iteration.

## 2. Claude Multipart “TCP-like” Recovery

For large builds, Claude is instructed to split output into numbered parts.

Required markers:
- `<!-- PART X/N -->` at the start of each part
- `<!-- END PART X/N -->` at the end of non-final parts
- `REMAINING FILES:` list at the end of non-final parts
- `BUILD STATE: COMPLETED_CLOSED` at the end of the final part

How the harness assembles parts:
- The first response is scanned by `detect_multipart()` for `PART X/N` markers.
- If multipart is detected and the final marker is missing, the harness requests subsequent parts in sequence.
- Each follow-up call uses `directives/prompts/part_prompt.md`, passing:
- The part number and total parts
- Files already received (so Claude does not repeat them)
- Remaining files list (so Claude knows what to output next)
- Each returned part is appended to the build output.
- The loop stops when the final part includes `BUILD STATE: COMPLETED_CLOSED` or the max part limit is hit.

Config controls:
- `--max-parts` controls the ceiling for multipart assembly (default 10).

## 3. Fallback Continuation Recovery

If output is still truncated after multipart assembly, or if no multipart markers are found, the harness uses a continuation fallback.

How it works:
- The harness checks for truncation using build-state markers and code block validation.
- If truncation is detected, it requests a continuation using `directives/prompts/continuation_prompt.md`.
- The continuation prompt includes the last 1500 characters of the previous output to resume cleanly.
- Continuations are appended with an `<!-- CONTINUATION -->` separator.
- The loop stops when a valid `BUILD STATE: COMPLETED_CLOSED` marker appears or the max continuation limit is hit.

Config controls:
- `--max-continuations` controls the ceiling for fallback continuations (default 9).

## 4. Feature QA Calls (ChatGPT)

QA calls are sent to OpenAI via the ChatGPT client.

How the request is sent:
- Endpoint: `https://api.openai.com/v1/chat/completions`
- Payload includes the QA prompt and model selection.
- Timeout and retry logic handle 429 and transient errors with backoff.

Model choice:
- Default QA model is `gpt-4o-mini` (high TPM for large prompts).
- For larger or stricter QA passes, use `--gpt-model gpt-4o` to switch to a larger model.

QA outputs:
- Responses are parsed into a structured QA report.
- Acceptance is detected by the `QA STATUS: ACCEPTED - Ready for deployment` marker.
- Rejection triggers the next fix iteration.
