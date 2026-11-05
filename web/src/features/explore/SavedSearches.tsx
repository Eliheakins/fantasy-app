import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { addSaved, MAX_NAME_LENGTH, MAX_SAVED, queryWithoutShell, readSaved, removeSaved, savedHref, writeSaved } from "./savedSearchStore";

/** Name the query in the URL, keep it in this browser, run it again or delete it. */
export function SavedSearches() {
  const { search } = useLocation();
  const [saved, setSaved] = useState(readSaved);
  const [name, setName] = useState("");
  const [kept, setKept] = useState(true);
  const full = saved.length >= MAX_SAVED && !saved.some((x) => x.name === name.trim());
  const empty = queryWithoutShell(search) === "";

  const update = (next: typeof saved) => {
    setSaved(next);
    setKept(writeSaved(next));
  };
  return (
    <details className="rounded-xl border border-line px-4">
      <summary className="flex min-h-[44px] cursor-pointer items-center text-body font-semibold">Saved searches ({saved.length})</summary>
      <div className="space-y-3 pb-3">
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (empty || !name.trim()) return;
            update(addSaved(saved, name, search));
            setName("");
          }}
        >
          <label htmlFor="saved-search-name" className="text-body">Name this search</label>
          <input id="saved-search-name" value={name} maxLength={MAX_NAME_LENGTH} onChange={(e) => setName(e.target.value)} className="min-h-[44px] rounded-full border border-panel-line bg-panel px-4 text-body" />
          <button type="submit" disabled={empty || !name.trim() || full} className="min-h-[44px] rounded-full border border-panel-line bg-panel px-4 text-body disabled:opacity-50">
            Save search
          </button>
        </form>
        {full && <p className="text-caption text-muted">You can keep {MAX_SAVED} searches. Delete one to save another.</p>}
        {empty && <p className="text-caption text-muted">Pick players or stats first; the current query is empty.</p>}
        {!kept && <p role="status" className="text-caption text-warning">This browser blocked storage, so the search could not be stored and will be gone after you leave.</p>}
        <ul>
          {saved.map((s) => (
            <li key={s.name} className="flex items-center justify-between gap-2 border-t border-line first:border-t-0">
              <Link to={savedHref(s, search)} className="inline-flex min-h-[44px] items-center underline">{s.name}</Link>
              <button type="button" aria-label={`Delete ${s.name}`} onClick={() => update(removeSaved(saved, s.name))} className="min-h-[44px] px-3 text-body text-muted underline">
                Delete
              </button>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}
