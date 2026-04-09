import { FormulaLab } from "@/features/formulas/FormulaLab";
import { PageHeader } from "@/shared/components/PageHeader";

export function FormulasPage() {
  return (
    <div className="mx-auto w-full max-w-3xl flex-1 space-y-4 px-4 pb-12 pt-4 lg:max-w-5xl lg:px-8 lg:pt-6">
      <PageHeader
        eyebrow="Workbench / Formulas"
        title="Formula Lab"
        description="Run custom SQL against gold tables or pinned players' PBP shards. Pin players on Explore when your query uses the player token."
      />
      <FormulaLab />
    </div>
  );
}
