// gossip-graph: NPC memory lives in the graph-memory service (FalkorDB), not in Convex.
// AI Town's original vector memory (the memories/memoryEmbeddings tables, importance scoring and reflections)
// was removed. Recall, gossip, trust and "who told you?" are graph queries in the service: see ../../../memory/
// and ../../../docs/DATA_MODEL.md in the repository root.
import { v } from 'convex/values';
import { ActionCtx, internalQuery } from '../_generated/server';
import { Id } from '../_generated/dataModel';
import { internal } from '../_generated/api';
import { GameId, conversationId } from '../aiTown/ids';
import { INVESTIGATOR_TOKEN_PREFIX } from '../constants';

const selfInternal = internal.agent.memory;

type Character = { id: string; name: string; kind: 'npc' | 'human'; identity: string };

export type Recalled = {
  // First-person memory lines, e.g. "Pip told me that Kai stole a silver hammer from Bram (I believe it)."
  memories: { description: string }[];
  // Summary of this pair's most recent finished conversation, if any.
  lastConversationSummary: string | null;
  // The news the graph wants this NPC to open with, in its own words (best-ranked, not yet shared with them).
  topic: string | null;
};

function serviceUrl(): string {
  return process.env.MEMORY_SERVICE_URL ?? 'http://host.docker.internal:8100';
}

async function callMemoryService(method: 'GET' | 'POST', path: string, body?: unknown) {
  const response = await fetch(serviceUrl() + path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${method} ${path} -> ${response.status} ${await response.text()}`);
  }
  return response.json();
}

// Sends a finished conversation to the memory service, which extracts claims and spreads them as beliefs.
// AI Town calls this once per agent in the conversation; the service ingests each conversation only once.
export async function rememberConversation(
  ctx: ActionCtx,
  worldId: Id<'worlds'>,
  _agentId: GameId<'agents'>,
  _playerId: GameId<'players'>,
  conversationId: GameId<'conversations'>,
) {
  const { characters, participants, messages, interview } = await ctx.runQuery(selfInternal.loadForMemory, {
    worldId,
    conversationId,
  });
  // Interviews are recorded by the case endpoint (scripts/investigate.py); ingesting them again would duplicate them.
  if (!messages.length || interview) {
    return;
  }
  const byId = new Map(characters.map((c) => [c.id, c]));
  try {
    // Every villager, so claims about people outside this conversation can be resolved.
    await callMemoryService('POST', `/worlds/${worldId}/characters`, characters);
    await callMemoryService('POST', `/worlds/${worldId}/conversations`, {
      id: conversationId,
      participants: participants.map((id) => byId.get(id) ?? { id, name: id, kind: 'npc', identity: '' }),
      messages,
    });
  } catch (e) {
    // Keep the agent loop going. The service stores the transcript first and retries failed ingests itself.
    console.error(`memory service: could not remember ${conversationId}:`, e);
  }
}

// What `playerId` remembers when about to talk to `otherPlayerId`: ranked gossip, trust, reputation and
// past conversations, as first-person lines. Pure graph queries in the service (~2 ms), no LLM.
export async function recallMemories(
  worldId: Id<'worlds'>,
  playerId: GameId<'players'>,
  otherPlayerId: GameId<'players'>,
  k: number,
): Promise<Recalled> {
  const query = new URLSearchParams({ me: playerId, other: otherPlayerId, k: String(k) });
  try {
    const recalled = await callMemoryService('GET', `/worlds/${worldId}/recall?${query}`);
    return {
      memories: (recalled.memories as string[]).map((description) => ({ description })),
      lastConversationSummary: recalled.episodes[0]?.summary ?? null,
      topic: recalled.topic ?? null,
    };
  } catch (e) {
    console.error(`memory service: recall failed for ${playerId} -> ${otherPlayerId}:`, e);
    return { memories: [], lastConversationSummary: null, topic: null };
  }
}

export const loadForMemory = internalQuery({
  args: {
    worldId: v.id('worlds'),
    conversationId,
  },
  handler: async (ctx, args) => {
    const world = await ctx.db.get(args.worldId);
    if (!world) {
      throw new Error(`World ${args.worldId} not found`);
    }
    const agentOfPlayer = new Map(world.agents.map((a) => [a.playerId as string, a.id as string]));
    const identities = new Map<string, string>();
    const agentDescriptions = await ctx.db
      .query('agentDescriptions')
      .withIndex('worldId', (q) => q.eq('worldId', args.worldId))
      .collect();
    for (const d of agentDescriptions) {
      identities.set(d.agentId, d.identity);
    }
    const playerDescriptions = await ctx.db
      .query('playerDescriptions')
      .withIndex('worldId', (q) => q.eq('worldId', args.worldId))
      .collect();
    const characters: Character[] = playerDescriptions.map((d) => {
      const agentId = agentOfPlayer.get(d.playerId);
      return agentId
        ? { id: d.playerId, name: d.name, kind: 'npc', identity: identities.get(agentId) ?? '' }
        : { id: d.playerId, name: d.name, kind: 'human', identity: d.description };
    });
    const conversation = await ctx.db
      .query('archivedConversations')
      .withIndex('worldId', (q) => q.eq('worldId', args.worldId).eq('id', args.conversationId))
      .first();
    if (!conversation) {
      throw new Error(`Conversation ${args.conversationId} not found`);
    }
    const messages = await ctx.db
      .query('messages')
      .withIndex('conversationId', (q) =>
        q.eq('worldId', args.worldId).eq('conversationId', args.conversationId),
      )
      .collect();
    const tokens = new Map<string, string | undefined>(world.players.map((p) => [p.id as string, p.human]));
    for (const id of conversation.participants) {
      if (!tokens.has(id)) {
        const archived = await ctx.db
          .query('archivedPlayers')
          .withIndex('worldId', (q) => q.eq('worldId', args.worldId).eq('id', id))
          .first();
        tokens.set(id, archived?.human);
      }
    }
    return {
      characters,
      interview: conversation.participants.some((id) =>
        tokens.get(id)?.startsWith(INVESTIGATOR_TOKEN_PREFIX),
      ),
      participants: conversation.participants as string[],
      messages: messages.map((m) => ({ author: m.author as string, text: m.text, ts: m._creationTime })),
    };
  },
});
