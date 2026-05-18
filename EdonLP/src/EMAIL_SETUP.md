# Email Setup Instructions

## ✅ Current Implementation

The email system is now fully configured with **Resend API**!

### What Happens When Forms Are Submitted:

1. **Notification Email to Charlie**: All form submissions are sent to `charlie@edoncore.com` with the form data
2. **Auto-Reply to User**: Users automatically receive a professional auto-reply email:
   - **OEM Access requests**: Receive an auto-reply with next steps and calendar booking link
   - **Evaluation Bundle requests**: Receive an auto-reply with onboarding information

### Email Templates:

- **OEM Access Auto-Reply**: Includes calendar link (https://cal.com/charliebiggins) and explains the review process
- **Evaluation Bundle Auto-Reply**: Includes calendar link and explains the gated access process

## Environment Variables

The Resend API key is configured. To update it:

1. Go to your Vercel project settings
2. Navigate to Environment Variables
3. Add or update `RESEND_API_KEY` with your Resend API key

**Note**: The API key is currently hardcoded as a fallback in the serverless function. For production, it's recommended to use environment variables only.

## Testing

Test the forms:
- **OEM Apply form**: `/oem/apply` - Sends notification + auto-reply
- **Download form**: `/download` - Sends notification + auto-reply  
- **Contact form**: `/contact` - Sends notification only

## Email Flow

1. User submits form → Form data sent to `/api/send-email`
2. Serverless function sends:
   - Notification email to `charlie@edoncore.com` (with form data)
   - Auto-reply email to user (with next steps and calendar link)
3. User receives confirmation email automatically
4. Charlie receives notification with all form details

## Troubleshooting

If emails aren't sending:
1. Check Vercel function logs for errors
2. Verify `RESEND_API_KEY` is set in Vercel environment variables
3. Check Resend dashboard for delivery status
4. Ensure the "from" domain is verified in Resend (noreply@edoncore.com)

