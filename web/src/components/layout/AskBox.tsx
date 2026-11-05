import { MessageCircleQuestion } from "lucide-react";
import { type FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { navSearch } from "./navLinks";

/** The question limit the intent endpoint accepts (see NLQPanel). */
const MAX_QUESTION_LENGTH = 2000;

/** Top bar question box: an input from md up, an icon that reveals it on phones. Opens /ask?q= keeping league and team. */
export function AskBox() {
  const [open, setOpen] = useState(false);
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
    setOpen(false);
  };

  return (
    <form role="search" onSubmit={submit} className={open ? "flex w-full items-center gap-2 md:w-auto" : "flex items-center gap-2"}>
      <button
        type="button"
        aria-label="Show the ask box"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md border border-border md:hidden"
      >
        <MessageCircleQuestion aria-hidden size={20} />
      </button>
      <input
        type="text"
        aria-label="Ask a question"
        placeholder="Ask, e.g. start Kelce or Kittle"
        value={text}
        maxLength={MAX_QUESTION_LENGTH}
        onChange={(e) => setText(e.target.value)}
        className={`min-h-[44px] min-w-0 flex-1 rounded-md border border-border bg-transparent px-3 text-body md:block md:w-72 md:flex-none ${open ? "block" : "hidden"}`}
      />
    </form>
  );
}
