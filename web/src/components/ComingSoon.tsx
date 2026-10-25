import { PageHeader } from "./PageHeader";

export function ComingSoon({ title }: { title: string }) {
  return (
    <section>
      <PageHeader title={title} />
      <p className="text-muted">coming soon</p>
    </section>
  );
}
