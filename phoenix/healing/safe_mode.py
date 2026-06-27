"""
safe_mode.py

Human-in-the-loop healing. Shows the full healing context in the
terminal — broken selector, error, proposed fix, confidence, reasoning —
then asks accept/reject. Per direct discussion: a bare accept/reject with
no context would be useless ("dobrze wiedzieć co się akceptuje").

IMPORTANT — pytest output capturing: this uses input(), which requires
running pytest with the -s flag (--capture=no). Without -s, pytest
swallows stdout/stdin during test execution and the prompt never reaches
the terminal — the test will hang with no visible explanation. This is
documented here AND in the README/LEARNINGS so it isn't a confusing
surprise on first run.
"""
from phoenix.ai.base_provider import HealingContext, HealingProposal


def request_human_review(context: HealingContext, proposal: HealingProposal) -> bool:
    """
    Displays the full healing decision context and asks the human to
    accept or reject. Returns True if accepted, False if rejected.

    Deliberately verbose — see module docstring. A confidence number
    alone isn't enough to make an informed decision; the human needs to
    see the actual selector change and the model's stated reasoning.

    Caught via a real end-to-end run: a proposal with an EMPTY
    proposed_selector (the response_parser fallback for an unparseable
    LLM response — see response_parser.py) was accidentally accept-able
    by typing 'y'. The human did accept it, expecting "the LLM's fix,
    whatever it was" — but there was no fix, just a parse failure
    surfaced as a zero-confidence placeholder. The empty string then hit
    Playwright as `page.locator("").click()`, raising a confusing
    "Unexpected token" CSS parsing error instead of a clear message about
    what actually went wrong. There's nothing to accept here — this is
    not a human decision, it's a hard stop.
    """
    print("\n" + "=" * 70)
    print("🔥 PhoenixQA — Healing proposal requires review")
    print("=" * 70)
    print(f"Page URL:          {context.page_url}")
    print(f"Broken selector:   {context.broken_selector}")
    print(f"Error:             {context.error_message}")
    print("-" * 70)
    print(f"Proposed selector: {proposal.proposed_selector}")
    print(f"Confidence:        {proposal.confidence:.0%}")
    print(f"Reasoning:         {proposal.reasoning}")
    if proposal.alternative_selectors:
        print(f"Alternatives:      {', '.join(proposal.alternative_selectors)}")
    print("=" * 70)

    if not proposal.proposed_selector:
        print(
            "⚠️  No usable selector was proposed (LLM response could not be "
            "parsed). Nothing to accept — auto-rejecting. The original "
            "test failure will be reported."
        )
        return False

    while True:
        answer = input("Accept this fix and retry the action? [y/n]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")
