"""
autonomous_mode.py

Historical placeholder — Autonomous Mode is fully implemented, but NOT
in this file. The actual logic lives in:
  - phoenix/healing/autonomous_policy.py (AutonomousPolicy, HealingBudget,
    HealLifecycleTimer)
  - phoenix/healing/healer.py (Healer._attempt_heal_autonomous())

This file predates that decision (see LEARNINGS.md Sprint 5) and was
never deleted or repurposed afterward — kept here, now correctly
documented, rather than silently removed, since removing it invisibly
could look like a regression to a future `git blame` reader rather than
a deliberate cleanup. No import in the codebase references this module;
safe to delete outright in a future pass if a cleaner history matters
more than a paper trail.
"""