#!/usr/bin/env python3
"""Check whether Claude and/or OpenAI APIs are up and responding.

Usage:
  python check_openai.py            # check both (default)
  python check_openai.py --claude   # Claude only
  python check_openai.py --openai   # OpenAI only

NOTE: A passing ping does NOT mean a big QA call will work.
OpenAI rate-limits on TWO axes independently:
  RPM  — requests per minute  (a 5-token ping barely touches this)
  TPM  — tokens per minute    (a full QA prompt can be 10k–30k tokens)
If the harness still gets 429 after this passes, you are hitting TPM quota.
Wait a minute and try again, or check your OpenAI usage dashboard.
"""

import os
import sys
import time
import argparse
import requests

MAX_ATTEMPTS = 6
WAIT_429     = 60
WAIT_RETRY   = 10


def check_openai():
    key = os.getenv('OPENAI_API_KEY')
    if not key:
        print("✗ OpenAI  — OPENAI_API_KEY not set")
        return False

    url     = 'https://api.openai.com/v1/chat/completions'
    payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": "Reply with one word: UP"}], "max_tokens": 5}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=20)
            if r.status_code == 200:
                reply = r.json()['choices'][0]['message']['content'].strip()
                print(f"✓ OpenAI  — UP  (reply: {reply!r})")
                # Show remaining quota so you know if a big QA call will succeed
                rpm_rem = r.headers.get('x-ratelimit-remaining-requests', '?')
                tpm_rem = r.headers.get('x-ratelimit-remaining-tokens',   '?')
                rpm_lim = r.headers.get('x-ratelimit-limit-requests',     '?')
                tpm_lim = r.headers.get('x-ratelimit-limit-tokens',       '?')
                tpm_rst = r.headers.get('x-ratelimit-reset-tokens',       '?')
                print(f"   Requests: {rpm_rem}/{rpm_lim} remaining")
                print(f"   Tokens  : {tpm_rem}/{tpm_lim} remaining  (resets in {tpm_rst})")
                if tpm_rem != '?' and int(tpm_rem) < 20000:
                    print(f"   ⚠ TPM quota low — large QA calls (~10k–30k tokens) may 429")
                return True
            elif r.status_code == 429:
                if attempt < MAX_ATTEMPTS:
                    print(f"⚠ OpenAI  — 429 rate-limited, waiting {WAIT_429}s (attempt {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(WAIT_429)
                else:
                    print(f"✗ OpenAI  — still 429 after {MAX_ATTEMPTS} attempts")
                    return False
            else:
                print(f"✗ OpenAI  — HTTP {r.status_code}: {r.text[:200]}")
                return False
        except requests.exceptions.Timeout:
            print(f"⚠ OpenAI  — timeout (attempt {attempt}/{MAX_ATTEMPTS})")
            if attempt < MAX_ATTEMPTS:
                time.sleep(WAIT_RETRY)
            else:
                return False
        except Exception as e:
            print(f"✗ OpenAI  — {e}")
            return False


def check_claude():
    key = os.getenv('ANTHROPIC_API_KEY')
    if not key:
        print("✗ Claude  — ANTHROPIC_API_KEY not set")
        return False

    url     = 'https://api.anthropic.com/v1/messages'
    payload = {"model": "claude-haiku-4-5-20251001", "max_tokens": 5, "messages": [{"role": "user", "content": "Reply with one word: UP"}]}
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=20)
            if r.status_code == 200:
                reply = r.json()['content'][0]['text'].strip()
                print(f"✓ Claude  — UP  (reply: {reply!r})")
                return True
            elif r.status_code == 529:
                if attempt < MAX_ATTEMPTS:
                    print(f"⚠ Claude  — 529 overloaded, waiting {WAIT_429}s (attempt {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(WAIT_429)
                else:
                    print(f"✗ Claude  — still 529 after {MAX_ATTEMPTS} attempts")
                    return False
            elif r.status_code == 429:
                if attempt < MAX_ATTEMPTS:
                    print(f"⚠ Claude  — 429 rate-limited, waiting {WAIT_429}s (attempt {attempt}/{MAX_ATTEMPTS})")
                    time.sleep(WAIT_429)
                else:
                    print(f"✗ Claude  — still 429 after {MAX_ATTEMPTS} attempts")
                    return False
            else:
                print(f"✗ Claude  — HTTP {r.status_code}: {r.text[:200]}")
                return False
        except requests.exceptions.Timeout:
            print(f"⚠ Claude  — timeout (attempt {attempt}/{MAX_ATTEMPTS})")
            if attempt < MAX_ATTEMPTS:
                time.sleep(WAIT_RETRY)
            else:
                return False
        except Exception as e:
            print(f"✗ Claude  — {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description='Check Claude / OpenAI API availability')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--claude', action='store_true', help='Check Claude only')
    group.add_argument('--openai', action='store_true', help='Check OpenAI only')
    args = parser.parse_args()

    check_both   = not args.claude and not args.openai
    results      = []

    if args.claude or check_both:
        results.append(check_claude())
    if args.openai or check_both:
        results.append(check_openai())

    sys.exit(0 if all(results) else 1)


if __name__ == '__main__':
    main()
