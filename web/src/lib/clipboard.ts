/** Clipboard API first, then a hidden textarea and execCommand; true when the text was copied. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // clipboard missing or refused (insecure page, no permission): use the fallback
  }
  const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const box = document.createElement("textarea");
  box.value = text;
  box.setAttribute("readonly", "");
  box.style.position = "fixed";
  box.style.opacity = "0";
  document.body.appendChild(box);
  box.select();
  box.setSelectionRange(0, text.length); // iOS ignores select() alone
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    box.remove();
    previous?.focus();
  }
}
