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


class EventIn(BaseModel):
    """Something that really happened (narrator). Characters may be given by id or by name."""
    kind: str  # one of the claim predicates, e.g. "stole_from"
    actor: str
    target: str | None = None
    description: str  # e.g. "Kabir stole a silver hammer from Ramesh's forge"
    claim: str | None = None  # what people will say about it; defaults to the description
    valence: float = Field(default=-0.8, ge=-1, le=1)  # how it reflects on the actor
    severity: float = Field(default=0.8, ge=0, le=1)
    witnesses: list[str] = []
    id: str | None = None  # defaults to a hash of the event, so re-sending it is harmless
    ts: float | None = None  # ms since epoch; defaults to now


class CaseIn(BaseModel):
    """An investigation. The investigator is a character outside AI Town (e.g. id "inv:vikram")."""
    title: str  # e.g. "The missing silver hammer"
    question: str  # what the investigator must find out
    investigator: CharacterIn
    id: str | None = None  # defaults to a hash of the title


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
