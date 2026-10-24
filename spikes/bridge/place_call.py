"""Place the agency leg: agent number -> mock agency (or --agency-number), streamed to /ws.

PYTHONPATH=backend python -m spikes.bridge.place_call [--agency-number +1...]
"""

import argparse
import asyncio

from spikes.bridge.settings import load_settings
from spikes.bridge.twilio_calls import dial_agency


async def main(agency_number: str | None) -> None:
    settings = load_settings()
    call_sid = await dial_agency(
        settings, agency_number or settings.twilio_mock_agency_number
    )
    print(f"agency leg placed call_sid={call_sid}")
    print(
        "when its greeting shows up in the server log: curl -X POST localhost:8000/bridge"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agency-number", help="a second phone to play the agency instead of the mock"
    )
    asyncio.run(main(parser.parse_args().agency_number))
