import { WritingWorkspacePage } from "@/components/screens/project/pages/writing";

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <WritingWorkspacePage projectId={projectId} />;
}
