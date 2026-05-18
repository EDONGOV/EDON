/**
 * Email validation utilities
 * Ensures only company emails are accepted (blocks personal email providers)
 */

// List of common personal email providers to block
const PERSONAL_EMAIL_PROVIDERS = [
  'gmail.com',
  'yahoo.com',
  'hotmail.com',
  'outlook.com',
  'live.com',
  'msn.com',
  'aol.com',
  'icloud.com',
  'mail.com',
  'protonmail.com',
  'proton.me',
  'yandex.com',
  'zoho.com',
  'gmx.com',
  'mail.ru',
  'qq.com',
  '163.com',
  '126.com',
  'sina.com',
  'rediffmail.com',
  'inbox.com',
  'fastmail.com',
  'tutanota.com',
  'hey.com',
];

/**
 * Validates if an email is from a company domain (not a personal email provider)
 * @param email - The email address to validate
 * @returns Object with isValid boolean and error message if invalid
 */
export const validateCompanyEmail = (email: string): { isValid: boolean; error?: string } => {
  if (!email || !email.includes('@')) {
    return { isValid: false, error: 'Please enter a valid email address' };
  }

  const emailLower = email.toLowerCase().trim();
  const domain = emailLower.split('@')[1];

  if (!domain) {
    return { isValid: false, error: 'Please enter a valid email address' };
  }

  // Check if it's a personal email provider
  if (PERSONAL_EMAIL_PROVIDERS.includes(domain)) {
    return {
      isValid: false,
      error: 'Please use your company email address. Personal email addresses (Gmail, Yahoo, etc.) are not accepted.',
    };
  }

  // Additional check: block common free email patterns
  const freeEmailPatterns = [
    /^mail\d*\./,
    /^email\d*\./,
    /^temp\d*\./,
    /^test\d*\./,
  ];

  for (const pattern of freeEmailPatterns) {
    if (pattern.test(domain)) {
      return {
        isValid: false,
        error: 'Please use your company email address. Free email services are not accepted.',
      };
    }
  }

  return { isValid: true };
};

/**
 * Checks if an email domain is likely a company domain
 * @param domain - The email domain to check
 * @returns boolean indicating if it's likely a company domain
 */
export const isCompanyDomain = (domain: string): boolean => {
  const domainLower = domain.toLowerCase();
  
  // If it's not in the personal providers list, assume it's a company domain
  return !PERSONAL_EMAIL_PROVIDERS.includes(domainLower);
};

