import { ProjectOverviewPage } from "@/components/screens/project/overview";

export default async function ProjectPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <ProjectOverviewPage projectId={projectId} />;
}
