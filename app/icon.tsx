import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          borderRadius: 8,
          background: "#000",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <circle cx="7" cy="7.5" r="3" fill="#f0f0f0" />
          <circle cx="17" cy="7.5" r="3" fill="#a6a6a6" />
          <circle cx="12" cy="16" r="3" fill="#f0f0f0" />
        </svg>
      </div>
    ),
    { ...size }
  );
}
