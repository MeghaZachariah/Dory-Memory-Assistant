"""Day-1 check: call each tier once on the real API and print the speed.

    python -m backend.ai.scripts.smoke_test
"""
from backend.ai import config
from backend.ai.client import ModelError, call_model


def main() -> None:
    for tier in ("nano", "super", "ultra"):
        try:
            r = call_model(tier, [{"role": "user", "content": "Reply with exactly: ok"}], purpose="smoke", max_tokens=10)
            flag = "  (over target!)" if r.latency_ms > config.LATENCY_TARGET_MS else ""
            print(f"{tier:6} {r.model:45} {r.latency_ms:6} ms  tokens {r.prompt_tokens}/{r.completion_tokens}  -> {r.text!r}{flag}")
        except ModelError as e:
            print(f"{tier:6} {config.MODELS[tier]:45} FAILED: {e}")
    print(f"\nEvery call is also logged to {config.LOG_PATH}")


if __name__ == "__main__":
    main()
