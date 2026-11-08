/** Backend datetimes may come without timezone (UTC) — normalise and format in Indonesian. */
export const parseDate = (iso: string) => new Date(/Z$|[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + "Z");

export const fmtDate = (iso: string) => {
  const d = parseDate(iso);
  return d.toLocaleString("id-ID", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
};
