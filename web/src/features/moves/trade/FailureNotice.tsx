import type { ApiError } from "@/api/envelope";
import { Notice, RetryButton } from "./Notice";

/** Server-explained failures as an amber notice; "busy" and unexpected failures offer a retry. */
export function FailureNotice({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  const retry = error.code === "invalid" ? undefined : <RetryButton onClick={onRetry} />;
  return <Notice action={retry}>{error.message}</Notice>;
}
