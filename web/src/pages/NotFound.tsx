import { Link } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";

export default function NotFound() {
  return (
    <section>
      <PageHeader title="Page not found" />
      <p className="measure text-muted">That address does not match a page here.</p>
      <Link to="/" className="mt-2 inline-flex min-h-[44px] items-center underline">
        Go to Home
      </Link>
    </section>
  );
}
