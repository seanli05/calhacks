"""The real line's ears (`listener.py`): turns from voice activity and transcripts,
and the quiet between them. Timestamps only; no audio, no network."""

from array import array

from app.phone.audio_pipeline import MarkingTwilioSerializer
from app.phone.line import Heard, LineEvent, NonSpeech, Overheard, SpeechStarted
from app.phone.listener import (
    FORK_TIMING,
    LOUD_RMS,
    PlaybackMarkFrame,
    TurnAssembler,
    TurnTiming,
    overheard,
    rms,
)
from pipecat.serializers.twilio import TwilioFrameSerializer

GAP = TurnTiming().merge_gap_s
GRACE = TurnTiming().final_grace_s


def test_a_fork_makes_a_line_of_each_finished_phrase() -> None:
    """Forks feed only the live view, so they don't wait to join phrases."""
    turns = TurnAssembler(now=0, timing=FORK_TIMING)
    turns.speech_started(1.0)
    turns.speech_stopped(2.0)
    turns.transcript("Your interview is still on", 2.2)
    assert turns.tick(2.3) == [Heard(text="Your interview is still on")]
    assert turns.speech_started(2.5) == [SpeechStarted()]
    turns.speech_stopped(3.5)
    turns.transcript("for November 12.", 3.6)
    assert turns.tick(3.7) == [Heard(text="for November 12.")]


def _loud(turns: TurnAssembler, start: float, end: float) -> None:
    """Hold music: loud audio every 20 ms."""
    now = start
    while now < end:
        turns.audio(LOUD_RMS * 3, now)
        now += 0.02


def test_fragments_join_into_one_turn_once_the_line_is_quiet() -> None:
    turns = TurnAssembler(now=0)
    assert turns.speech_started(1.0) == [SpeechStarted()]
    turns.speech_stopped(2.0)
    turns.transcript("For case status, press 1.", 2.3)
    assert turns.tick(2.4) == []
    assert turns.speech_started(2.6) == []  # a pause between options, same turn
    turns.speech_stopped(4.0)
    turns.transcript("For interviews, press 2.", 4.2)

    assert turns.tick(4.0 + GAP - 0.1) == []
    assert turns.tick(4.0 + GAP + 0.01) == [
        Heard(text="For case status, press 1. For interviews, press 2.")
    ]


def test_a_late_last_fragment_is_waited_for() -> None:
    turns = TurnAssembler(now=0)
    turns.speech_started(1.0)
    turns.speech_stopped(2.0)
    # The gap passed, but speech-to-text hasn't answered.
    assert turns.tick(2.0 + GAP + 0.1) == []
    turns.transcript("Please hold.", 2.0 + GAP + 0.2)
    assert turns.tick(2.0 + GAP + 0.3) == [Heard(text="Please hold.")]


def test_a_turn_with_no_words_closes_as_non_speech_soon_after_the_gap() -> None:
    turns = TurnAssembler(now=0)
    turns.speech_started(1.0)
    turns.speech_stopped(2.0)
    closes = 2.0 + GAP + GRACE + 0.01
    assert turns.tick(closes - 0.1) == []
    assert turns.tick(closes) == [NonSpeech(sound="silence", seconds=closes - 1.0)]


def test_a_wordless_turn_during_music_is_music() -> None:
    turns = TurnAssembler(now=0)
    _loud(turns, 0, 4)
    turns.speech_started(4.0)  # the VAD heard a singer
    turns.speech_stopped(6.0)
    [event] = turns.tick(8.0)
    assert isinstance(event, NonSpeech) and event.sound == "music"


def test_a_long_turn_is_cut_so_a_long_menu_isnt_held_back() -> None:
    turns = TurnAssembler(now=0)
    turns.speech_started(0.0)
    turns.transcript("For a pending application, press 1.", 5.0)
    assert turns.tick(24.9) == []
    assert turns.tick(25.0) == [
        Heard(text="For a pending application, press 1."),
        SpeechStarted(),
    ]


def test_quiet_is_reported_every_five_seconds_with_its_running_length() -> None:
    turns = TurnAssembler(now=0)
    _loud(turns, 0, 10)
    assert turns.tick(4.9) == []
    assert turns.tick(5.0) == [NonSpeech(sound="music", seconds=5.0)]
    assert turns.tick(7.0) == []
    assert turns.tick(10.0) == [NonSpeech(sound="music", seconds=10.0)]


def test_quiet_after_a_turn_counts_from_when_the_speech_stopped() -> None:
    turns = TurnAssembler(now=0)
    turns.speech_started(1.0)
    turns.speech_stopped(2.0)
    turns.transcript("Goodbye.", 2.1)
    assert turns.tick(3.0) == [Heard(text="Goodbye.")]
    assert turns.tick(6.9) == []
    assert turns.tick(7.0) == [NonSpeech(sound="silence", seconds=5.0)]


def test_no_report_while_someone_is_talking() -> None:
    turns = TurnAssembler(now=0)
    turns.speech_started(1.0)
    assert turns.tick(12.0) == []


def test_a_transcript_after_its_turn_closed_is_a_turn_of_its_own() -> None:
    turns = TurnAssembler(now=0)
    turns.speech_started(1.0)
    turns.speech_stopped(2.0)
    turns.tick(4.0)  # closed as non-speech: speech-to-text was very late
    assert turns.transcript("Hello?", 4.5) == [SpeechStarted(), Heard(text="Hello?")]


def test_flush_closes_a_half_built_turn() -> None:
    turns = TurnAssembler(now=0)
    assert turns.flush(1.0) == []
    turns.speech_started(1.0)
    turns.transcript("To repeat", 2.0)
    assert turns.flush(2.5) == [Heard(text="To repeat")]


def test_a_fork_passes_on_only_finished_turns_as_its_speakers_lines() -> None:
    lines: list[LineEvent] = []
    emit = overheard(lines.append, "agency")
    turns = TurnAssembler(now=0)
    for event in [
        *turns.speech_started(1.0),
        *turns.speech_stopped(2.0),
        *turns.transcript("Your reference number is", 2.2),
        *turns.speech_started(2.4),
        *turns.speech_stopped(4.0),
        *turns.transcript("C as in cat, 4, 4, 7.", 4.1),
        *turns.tick(5.1),
        *turns.tick(11.0),  # a quiet stretch: dropped
    ]:
        emit(event)

    assert lines == [
        Overheard(
            speaker="agency", text="Your reference number is C as in cat, 4, 4, 7."
        )
    ]


def test_rms() -> None:
    assert rms(b"") == 0.0
    assert rms(array("h", [300, -300, 300, -300]).tobytes()) == 300.0


async def test_twilios_mark_echo_becomes_a_playback_frame() -> None:
    serializer = MarkingTwilioSerializer(
        stream_sid="MZ1",
        params=TwilioFrameSerializer.InputParams(auto_hang_up=False),
    )
    frame = await serializer.deserialize(
        '{"event": "mark", "streamSid": "MZ1", "mark": {"name": "say-7"}}'
    )
    assert isinstance(frame, PlaybackMarkFrame) and frame.mark == "say-7"
    assert await serializer.deserialize('{"event": "stop"}') is None
