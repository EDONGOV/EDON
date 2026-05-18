export type FetchWithTimeoutOptions = RequestInit & {
  timeoutMs?: number;
  retries?: number;
  retryDelayMs?: number;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function fetchWithTimeout(url: string, options: FetchWithTimeoutOptions = {}) {
  const {
    timeoutMs = 10000,
    retries = 2,
    retryDelayMs = 400,
    ...init
  } = options;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        ...init,
        signal: controller.signal,
      });

      if (!response.ok && response.status >= 500 && attempt < retries) {
        await sleep(retryDelayMs * Math.pow(2, attempt));
        continue;
      }

      return response;
    } catch (error) {
      if (attempt >= retries) {
        throw error;
      }
      await sleep(retryDelayMs * Math.pow(2, attempt));
    } finally {
      clearTimeout(timeoutId);
    }
  }

  throw new Error("Request failed after retries");
}
