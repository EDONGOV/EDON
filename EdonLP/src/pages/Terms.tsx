import { Link } from 'react-router-dom'
import { Shield } from 'lucide-react'

export default function Terms() {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 h-[400px] w-[400px] rounded-full bg-primary/5 blur-[100px]" />
      </div>

      <header className="relative border-b border-border/50 py-4 px-6">
        <Link to="/" className="flex items-center gap-2 w-fit">
          <div className="h-7 w-7 rounded-lg bg-primary flex items-center justify-center glow-primary-sm">
            <Shield className="h-4 w-4 text-primary-foreground" />
          </div>
          <span className="font-space text-[15px] font-semibold tracking-tight">EDON</span>
        </Link>
      </header>

      <main className="relative flex-1 px-4 py-16">
        <div className="max-w-2xl mx-auto">
          <p className="text-xs font-semibold uppercase tracking-widest text-primary mb-3">Legal</p>
          <h1 className="font-space text-3xl font-bold tracking-tight mb-2">Terms of Service</h1>
          <p className="text-sm text-muted-foreground mb-10">Last updated: April 2026</p>

          <div className="space-y-8 text-sm text-muted-foreground leading-relaxed">
            <Section title="1. Acceptance of terms">
              By accessing or using EDON ("the Service"), you agree to be bound by these Terms of Service. If you do not agree, do not use the Service.
            </Section>
            <Section title="2. Use of the service">
              You may use the Service only for lawful purposes and in accordance with these Terms. You are responsible for all activity that occurs under your account.
            </Section>
            <Section title="3. Accounts">
              You must provide accurate information when creating an account. You are responsible for maintaining the confidentiality of your API key and credentials. Notify us immediately of any unauthorised access.
            </Section>
            <Section title="4. Fees and payment">
              Paid plans are billed in advance on a monthly or annual basis. All fees are non-refundable except where required by law. We reserve the right to change pricing with 30 days' notice.
            </Section>
            <Section title="5. Intellectual property">
              EDON and its original content, features, and functionality are owned by EDON and are protected by applicable intellectual property laws. You retain ownership of any data you submit.
            </Section>
            <Section title="6. Limitation of liability">
              To the maximum extent permitted by law, EDON shall not be liable for any indirect, incidental, special, consequential, or punitive damages arising out of your use of the Service.
            </Section>
            <Section title="7. Termination">
              We may suspend or terminate your access at any time for breach of these Terms. You may cancel your account at any time from the billing portal.
            </Section>
            <Section title="8. Governing law">
              These Terms are governed by the laws of the United States. Any disputes shall be resolved in the courts of competent jurisdiction.
            </Section>
            <Section title="9. Contact">
              Questions? Email{' '}
              <a href="mailto:hello@edoncore.com" className="text-primary hover:underline">hello@edoncore.com</a>.
            </Section>
          </div>
        </div>
      </main>

      <footer className="relative border-t border-border/50 py-6 px-6">
        <div className="max-w-2xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground/50">© {new Date().getFullYear()} EDON. All rights reserved.</span>
          <div className="flex items-center gap-4 text-xs text-muted-foreground/60">
            <Link to="/privacy" className="hover:text-foreground transition-colors">Privacy</Link>
            <Link to="/contact" className="hover:text-foreground transition-colors">Contact</Link>
          </div>
        </div>
      </footer>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="font-space text-base font-semibold text-foreground mb-2">{title}</h2>
      <p>{children}</p>
    </div>
  )
}
