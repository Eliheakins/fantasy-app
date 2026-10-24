export function ComingSoon({ title }: { title: string }) {
  return (
    <section>
      <h1 className="text-display font-semibold">{title}</h1>
      <p className="mt-2 text-muted">coming soon</p>
    </section>
  );
}
