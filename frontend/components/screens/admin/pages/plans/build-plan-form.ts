import type { AdminPlan, AdminPlanUpsert } from "@/lib/api";

export function buildPlanForm(
  plan: AdminPlan | undefined,
  draft: Partial<AdminPlanUpsert>,
): AdminPlanUpsert {
  return {
    code: draft.code ?? plan?.code ?? "",
    name: draft.name ?? plan?.name ?? "",
    description: draft.description ?? plan?.description ?? "",
    price_monthly: draft.price_monthly ?? plan?.price_monthly ?? 0,
    price_yearly: draft.price_yearly ?? plan?.price_yearly ?? null,
    currency: draft.currency ?? plan?.currency ?? "CNY",
    status: draft.status ?? plan?.status ?? "active",
    features:
      draft.features ??
      plan?.features.map((feature) => ({
        feature_key: feature.feature_key,
        enabled: feature.enabled,
        limit_value: feature.limit_value,
        limit_unit: feature.limit_unit,
      })) ??
      [
        {
          feature_key: "monthly_generated_words",
          enabled: true,
          limit_value: 50000,
          limit_unit: "words",
        },
      ],
  };
}
