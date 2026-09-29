import { redirect } from "next/navigation";
import { datasets } from "@/lib/api";

export default async function DatasetDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const dataset = await datasets.get(id);
  redirect(`/collections/${dataset.collection_id}`);
}
