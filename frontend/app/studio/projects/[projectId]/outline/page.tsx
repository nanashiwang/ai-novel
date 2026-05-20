import { OutlinePage } from "@/components/screens/project/pages/outline";

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <OutlinePage projectId={projectId} />;
}
