"""Phone agent playground (person 4): you play the phone line, the real runner (1e)
answers, and every step is shown. Manual tool; real Claude unless `--fake`.

    python -m app.phone.playground                      # from backend/
    python -m app.phone.playground --fake               # you type the model's answers
    python -m app.phone.playground --replay app/phone/playground/scripts/<name>.json

The runner runs unchanged on 1d fakes and a `FakeClock`, so time moves only when you
say. Split by job: `tap.py` (the Claude wrapper and the console relay), `session.py`
(one call on the runner), `script.py` (steps, expectations, replay), `render.py`
(output), `repl.py` (commands). Phrases in the scripts are invented, not taken from
any one line (CLAUDE.md → the mock agency is a test target).
"""
