"""Place the spike call: agent number -> mock agency, streamed to our /ws.

PYTHONPATH=backend python -m spikes.dtmf.place_call --mode dtmf|speak|rest
"""

import argparse
import asyncio

from spikes.dtmf.probe import Mode
from spikes.dtmf.settings import load_settings, stream_url
from spikes.dtmf.twilio_calls import place_call, stream_twiml


async def main(mode: Mode) -> None:
    settings = load_settings(need_voice=mode is Mode.SPEAK)
    call_sid = await place_call(settings, stream_twiml(stream_url(settings), mode=mode))
    print(f"call placed mode={mode} call_sid={call_sid}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", type=Mode, choices=list(Mode), required=True)
    asyncio.run(main(parser.parse_args().mode))
