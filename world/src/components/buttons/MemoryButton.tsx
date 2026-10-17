// gossip-graph: open the memory page (the FalkorDB graph behind the town) for the current world, in a new tab.
import { useQuery } from 'convex/react';
import { api } from '../../../convex/_generated/api';
import memoryImg from '../../../assets/memory.svg';
import Button from './Button';

const MEMORY_UI_URL =
  (import.meta.env.VITE_MEMORY_UI_URL as string | undefined) ?? 'http://127.0.0.1:8100/ui';

export default function MemoryButton() {
  const worldStatus = useQuery(api.world.defaultWorldStatus);
  const href = worldStatus ? `${MEMORY_UI_URL}?world=${worldStatus.worldId}` : MEMORY_UI_URL;
  return (
    <Button href={href} target="_blank" imgUrl={memoryImg} title="See the village's memory graph">
      Memory
    </Button>
  );
}
