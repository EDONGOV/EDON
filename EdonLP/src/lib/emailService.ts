/**
 * Email service utility to send form submissions to charlie@edoncore.com
 * 
 * This uses a simple mailto approach that opens the user's email client.
 * For production, you may want to integrate with:
 * - EmailJS (client-side)
 * - A serverless function (Vercel, Netlify)
 * - A backend API endpoint
 */

import { fetchWithTimeout } from "@/lib/fetcher";

export interface EmailData {
  to: string;
  subject: string;
  body: string;
}

type FormDataMap = Record<string, string | number | boolean | null | undefined>;

/**
 * Sends an email using mailto protocol (opens default email client)
 * For production, replace this with an actual email service
 */
export const sendEmail = async (data: EmailData): Promise<boolean> => {
  try {
    const mailtoLink = `mailto:${data.to}?subject=${encodeURIComponent(data.subject)}&body=${encodeURIComponent(data.body)}`;
    window.location.href = mailtoLink;
    return true;
  } catch (error) {
    if (import.meta.env.DEV) {
      console.error('Error sending email:', error);
    }
    return false;
  }
};

/**
 * Sends form submission via fetch to a serverless function or API endpoint
 * This is the preferred method for production
 */
export const sendFormSubmission = async (
  formType: 'oem' | 'download' | 'contact',
  formData: FormDataMap
): Promise<boolean> => {
  try {
    // Format email content
    const emailContent = formatEmailContent(formType, formData);
    
    // Try to send via API endpoint first (if available)
    // For Vercel deployments, this will be /api/send-email
    // You can also set VITE_EMAIL_API_ENDPOINT in your .env file
    const apiEndpoint = import.meta.env.VITE_EMAIL_API_ENDPOINT || '/api/send-email';
    
    try {
      // Get user email from form data for auto-reply
      const userEmail = formType === 'oem' 
        ? formData.workEmail 
        : formType === 'download' 
        ? formData.email 
        : formData.email;

      const response = await fetchWithTimeout(apiEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          to: 'charlie@edoncore.com',
          subject: emailContent.subject,
          body: emailContent.body,
          formType,
          userEmail: userEmail || null,
          formData,
        }),
        timeoutMs: 10000,
        retries: 2,
      });
      
      if (response.ok) {
        return true;
      } else {
        if (import.meta.env.DEV) {
          console.warn('API endpoint returned error, falling back to mailto');
        }
      }
    } catch (apiError) {
      if (import.meta.env.DEV) {
        console.warn('API endpoint not available, falling back to mailto:', apiError);
      }
    }
    
    // Fallback to mailto if API is not available
    // This opens the user's email client with pre-filled content
    return await sendEmail({
      to: 'charlie@edoncore.com',
      subject: emailContent.subject,
      body: emailContent.body,
    });
  } catch (error) {
    if (import.meta.env.DEV) {
      console.error('Error sending form submission:', error);
    }
    // Final fallback to mailto
    const emailContent = formatEmailContent(formType, formData);
    return await sendEmail({
      to: 'charlie@edoncore.com',
      subject: emailContent.subject,
      body: emailContent.body,
    });
  }
};

/**
 * Formats email content based on form type
 */
const formatEmailContent = (
  formType: 'oem' | 'download' | 'contact',
  formData: FormDataMap
): { subject: string; body: string } => {
  let subject = '';
  let body = '';

  switch (formType) {
    case 'oem':
      subject = `New OEM Access Request - ${formData.companyName || 'Unknown Company'}`;
      body = `New OEM Access Request Received

Company: ${formData.companyName || 'N/A'}
Role: ${formData.role || 'N/A'}
Use Case: ${formData.useCase || 'N/A'}
Deployment Timeline: ${formData.deploymentTimeline || 'N/A'}
Region: ${formData.region || 'N/A'}
Work Email: ${formData.workEmail || 'N/A'}
Terms Accepted: ${formData.termsAccepted ? 'Yes' : 'No'}

Submitted: ${new Date().toLocaleString()}
`;
      break;

    case 'download':
      subject = `New Download Request - ${formData.company || 'Unknown Company'}`;
      body = `New Download Request Received

Email: ${formData.email || 'N/A'}
Company: ${formData.company || 'N/A'}
Region: ${formData.region || 'N/A'}
Device Type: ${formData.deviceType || 'N/A'}
License Accepted: ${formData.licenseAccepted ? 'Yes' : 'No'}

Submitted: ${new Date().toLocaleString()}
`;
      break;

    case 'contact':
      subject = `New Contact Request - ${formData.inquiryType || 'General Inquiry'}`;
      body = `New Contact Request Received

Name: ${formData.name || 'N/A'}
Email: ${formData.email || 'N/A'}
Organization: ${formData.organization || 'N/A'}
Inquiry Type: ${formData.inquiryType || 'N/A'}
Message:
${formData.message || 'N/A'}

Submitted: ${new Date().toLocaleString()}
`;
      break;
  }

  return { subject, body };
};

