// Minimal EIP-1193 provider typing — just what this app calls.
export interface Eip1193Provider {
  request: (args: { method: string; params?: unknown[] | object }) => Promise<unknown>;
  on?: (event: string, handler: (...args: unknown[]) => void) => void;
  removeListener?: (event: string, handler: (...args: unknown[]) => void) => void;
}

export interface Eip1193RequestError {
  code: number;
  message: string;
}

export function isEip1193Error(err: unknown): err is Eip1193RequestError {
  return (
    typeof err === "object" &&
    err !== null &&
    "code" in err &&
    typeof (err as { code: unknown }).code === "number"
  );
}
