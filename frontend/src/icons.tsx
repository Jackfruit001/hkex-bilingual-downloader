import type { ReactNode } from "react";

function Svg({ children, size = 18, className }: { children: ReactNode; size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      {children}
    </svg>
  );
}

export const SearchIcon = ({ size }: { size?: number }) => (
  <Svg size={size}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Svg>
);

export const DownloadIcon = () => (
  <Svg>
    <path d="M12 4v11m0 0 4-4m-4 4-4-4M5 20h14" />
  </Svg>
);

export const ZipIcon = () => (
  <Svg>
    <path d="M4 8h16v12H4zM4 8l2-4h12l2 4M12 8v5m-2 0h4" />
  </Svg>
);

export const CheckIcon = ({ className }: { className?: string }) => (
  <Svg className={className}>
    <path d="m5 12.5 4.5 4.5L19 7" />
  </Svg>
);

export const AlertIcon = () => (
  <Svg>
    <path d="M12 4 3 20h18L12 4zM12 10v4M12 17v.01" />
  </Svg>
);

export const SingleIcon = () => (
  <Svg>
    <path d="M6 12h12" />
  </Svg>
);

export const ExternalIcon = () => (
  <Svg size={14}>
    <path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6" />
  </Svg>
);

export const CompareIcon = () => (
  <Svg>
    <path d="M8 4v16M16 4v16M4 8l4-4 4 4M20 16l-4 4-4-4" />
  </Svg>
);

export const PencilIcon = () => (
  <Svg size={16}>
    <path d="M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4" />
  </Svg>
);

export const InfoIcon = () => (
  <Svg size={20}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8v.01" />
  </Svg>
);

export const ChevronLeft = () => (
  <Svg size={16}>
    <path d="m15 6-6 6 6 6" />
  </Svg>
);

export const ChevronRight = () => (
  <Svg size={16}>
    <path d="m9 6 6 6-6 6" />
  </Svg>
);

export const Spinner = () => (
  <Svg className="spin">
    <path d="M12 3a9 9 0 1 0 9 9" />
  </Svg>
);

/** Two overlapping documents: the Chinese and English versions as one unit. */
export const BrandMark = () => (
  <svg width="46" height="46" viewBox="0 0 46 46" aria-hidden="true" focusable="false" className="brand-mark">
    <rect x="2" y="7" width="23" height="29" rx="4" fill="#ffffff" fillOpacity=".3" />
    <rect x="21" y="11" width="23" height="29" rx="4" fill="#ffffff" />
    <text x="12" y="27" textAnchor="middle" fontSize="13" fontWeight="700" fill="#ffffff" fontFamily="system-ui, sans-serif">
      中
    </text>
    <text x="32.5" y="30" textAnchor="middle" fontSize="12" fontWeight="800" fill="#123a7a" fontFamily="system-ui, sans-serif">
      EN
    </text>
  </svg>
);
