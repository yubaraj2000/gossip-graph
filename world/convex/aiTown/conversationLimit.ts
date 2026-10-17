// gossip-graph: count the conversations that use the villagers' LLM (see MAX_NPC_CONVERSATIONS).
import { INVESTIGATOR_TOKEN_PREFIX } from '../constants';

export function npcConversationCount<Id>(
  conversations: Iterable<{ participants: Map<Id, unknown> }>,
  players: Map<Id, { human?: string }>,
): number {
  let count = 0;
  for (const conversation of conversations) {
    const withInvestigator = [...conversation.participants.keys()].some((id) =>
      players.get(id)?.human?.startsWith(INVESTIGATOR_TOKEN_PREFIX),
    );
    if (!withInvestigator) {
      count++;
    }
  }
  return count;
}
