"""Print the Nemotron model IDs your Token Factory key can use.

    python -m backend.ai.scripts.list_models

Copy the right IDs into DORY_MODEL_NANO / DORY_MODEL_SUPER / DORY_MODEL_ULTRA.
"""
from backend.ai.client import _openai_client


def main() -> None:
    models = sorted(m.id for m in _openai_client().models.list().data)
    nemotron = [m for m in models if "nemotron" in m.lower()]
    print("Nemotron models available to you:")
    for m in nemotron or ["(none found; see full list below)"]:
        print("  ", m)
    print(f"\nAll models ({len(models)}):")
    for m in models:
        print("  ", m)


if __name__ == "__main__":
    main()
