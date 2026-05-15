import { BiblePage } from "@/components/screens/project/detail-pages";

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <BiblePage projectId={projectId} />;
}
