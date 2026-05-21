import { MemoryPage } from "@/components/screens/project/pages/memory";

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <MemoryPage projectId={projectId} />;
}
