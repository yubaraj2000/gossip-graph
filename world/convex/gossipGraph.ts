// gossip-graph: lets the investigator agent (scripts/investigate.py --in-town) appear in AI Town as a visible
// player: join, walk, invite a villager, post the interview lines the memory service recorded, and leave.
// Every call needs INVESTIGATOR_SECRET (Convex env), so only that script can act through these mutations.
import { ConvexError, v } from 'convex/values';
import { mutation } from './_generated/server';
import { insertInput } from './aiTown/insertInput';
import { conversationId, playerId } from './aiTown/ids';
import { point } from './util/types';
import { INVESTIGATOR_TOKEN_PREFIX } from './constants';

function authorize(secret: string) {
  const expected = process.env.INVESTIGATOR_SECRET;
  if (!expected || secret !== expected) {
    throw new ConvexError('not allowed');
  }
}

export const join = mutation({
  args: {
    secret: v.string(),
    worldId: v.id('worlds'),
    name: v.string(),
    character: v.string(),
    description: v.string(),
  },
  handler: async (ctx, args) => {
    authorize(args.secret);
    return await insertInput(ctx, args.worldId, 'join', {
      name: args.name,
      character: args.character,
      description: args.description,
      tokenIdentifier: INVESTIGATOR_TOKEN_PREFIX + args.name,
    });
  },
});

export const moveTo = mutation({
  args: { secret: v.string(), worldId: v.id('worlds'), playerId, destination: point },
  handler: async (ctx, args) => {
    authorize(args.secret);
    return await insertInput(ctx, args.worldId, 'moveTo', {
      playerId: args.playerId,
      destination: args.destination,
    });
  },
});

export const invite = mutation({
  args: { secret: v.string(), worldId: v.id('worlds'), playerId, invitee: playerId },
  handler: async (ctx, args) => {
    authorize(args.secret);
    return await insertInput(ctx, args.worldId, 'startConversation', {
      playerId: args.playerId,
      invitee: args.invitee,
    });
  },
});

// Posts one interview line as either participant (the villager's testimony comes from the graph, word for word).
export const say = mutation({
  args: { secret: v.string(), worldId: v.id('worlds'), conversationId, playerId, text: v.string() },
  handler: async (ctx, args) => {
    authorize(args.secret);
    await ctx.db.insert('messages', {
      conversationId: args.conversationId,
      author: args.playerId,
      messageUuid: crypto.randomUUID(),
      text: args.text,
      worldId: args.worldId,
    });
    return await insertInput(ctx, args.worldId, 'finishSendingMessage', {
      conversationId: args.conversationId,
      playerId: args.playerId,
      timestamp: Date.now(),
    });
  },
});

export const leaveConversation = mutation({
  args: { secret: v.string(), worldId: v.id('worlds'), playerId, conversationId },
  handler: async (ctx, args) => {
    authorize(args.secret);
    return await insertInput(ctx, args.worldId, 'leaveConversation', {
      playerId: args.playerId,
      conversationId: args.conversationId,
    });
  },
});
