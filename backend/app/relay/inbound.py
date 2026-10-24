from collections.abc import Mapping

from pydantic import BaseModel, Field

WHATSAPP_PREFIX = "whatsapp:"

# Twilio allows up to 10 media items per WhatsApp message.
MAX_MEDIA = 10


class InboundMedia(BaseModel):
    url: str = Field(repr=False)
    content_type: str

    @property
    def is_letter_page(self) -> bool:
        """Photos and PDFs are pages of a letter; voice notes and the rest are not."""
        return self.content_type.startswith("image/") or (
            self.content_type == "application/pdf"
        )


class InboundMessage(BaseModel):
    """An inbound WhatsApp message, parsed from Twilio's webhook form fields.

    Phone numbers, text, and media URLs are left out of the repr so the model can't
    leak them into logs by accident.
    """

    message_sid: str = Field(alias="MessageSid", pattern=r"^[A-Za-z0-9]+$")
    from_number: str = Field(alias="From", repr=False)
    to_number: str = Field(alias="To", repr=False)
    body: str = Field(default="", alias="Body", repr=False)
    num_media: int = Field(default=0, alias="NumMedia", ge=0, le=MAX_MEDIA)
    media: list[InboundMedia] = Field(default_factory=list)

    @classmethod
    def from_form(cls, params: Mapping[str, str]) -> "InboundMessage":
        """Twilio numbers media fields (`MediaUrl0`, `MediaUrl1`, ...), so they're
        collected here rather than through aliases."""
        message = cls.model_validate(params)
        message.media = [
            InboundMedia(
                url=params[f"MediaUrl{i}"],
                content_type=params.get(
                    f"MediaContentType{i}", "application/octet-stream"
                ),
            )
            for i in range(message.num_media)
            if params.get(f"MediaUrl{i}")
        ]
        return message

    @property
    def whatsapp_number(self) -> str:
        """The sender in E.164, as `users.whatsapp_number` stores it."""
        return self.from_number.removeprefix(WHATSAPP_PREFIX)

    @property
    def text(self) -> str:
        return self.body.strip()
