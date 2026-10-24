/**
 * The dashboard never sends messages (rules 1 and 5). Suggestions, the chat bar and
 * the landing QR open WhatsApp with the text prefilled; the user sends it, and the
 * orchestrator answers there as usual.
 */
export function waLink(whatsappNumber: string, text: string): string {
  const digits = whatsappNumber.replace(/\D/g, "");
  return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`;
}
