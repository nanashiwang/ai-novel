import { CharactersPage } from "@/components/screens/project/detail-pages";

export default async function Page({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <CharactersPage projectId={projectId} />;
}
