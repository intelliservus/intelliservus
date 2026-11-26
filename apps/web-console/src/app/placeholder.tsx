export function ModulePlaceholder({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </header>
      <div className="rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
        页面骨架，随对应垂直切片交付
      </div>
    </section>
  );
}
