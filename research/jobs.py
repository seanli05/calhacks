"""Job handlers: the only research code that touches the Store."""

from research.sim.store import Job, Store


async def handle_research_fast(job: Job, store: Store) -> None:
    """Run a `research_fast` job end to end.

    Reads the documents, runs the fast pass, writes `cases` and `case_refs`,
    queues `memory_write` and (on status ok) `research_deep`, logs
    `research.fast_*` events, and sets the job result to R1.
    """
    raise NotImplementedError


async def handle_research_deep(job: Job, store: Store) -> None:
    """Run a `research_deep` job end to end.

    Reads the case's signals, runs the deep pass, writes `verifications` and
    `case_briefs`, logs `research.deep_*` and `verification.*` events, and
    sets the job result to R2.
    """
    raise NotImplementedError
