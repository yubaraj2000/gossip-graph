"""LLM claim extraction: turn a finished conversation into structured claims (docs/DATA_MODEL.md)."""
from memory import llm
from memory.models import ConversationIn

PREDICATES = [
    "stole_from", "attacked", "helped", "lied_to", "gave_to", "owes",
    "likes", "dislikes", "is", "did", "plans_to",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "message_index": {"type": "integer"},
                    "subject": {"type": "string"},
                    "predicate": {"type": "string", "enum": PREDICATES},
                    "object": {"type": "string"},
                    "text": {"type": "string"},
                    "valence": {"type": "number"},
                },
                "required": ["message_index", "subject", "predicate", "object", "text", "valence"],
            },
        },
    },
    "required": ["summary", "claims"],
}

SYSTEM = f"""You read a conversation between villagers and list the claims people make about someone.
A claim is a statement about a named person: something they did, a trait they have, how they feel about someone, or a plan.

Rules:
- Only list claims whose subject is in the known-people list. Skip greetings, questions, small talk, remarks about objects or the weather, and remarks about how someone looks or feels right now.
- subject: the person the claim is about, spelled exactly as in the known-people list.
- predicate: one of {", ".join(PREDICATES)}. Use "did" for any other action and "is" for a lasting trait.
- object: for stole_from, attacked, helped, lied_to, gave_to, owes, likes and dislikes, the other PERSON's exact name (put the thing involved in text). Otherwise the thing involved, or "" if none.
- text: the claim as one short plain sentence in the third person, e.g. "Kai stole a silver hammer from Bram".
- valence: how the claim affects the subject's reputation: -1 for crimes or violence, -0.5 for lies or cruelty, -0.2 for mild faults, 0 for neutral facts, 0.5 for kindness, 1 for heroism.
- message_index: the [number] of the message where the claim is first made.
- If someone only repeats or reacts to a claim made earlier in the conversation, do not list it again.

Also write summary: one sentence describing what happened in the conversation."""


def extract(conv: ConversationIn, known_people: list[str]) -> dict:
    names = {p.id: p.name for p in conv.participants}
    transcript = "\n".join(f"[{i}] {names[m.author]}: {m.text}" for i, m in enumerate(conv.messages))
    user = f"Known people: {', '.join(known_people)}\n\nConversation:\n{transcript}"
    return llm.chat_json(SYSTEM, user, SCHEMA)
