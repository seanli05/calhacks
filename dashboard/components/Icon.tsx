const PATHS = {
  doc: (
    <>
      <path d="M7 3h7l4 4v14H7z" />
      <path d="M14 3v4h4M10 12h5M10 16h5" />
    </>
  ),
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  chat: <path d="M4 5h16v11H9l-5 4z" />,
  phone: (
    <path d="M6 3.5h3.2l1.6 4.4-2.2 1.6a11 11 0 0 0 5.9 5.9l1.6-2.2 4.4 1.6V18a2 2 0 0 1-2 2A16 16 0 0 1 4 6a2 2 0 0 1 2-2.5z" />
  ),
  keypad: (
    <>
      <circle cx="7" cy="6" r="1.2" />
      <circle cx="12" cy="6" r="1.2" />
      <circle cx="17" cy="6" r="1.2" />
      <circle cx="7" cy="11" r="1.2" />
      <circle cx="12" cy="11" r="1.2" />
      <circle cx="17" cy="11" r="1.2" />
      <circle cx="12" cy="16" r="1.2" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8v4.5l3 2" />
    </>
  ),
  person: (
    <>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M4.5 20c1.4-3.8 4.2-5.6 7.5-5.6s6.1 1.8 7.5 5.6" />
    </>
  ),
  link: (
    <path d="M10 14l4-4M8.5 11.5l-2 2a3.5 3.5 0 0 0 5 5l2-2M15.5 12.5l2-2a3.5 3.5 0 0 0-5-5l-2 2" />
  ),
  end: (
    <path d="M3 13.5c5-4.5 13-4.5 18 0l-2.2 2.6-3.6-1.4v-2.4a12 12 0 0 0-6.4 0v2.4l-3.6 1.4z" />
  ),
  warn: (
    <>
      <path d="M12 4l9 16H3z" />
      <path d="M12 10v4M12 17v.01" />
    </>
  ),
  trash: <path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13" />,
  memory: <path d="M7 4h10v16l-5-3.5L7 20z" />,
  book: <path d="M5 4h6a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H5zM19 4h-4a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h4z" />,
  arrow: <path d="M5 12h13M13 6l6 6-6 6" />,
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16l4.5 4.5" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l7 3v6c0 4-3 7.5-7 9-4-1.5-7-5-7-9V6z" />
      <path d="M9 12l2 2 4-4" />
    </>
  ),
  wave: <path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2" />,
  chevron: <path d="M6 9l6 6 6-6" />,
  lock: (
    <>
      <rect x="5.5" y="10.5" width="13" height="9.5" />
      <path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" />
    </>
  ),
  close: <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />,
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 17 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flex: "none" }}
    >
      {PATHS[name]}
    </svg>
  );
}

/** Which icon a feed event shows, by its dotted type. */
export function iconForEvent(type: string): IconName {
  if (type.endsWith(".deleted") || type === "user.deleted_all") return "trash";
  if (type.startsWith("case.")) return "doc";
  if (type.startsWith("research.")) return "chat";
  if (type === "verification.verified") return "check";
  if (type.startsWith("verification.")) return "warn";
  if (type === "consent.given") return "check";
  if (type.startsWith("consent.")) return "chat";
  if (type === "call.dialing" || type === "call.user_dialed") return "phone";
  if (type.startsWith("call.menu")) return "keypad";
  if (type.startsWith("call.ask_user")) return "chat";
  if (type === "call.on_hold") return "clock";
  if (type === "call.human_detected") return "person";
  if (type === "call.user_joined") return "link";
  if (type === "call.user_unreachable") return "warn";
  if (type === "call.ended") return "end";
  if (type.startsWith("memory.")) return "memory";
  if (type.startsWith("glossary.")) return "book";
  return "chat";
}
