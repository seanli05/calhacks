import { CasesPage } from "@/components/cases/CasesPage";

export default async function MyCasesPage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = await params;
  return <CasesPage userId={userId} />;
}
