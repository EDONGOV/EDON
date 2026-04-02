// Redaction helper for sensitive data

const SENSITIVE_KEYS = [
  'token',
  'authorization',
  'api_key',
  'apikey',
  'api-key',
  'password',
  'secret',
  'credential',
  'bearer',
  'x-edon-token',
  'x-api-key',
];

export function redactSensitiveData(obj: unknown, depth: number = 0): unknown {
  if (depth > 10) return obj; // Prevent infinite recursion

  if (obj === null || obj === undefined) {
    return obj;
  }

  if (typeof obj === 'string') {
    // Check if it looks like a token or key
    if (obj.length > 20 && /^[A-Za-z0-9_-]+$/.test(obj)) {
      return '[REDACTED]';
    }
    return obj;
  }

  if (Array.isArray(obj)) {
    return obj.map(item => redactSensitiveData(item, depth + 1));
  }

  if (typeof obj === 'object') {
    const result: Record<string, unknown> = {};
    
    for (const [key, value] of Object.entries(obj)) {
      const lowerKey = key.toLowerCase();
      
      if (SENSITIVE_KEYS.some(k => lowerKey.includes(k))) {
        result[key] = '[REDACTED]';
      } else {
        result[key] = redactSensitiveData(value, depth + 1);
      }
    }
    
    return result;
  }

  return obj;
}

export function formatJSON(obj: unknown): string {
  const redacted = redactSensitiveData(obj);
  return JSON.stringify(redacted, null, 2);
}
