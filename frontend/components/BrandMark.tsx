export function BrandMark({ className = "size-8" }: { className?: string }) {
  return (
    <svg className={`${className} shrink-0`} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="#102D4F" />
      <path d="m8 11 8-4 8 4-8 4-8-4Z" stroke="#7DE3CD" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="m8 16 8 4 8-4M8 21l8 4 8-4" stroke="white" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
