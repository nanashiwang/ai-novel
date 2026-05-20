import { ExportPage } from "@/components/screens/project/pages/export";

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <ExportPage projectId={projectId} />;
}
