# LEARNINGS.md

Conventions, decisions, and hard-won lessons from building PhoenixQA.
Carried across all repos in the ecosystem.

---

## Sprint 0

### Project structure
- Mirrors defect-pilot conventions: same folder layout, same `.env.example` pattern, same dual-provider AI abstraction
- `config/settings.py` is the single source of truth — no scattered `os.getenv()` calls
- `__init__.py` in every package — avoids mysterious import errors later

### AI Provider pattern
- `BaseProvider` (ABC) → `AnthropicProvider` / `OllamaProvider` → `provider_factory.get_provider(settings)`
- Switching providers = change one env var, zero code changes
- `HealingContext` and `HealingProposal` are dataclasses — structured, typed, LLM-agnostic

### BasePage healing hooks
- `healing=False` by default — opt-in per call, not opt-out
- Healing wired at method level (`click`, `fill`) not test level — transparent to test authors
- `NotImplementedError` stubs are intentional — better than silent no-ops

### Chaos App decision
- Must be built in-house — public sites too stable, rate-limited, or auth-walled
- React/Vite chosen for ecosystem familiarity and easy DOM manipulation
- Chaos levels: LOW / MEDIUM / HIGH / CHAOS — configurable, deterministic enough to write tests against

---

## TODO (future sprints)
- Sprint 2: decide on DOM snapshot strategy (full HTML vs targeted subtree)
- Sprint 3: prompt template for selector healing — include element role, aria, surrounding context
- Sprint 6: SQLite schema design — index by page_url + broken_selector for fast few-shot lookup
