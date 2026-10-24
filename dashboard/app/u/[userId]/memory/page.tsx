import { Placeholder } from "@/components/Placeholder";

export default async function MemoryPage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = await params;
  return <Placeholder userId={userId} title="What we know about you" />;
}
