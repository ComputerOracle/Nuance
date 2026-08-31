import type { StatusKey } from "@/components/app/types";

export interface StatusMeta {
  label: string;
  badgeBg: string;
  badgeText: string;
  cardBorder: string;
}

const STATUS_META: Record<StatusKey, StatusMeta> = {
  approved: {
    label: "Approved",
    badgeBg: "bg-positive/16",
    badgeText: "text-positive-text",
    cardBorder: "border-positive/35",
  },
  in_review: {
    label: "In Review",
    badgeBg: "bg-review/18",
    badgeText: "text-review-text",
    cardBorder: "border-review/40",
  },
  in_progress: {
    label: "In Progress",
    badgeBg: "bg-info/18",
    badgeText: "text-info-text",
    cardBorder: "border-info/40",
  },
  pending: {
    label: "Pending",
    badgeBg: "bg-neutral",
    badgeText: "text-pending-text",
    cardBorder: "border-border-4",
  },
  disputed: {
    label: "Disputed",
    badgeBg: "bg-negative/18",
    badgeText: "text-negative-text",
    cardBorder: "border-negative/40",
  },
};

export function statusMeta(key: StatusKey): StatusMeta {
  return STATUS_META[key] ?? STATUS_META.pending;
}

export function initials(name: string): string {
  return name
    .split(" ")
    .filter((w) => w.length)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

export function activeMilestoneIndex<T extends { statusKey: StatusKey }>(
  milestones: T[]
): number {
  const idx = milestones.findIndex(
    (m) =>
      m.statusKey === "in_review" ||
      m.statusKey === "in_progress" ||
      m.statusKey === "disputed"
  );
  return idx === -1 ? 0 : idx;
}

export function formatAddress(address?: string | null): string {
  if (!address) return "0x0000…0000";
  const trimmed = address.trim();
  if (trimmed.startsWith("0x") && trimmed.length >= 10) {
    return `${trimmed.slice(0, 6)}…${trimmed.slice(-4)}`;
  }
  return trimmed;
}

