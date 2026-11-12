import { Link } from "react-router-dom";

export function Brand({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className="brand" aria-label="RAG Doctor home">
      <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden>
        <rect width="32" height="32" rx="7" fill="var(--pen)" />
        <path d="M9 8h-2.5v16H9M23 8h2.5v16H23" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M16 11v10M11 16h10" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
      </svg>
      <span>RAG Doctor</span>
    </Link>
  );
}
