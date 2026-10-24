import { UserShell } from "@/components/UserShell";

export default async function UserLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ userId: string }>;
}) {
  const { userId } = await params;
  return <UserShell userId={userId}>{children}</UserShell>;
}
