# Stripe Payment Links – Redirect After Payment

You **cannot** add a back arrow or custom UI on Stripe’s hosted checkout page. You **can** control where customers go after they pay or cancel.

## Redirect customers after payment

1. Open **[Stripe Dashboard](https://dashboard.stripe.com)** → **Payment Links**.
2. Open the **Pro $25** link (`.../00w7sK5a0b5077YgXSfIs02`) and the **Pro+ $60** link (`.../00w8wO1XO5KGboegXSfIs03`).
3. For each link, click **Customize** (or **…** → **Update details**).
4. Under **After payment**:
   - Choose **Redirect to a URL**.
   - Set the URL to one of:
     - **Thank-you page (recommended):**  
       `https://edoncore.com/thank-you`  
       (Shows “Thank you for your payment” and a “Return to home” button.)
     - **Home:**  
       `https://edoncore.com`
     - **Account:**  
       `https://edoncore.com/account`
5. Under **When payment is cancelled** (if available):
   - Set to `https://edoncore.com/pricing` or `https://edoncore.com`.
6. Save the Payment Link.

After you set these, customers will leave Stripe Checkout and land on your site (thank-you page or home) instead of Stripe’s default confirmation page.
