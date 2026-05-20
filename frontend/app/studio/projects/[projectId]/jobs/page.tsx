import { JobsPage } from "@/components/screens/project/pages/jobs";

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <JobsPage projectId={projectId} />;
}
