import { Placeholder } from "@/components/Placeholder";

export default async function CasesPage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = await params;
  return <Placeholder userId={userId} title="My cases" />;
}
