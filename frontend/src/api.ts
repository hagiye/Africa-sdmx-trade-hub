const configuredBase = import.meta.env.VITE_API_BASE_URL ?? "";
export const API_BASE_URL = configuredBase.replace(/\/$/, "");

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export async function fetchJson<T>(path: string, timeoutMs = 12000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(apiUrl(path), {
      headers: { Accept: "application/json" },
      signal: controller.signal
    });
    if (!response.ok) {
      throw new Error(
        response.status >= 500
          ? "The statistics service is temporarily unavailable."
          : `The request could not be completed (${response.status}).`
      );
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("The statistics service took too long to respond.");
    }
    if (error instanceof Error) throw error;
    throw new Error("The statistics service could not be reached.");
  } finally {
    window.clearTimeout(timeout);
  }
}

export function formatExactDecimal(value: string): string {
  const match = value.match(/^(-?)(\d+)(\.\d+)?$/);
  if (!match) return value;
  const [, sign, integer, fraction = ""] = match;
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${sign}${grouped}${fraction}`;
}
