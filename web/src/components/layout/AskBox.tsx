import { MessageCircleQuestion } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { navSearch } from "./navLinks";

/** The question limit the intent endpoint accepts (see NLQPanel). */
const MAX_QUESTION_LENGTH = 2000;

/** Top bar question box: an input from md up, an icon link to /ask on phones. Opens /ask?q= keeping league, team and week. */
export function AskBox() {
  const [text, setText] = useState("");
  const navigate = useNavigate();
  const { pathname, search } = useLocation();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const question = text.trim();
    if (!question) return;
    const params = new URLSearchParams(navSearch("/ask", search, pathname));
    params.set("q", question);
    navigate({ pathname: "/ask", search: params.toString() });
    setText("");
  };

  return (
    <>
      <Link
        to={{ pathname: "/ask", search: navSearch("/ask", search, pathname) }}
        aria-label="Ask"
        className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md border border-white/30 text-white md:hidden"
      >
        <MessageCircleQuestion aria-hidden size={20} />
      </Link>
      <form role="search" onSubmit={submit} className="hidden items-center gap-2 md:flex">
        <span aria-hidden className="font-display text-body italic text-[#CFE5D9]">Ask</span>
        <input
          type="text"
          aria-label="Ask a question"
          placeholder="e.g. start Kelce or Kittle"
          value={text}
          maxLength={MAX_QUESTION_LENGTH}
          onChange={(e) => setText(e.target.value)}
          className="min-h-[44px] w-64 min-w-0 rounded-full border border-white/20 bg-white/10 px-4 text-body text-white placeholder:text-[#E6F0EA]/70"
        />
      </form>
    </>
  );
}
