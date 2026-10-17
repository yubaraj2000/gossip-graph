import { npcConversationCount } from './conversationLimit';

const players = new Map<string, { human?: string }>([
  ['p:1', {}],
  ['p:2', {}],
  ['p:3', {}],
  ['p:4', {}],
  ['p:9', { human: 'investigator:Inspector Vikram' }],
]);
const conv = (...ids: string[]) => ({ participants: new Map(ids.map((id) => [id, {}])) });

describe('npcConversationCount', () => {
  test('counts villager conversations', () => {
    expect(npcConversationCount([conv('p:1', 'p:2'), conv('p:3', 'p:4')], players)).toBe(2);
  });

  test('ignores investigator interviews', () => {
    expect(npcConversationCount([conv('p:1', 'p:2'), conv('p:9', 'p:3')], players)).toBe(1);
  });

  test('is zero with no conversations', () => {
    expect(npcConversationCount([], players)).toBe(0);
  });
});
