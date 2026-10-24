"""Logs each final transcript as a `TranscriptLine`, the shape `transcripts.lines` uses."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from app.phone.ports import TranscriptLine
from loguru import logger
from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class HeardLog(FrameProcessor):
    def __init__(
        self,
        *,
        stream: str,
        speaker: Literal["agent", "agency", "user"],
        since_bridge: Callable[[], str],
    ) -> None:
        super().__init__()
        self._stream = stream
        self._speaker = speaker
        self._since_bridge = since_bridge

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            line = TranscriptLine(
                at=datetime.now(UTC), speaker=self._speaker, text=frame.text.strip()
            )
            logger.info(
                f"HEARD stream={self._stream} {self._since_bridge()} "
                f"{line.model_dump_json()}"
            )
