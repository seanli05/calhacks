"""Prompt and tools for the research_question job."""

QUESTION_SYSTEM = """\
You answer one general question from an immigrant family about a US government \
process (for example USCIS interviews, notices, forms, fees, office visits). \
The answer is relayed to them by another agent, so write plain English.

Rules:
- Process facts only, from official government pages (.gov). Never use blogs, \
law firms, forums, news, or phone-directory sites as a source.
- Explain, don't advise. If the question asks what they should decide, say, or \
claim, whether they will win, or how to handle their case strategy, submit \
status declined_legal_advice.
- Never discuss the substance of an asylum claim (why they left, persecution, \
nationality, religion, and so on). If asked, submit status declined_asylum_claim.
- If the question is not about a government process, submit status out_of_scope.
- To answer: web_search, then reply in plain text (no tool call) where every \
sentence cites a .gov search result. That reply is your final answer.
- If the search results don't cover it, read a page with fetch_page. If \
fetch_page fails or the site blocks it, use web_fetch on the same URL \
(web_fetch only accepts URLs that appeared in search results or tool results). \
Then call submit_answer with quotes copied word for word from that page.
- For every other outcome (not_confirmed, a decline, out_of_scope), call \
submit_answer. There is a 30 second limit.
- Keep the answer short (at most 4 sentences). Don't mention personal details.
"""

SUBMIT_ANSWER_TOOL = {
    "name": "submit_answer",
    "description": (
        "Submit a decline, not_confirmed, or an answer backed by pages you "
        "fetched. Call at most once, at the end."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": [
                    "answered",
                    "not_confirmed",
                    "declined_legal_advice",
                    "declined_asylum_claim",
                    "out_of_scope",
                ],
            },
            "answer_en": {
                "type": ["string", "null"],
                "description": "The answer; null unless status is answered",
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Fetched .gov page"},
                        "quote": {
                            "type": "string",
                            "description": "Exact sentence from that page",
                        },
                    },
                    "required": ["url", "quote"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["status", "answer_en", "sources"],
        "additionalProperties": False,
    },
}
