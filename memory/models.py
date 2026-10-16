"""Request bodies for the memory API."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CharacterIn(BaseModel):
    id: str  # AI Town player id, e.g. "p:3"
    name: str
    kind: Literal["npc", "human"] = "npc"
    identity: str = ""
    # Personality: default trust in people this character has no KNOWS edge to.
    gullibility: float | None = Field(default=None, ge=0, le=1)


class RelationshipIn(BaseModel):
    source: str  # character id of the one who trusts
    target: str  # character id of the one being trusted
    trust: float = Field(ge=0, le=1)  # how much `source` believes what `target` says


class MessageIn(BaseModel):
    author: str  # character id
    text: str
    ts: float  # ms since epoch, as AI Town stores it


class ConversationIn(BaseModel):
    id: str  # AI Town conversation id, e.g. "c:29"
    participants: list[CharacterIn] = Field(min_length=2)
    messages: list[MessageIn]

    @model_validator(mode="after")
    def authors_are_participants(self):
        ids = {p.id for p in self.participants}
        strangers = {m.author for m in self.messages} - ids
        if strangers:
            raise ValueError(f"message authors not in participants: {sorted(strangers)}")
        return self
