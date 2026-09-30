export const MAX_FAKE = 140;

// Same cleanup for every option on the ballot, fakes and the real definition alike, so typing style
// is never a tell: trim, collapse spaces, capitalize the first letter, end with punctuation, cap length.
export function tidy(raw: string): string {
  let s = raw.replace(/\s+/g, " ").trim();
  if (!s) return "";
  if (s.length > MAX_FAKE) s = s.slice(0, MAX_FAKE).replace(/\s+\S*$/, "").trim() || s.slice(0, MAX_FAKE);
  s = s.replace(/[\s,;:–—-]+$/, "");
  s = s.charAt(0).toUpperCase() + s.slice(1);
  if (!/[.!?…)"']$/.test(s)) s += ".";
  return s;
}

// Loose equality for spotting a fake that duplicates another option word for word.
export function sameText(a: string, b: string): boolean {
  const norm = (x: string) => x.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  return norm(a) === norm(b);
}
