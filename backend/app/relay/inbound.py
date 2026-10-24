from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    """An inbound WhatsApp message, parsed from Twilio's webhook form fields.

    Only the first media item is kept for now. Phone numbers and text are left out of
    the repr so the model can't leak them into logs by accident.
    """

    message_sid: str = Field(alias="MessageSid", pattern=r"^[A-Za-z0-9]+$")
    from_number: str = Field(alias="From", repr=False)
    to_number: str = Field(alias="To", repr=False)
    body: str = Field(default="", alias="Body", repr=False)
    num_media: int = Field(default=0, alias="NumMedia")
    media_url: str | None = Field(default=None, alias="MediaUrl0", repr=False)
    media_content_type: str | None = Field(default=None, alias="MediaContentType0")
