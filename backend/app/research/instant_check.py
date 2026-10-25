"""The checks that need no model and no web, run right after the fast pass (C46).

The same rules the deep pass starts with (`deep_pass._early_checks`): scam red flags
(payment demands, threats, notario offers) and the offline signals, of which any
conflict (a look-alike or non-.gov link on a federal notice, a malformed receipt
number) makes the deep pass's verdict suspicious anyway (`checks.decide_verdict`).
Running them first lets the orchestrator warn before it explains a scam letter.
"""

from app.contracts import LegitimacySignals
from app.research.deep_verify import offline_signals
from app.research.hints import guess_doc_type, where_to_look
from app.research.scam_rules import scam_red_flags


def instant_red_flags(signals: LegitimacySignals, doc_type: str | None) -> list[str]:
    """Why the letter already looks like a scam, in plain English; empty if nothing
    does. Signal conflicts are worded from their evidence."""
    hint = where_to_look(doc_type or guess_doc_type(signals))
    flags = scam_red_flags(signals, hint)
    for result in offline_signals(signals, hint, []):
        if result.state == "conflict":
            flags.extend(result.evidence)
    return list(dict.fromkeys(flags))
