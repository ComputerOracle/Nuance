// Wallet brand marks. MetaMask's is the real official artwork (see below);
// the rest are hand-drawn stand-ins — their official asset kits weren't
// fetchable here — built to be distinct and immediately recognizable
// rather than generic placeholders.

export function MetaMaskIcon() {
  // The real MetaMask fox mark, pulled from metamask.io/assets (the
  // official brand-assets page's own CDN link) and inlined verbatim —
  // not a hand-drawn approximation.
  return (
    <svg viewBox="0 0 32 32" width="20" height="20">
      <rect width="32" height="32" rx="9" fill="#1B1B1F" />
      <svg x="5.5" y="6.7" width="21" height="20.3" viewBox="0 0 142 137" fill="none">
        <path fill="#FF5C16" d="m132.24 131.751-30.481-9.076-22.986 13.741-16.038-.007-23-13.734-30.467 9.076L0 100.465l9.268-34.723L0 36.385 9.268 0l47.607 28.443h27.757L132.24 0l9.268 36.385-9.268 29.357 9.268 34.723-9.268 31.286Z" />
        <path fill="#FF5C16" d="m9.274 0 47.608 28.463-1.893 19.534L9.274 0Zm30.468 100.478 20.947 15.957-20.947 6.24v-22.197Zm19.273-26.381L54.989 48.01l-25.77 17.74-.014-.007v.013l.08 18.26 10.45-9.918h19.28ZM132.24 0 84.632 28.463l1.887 19.534L132.24 0Zm-30.467 100.478-20.948 15.957 20.948 6.24v-22.197Zm10.529-34.723h.007-.007v-.013l-.006.007-25.77-17.739L82.5 74.097h19.272l10.457 9.917.073-18.259Z" />
        <path fill="#E34807" d="m39.735 122.675-30.467 9.076L0 100.478h39.735v22.197ZM59.008 74.09l5.82 37.714-8.066-20.97-27.49-6.82 10.456-9.923h19.28Zm42.764 48.585 30.468 9.076 9.268-31.273h-39.736v22.197ZM82.5 74.09l-5.82 37.714 8.065-20.97 27.491-6.82-10.463-9.923H82.5Z" />
        <path fill="#FF8D5D" d="m0 100.465 9.268-34.723h19.93l.073 18.266 27.492 6.82 8.065 20.969-4.146 4.618-20.947-15.957H0v.007Zm141.508 0-9.268-34.723h-19.931l-.073 18.266-27.49 6.82-8.066 20.969 4.145 4.618 20.948-15.957h39.735v.007ZM84.632 28.443H56.875L54.99 47.977l9.839 63.8H76.68l9.845-63.8-1.893-19.534Z" />
        <path fill="#661800" d="M9.268 0 0 36.385l9.268 29.357h19.93l25.784-17.745L9.268 0Zm43.98 81.665h-9.029l-4.916 4.819 17.466 4.33-3.521-9.155v.006ZM132.24 0l9.268 36.385-9.268 29.357h-19.931L86.526 47.997 132.24 0ZM88.273 81.665h9.042l4.916 4.825-17.486 4.338 3.528-9.17v.007Zm-9.507 42.305 2.06-7.542-4.146-4.618H64.82l-4.145 4.618 2.059 7.542" />
        <path fill="#C0C4CD" d="M78.766 123.969v12.453H62.735v-12.453h16.03Z" />
        <path fill="#E7EBF6" d="m39.742 122.662 23.006 13.754v-12.453l-2.06-7.541-20.946 6.24Zm62.031 0-23.007 13.754v-12.453l2.06-7.541 20.947 6.24Z" />
      </svg>
    </svg>
  );
}

export function PhantomIcon() {
  return (
    <svg viewBox="0 0 32 32" width="20" height="20">
      <rect width="32" height="32" rx="9" fill="#AB9FF2" />
      <path
        d="M25 17.2c0 4.6-4.1 8.3-9.2 8.3S7 21.9 7 17.5C7 11.9 10.9 7 16 7s9 5 9 10.2z"
        fill="#FFFFFF"
      />
      <circle cx="12.6" cy="17" r="2.1" fill="#AB9FF2" />
      <circle cx="19.4" cy="17" r="2.1" fill="#AB9FF2" />
      <path
        d="M8.5 20c0 3.3 1.4 6 3.2 6 .9 0 1.3-1.5 1.3-3.4"
        stroke="#AB9FF2"
        strokeWidth="0"
        fill="none"
      />
    </svg>
  );
}

export function TrustWalletIcon() {
  return (
    <svg viewBox="0 0 32 32" width="20" height="20">
      <rect width="32" height="32" rx="9" fill="#0500FF" />
      <path
        d="M16 6c2.6 1.7 5 2.4 8 2.6 0 8.4-2.9 13.6-8 15.8-5.1-2.2-8-7.4-8-15.8 3-.2 5.4-.9 8-2.6z"
        fill="#FFFFFF"
      />
      <path
        d="M16 6c2.6 1.7 5 2.4 8 2.6 0 8.4-2.9 13.6-8 15.8V6z"
        fill="#33E6A0"
      />
    </svg>
  );
}

export function RabbyIcon() {
  return (
    <svg viewBox="0 0 32 32" width="20" height="20">
      <defs>
        <linearGradient id="rabby-g" x1="0" y1="0" x2="32" y2="32">
          <stop offset="0" stopColor="#8697FF" />
          <stop offset="1" stopColor="#7084FF" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#rabby-g)" />
      <path d="M10.5 7.5c-1.6.3-2.3 2.3-1.6 4.5l2.3 6.4 2-.7-1-9.2c-.1-.7-.9-1.1-1.7-1z" fill="#FFFFFF" />
      <path d="M21.5 7.5c1.6.3 2.3 2.3 1.6 4.5l-2.3 6.4-2-.7 1-9.2c.1-.7.9-1.1 1.7-1z" fill="#FFFFFF" />
      <ellipse cx="16" cy="20" rx="6.4" ry="5.6" fill="#FFFFFF" />
      <circle cx="13.6" cy="19.5" r="1" fill="#7084FF" />
      <circle cx="18.4" cy="19.5" r="1" fill="#7084FF" />
    </svg>
  );
}

export function OkxIcon() {
  return (
    <svg viewBox="0 0 32 32" width="20" height="20">
      <rect width="32" height="32" rx="9" fill="#000000" />
      <g fill="#FFFFFF">
        <rect x="13" y="6" width="6" height="6" />
        <rect x="6" y="13" width="6" height="6" />
        <rect x="20" y="13" width="6" height="6" />
        <rect x="13" y="20" width="6" height="6" />
      </g>
    </svg>
  );
}

export function CoinbaseIcon() {
  return (
    <svg viewBox="0 0 32 32" width="20" height="20">
      <circle cx="16" cy="16" r="16" fill="#0052FF" />
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M16 24.5c4.7 0 8.5-3.8 8.5-8.5s-3.8-8.5-8.5-8.5-8.5 3.8-8.5 8.5 3.8 8.5 8.5 8.5zm0-3.4c2.8 0 5.1-2.3 5.1-5.1s-2.3-5.1-5.1-5.1-5.1 2.3-5.1 5.1 2.3 5.1 5.1 5.1z"
        fill="#FFFFFF"
      />
    </svg>
  );
}
