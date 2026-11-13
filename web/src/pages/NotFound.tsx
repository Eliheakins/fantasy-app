import { Link } from "react-router";
import { PageHeader } from "@/components/PageHeader";
import { linkButtonClass } from "@/components/ui/styles";
import { cn } from "@/lib/utils";

export default function NotFound() {
  return (
    <section>
      <PageHeader title="Page not found" />
      <p className="measure text-muted">That address does not match a page here.</p>
      <Link to="/" className={cn("mt-2", linkButtonClass)}>
        Go to Home
      </Link>
    </section>
  );
}
