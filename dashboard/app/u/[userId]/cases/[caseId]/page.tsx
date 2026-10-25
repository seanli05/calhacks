import { Suspense } from "react";

import { CaseLiveView } from "@/components/case/CaseLiveView";

export default async function CasePage({ params }: { params: Promise<{ userId: string; caseId: string }> }) {
  const { userId, caseId } = await params;
  // The view reads its tab from the URL (`useSearchParams`), which needs a Suspense boundary.
  return (
    <Suspense>
      <CaseLiveView userId={userId} caseId={caseId} />
    </Suspense>
  );
}
