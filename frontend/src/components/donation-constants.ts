/**
 * Public Google Form for requesting withdrawal of a previous donation.
 * The Donation ID field is prefilled via entry.1579285102.
 * Email (entry.1671528607) and Reason (entry.1506875294) are left blank
 * for the user to fill in.
 */
export const WITHDRAW_FORM_URL =
  "https://docs.google.com/forms/d/e/1FAIpQLSelAMx_Zc_n68Zoy-6cxV5gIeqlY0eBqhxdN9pcyEcNPLE_8Q/viewform";

export const WITHDRAW_FORM_DONATION_ID_ENTRY = "entry.1579285102";

/** Build a withdrawal URL, optionally prefilling the Donation ID field. */
export function buildWithdrawUrl(donationId?: string): string {
  if (!donationId) return WITHDRAW_FORM_URL;
  const params = new URLSearchParams({
    usp: "pp_url",
    [WITHDRAW_FORM_DONATION_ID_ENTRY]: donationId,
  });
  return `${WITHDRAW_FORM_URL}?${params.toString()}`;
}

/** Format an ISO timestamp as "Apr 16, 2026 · 3:42 PM" in the user's locale. */
export function formatDonatedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const dateStr = date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
  const timeStr = date.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
  return `${dateStr} · ${timeStr}`;
}
