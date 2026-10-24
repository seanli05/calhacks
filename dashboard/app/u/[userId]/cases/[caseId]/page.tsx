import { CaseLiveView } from "@/components/case/CaseLiveView";

export default async function CasePage({ params }: { params: Promise<{ userId: string; caseId: string }> }) {
  const { userId, caseId } = await params;
  return <CaseLiveView userId={userId} caseId={caseId} />;
}
