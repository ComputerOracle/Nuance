import type { StatusKey } from "@/components/app/types";
import { statusMeta } from "@/components/app/status";

export function StatusBadge({ status }: { status: StatusKey }) {
  const meta = statusMeta(status);
  return (
    <div
      className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${meta.badgeBg} ${meta.badgeText}`}
    >
      {meta.label}
    </div>
  );
}
