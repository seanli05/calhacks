import { MemoryView } from "@/components/memory/MemoryView";

export default async function MemoryPage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = await params;
  return <MemoryView userId={userId} />;
}
