# MASTER SERVICE AGREEMENT

**Agreement Date:** _______________

This Master Service Agreement ("Agreement") is entered into between **EDON Technologies, Inc.**, a Delaware corporation ("EDON" or "Provider"), and the entity identified in the Order Form ("Customer").

---

## 1. SERVICES

### 1.1 Scope
EDON will provide the AI governance and runtime policy enforcement services ("Services") described in one or more Order Forms executed by the Parties. Each Order Form is incorporated into and governed by this Agreement.

### 1.2 Service Description
The EDON platform provides:
- **Runtime governance** — Intercepts and evaluates AI agent actions against customer-defined policies before execution
- **Audit logging** — Append-only, tamper-evident record of every agent decision with cryptographic hashing
- **Policy management** — Configurable policy packs and custom rules defining permitted agent behaviors
- **Human review queue** — Escalation workflow for high-risk actions requiring human approval
- **Analytics and alerting** — Agent behavioral monitoring, anomaly detection, and real-time alerts

### 1.3 Delivery
Services are delivered via:
- Cloud-hosted SaaS at `api.edoncore.com` (standard)
- On-premise or private cloud deployment (Enterprise plans only, as specified in Order Form)

### 1.4 Implementation
EDON will provide integration documentation and reasonable technical support for initial implementation. Standard implementation is expected to require 1–3 engineering days on Customer's side. Managed implementation services are available as a separate Order Form item.

---

## 2. CUSTOMER OBLIGATIONS

### 2.1 Account Responsibility
Customer is responsible for:
- All activity under Customer's account
- Maintaining the confidentiality of API keys and credentials
- Notifying EDON promptly of any unauthorized access or security incident

### 2.2 Acceptable Use
Customer shall not:
- Use the Services to process data in violation of applicable law
- Attempt to reverse engineer, decompile, or extract EDON's algorithms or models
- Resell or sublicense the Services without EDON's written consent
- Use the Services to benchmark or build a competing product

### 2.3 Data Accuracy
Customer is responsible for ensuring that agent policies and configurations are appropriate for Customer's use case and regulatory environment. EDON provides a governance infrastructure layer; Customer retains responsibility for the design and behavior of its agents.

---

## 3. FEES AND PAYMENT

### 3.1 Fees
Customer shall pay the fees set forth in the applicable Order Form. All fees are in U.S. dollars unless otherwise specified.

### 3.2 Invoicing and Payment
- **Monthly plans**: Invoiced monthly in advance; due within **15 days** of invoice
- **Annual plans**: Invoiced annually in advance; due within **30 days** of invoice
- **Enterprise/custom plans**: As specified in the Order Form

### 3.3 Overages
Usage above the included monthly decision volume will be billed at the overage rate specified in the Order Form, invoiced monthly in arrears.

### 3.4 Late Payment
Undisputed invoices not paid within the due date accrue interest at **1.5% per month** (or the maximum rate permitted by law, whichever is less). EDON may suspend Services after **15 days** written notice of non-payment.

### 3.5 Taxes
Fees exclude all applicable taxes. Customer is responsible for all taxes, levies, or duties imposed by taxing authorities, excluding taxes based on EDON's net income.

### 3.6 Disputes
Customer must notify EDON of any disputed invoice within **10 days** of receipt. The Parties will work in good faith to resolve billing disputes within **30 days**.

---

## 4. SERVICE LEVEL AGREEMENT

### 4.1 Uptime Commitment
EDON commits to the following monthly uptime for the core governance API:

| Plan | Uptime SLA |
|------|-----------|
| Hobby | No SLA |
| Pro | No SLA |
| Team | 99.9% (~8.7 hrs/mo downtime) |
| Business | 99.95% (~4.4 hrs/mo downtime) |
| Enterprise | 99.99% (~4.4 min/mo downtime) or as negotiated |

### 4.2 Uptime Calculation
Uptime = (Total minutes in month – Downtime minutes) / Total minutes in month × 100

Scheduled maintenance with **72 hours** advance notice is excluded from downtime calculations.

### 4.3 Service Credits
If EDON fails to meet the applicable SLA in a given calendar month, Customer is eligible for service credits:

| Monthly Uptime | Credit |
|----------------|--------|
| 99.0% – SLA threshold | 10% of monthly fee |
| 95.0% – 99.0% | 25% of monthly fee |
| Below 95.0% | 50% of monthly fee |

Credits are Customer's sole remedy for SLA failures and must be requested within **30 days** of the month in which the failure occurred. Credits apply to future invoices and are not refundable as cash.

### 4.4 Support Response Times

| Plan | Severity 1 (Service down) | Severity 2 (Degraded) | Severity 3 (General) |
|------|--------------------------|----------------------|---------------------|
| Pro | 8 business hours | Next business day | 48 hours |
| Team | 4 business hours | 8 business hours | 24 hours |
| Business | 1 hour (Slack) | 4 hours | 8 hours |
| Enterprise | 30 min (dedicated) | 2 hours | Next business day |

---

## 5. DATA AND PRIVACY

### 5.1 Data Ownership
Customer retains all right, title, and interest in Customer Data. EDON acquires no ownership rights in Customer Data.

### 5.2 Data Processing
EDON processes Customer Data solely to provide and improve the Services, as described in EDON's Privacy Policy and, where applicable, a Data Processing Addendum or BAA.

### 5.3 Data Security
EDON implements and maintains industry-standard security measures including encryption at rest (AES-256) and in transit (TLS 1.2+), access controls, and regular security assessments. Details are set forth in EDON's Security Documentation.

### 5.4 Data Retention
- **Audit logs**: Retained per the Customer's plan (7 days to 365 days for standard plans; custom retention for Enterprise)
- **Agent configurations**: Retained for the duration of the Agreement and 30 days post-termination
- Upon termination, Customer may export its data within **30 days**. After 30 days, EDON will delete Customer Data from production systems within **60 days**

### 5.5 HIPAA
If Customer is a Covered Entity or Business Associate under HIPAA, the Parties shall execute a Business Associate Agreement ("BAA") prior to Customer transmitting any Protected Health Information to EDON.

### 5.6 Sub-processors
EDON uses the following categories of sub-processors: cloud infrastructure providers, database hosting, and email delivery. A current list is available at edoncore.com/sub-processors and will be updated with **30 days** advance notice of material changes.

---

## 6. INTELLECTUAL PROPERTY

### 6.1 EDON IP
EDON retains all right, title, and interest in the Services, platform, algorithms, software, and all improvements thereto. Nothing in this Agreement transfers any EDON IP to Customer.

### 6.2 Customer IP
Customer retains all right, title, and interest in Customer's agents, models, policies, and data. Nothing in this Agreement transfers any Customer IP to EDON.

### 6.3 Feedback
If Customer provides feedback or suggestions regarding the Services, EDON may use such feedback without restriction or obligation to Customer.

### 6.4 Aggregated Data
EDON may use anonymized, aggregated data derived from use of the Services (with no personally identifiable information) for benchmarking, product development, and industry reporting.

---

## 7. CONFIDENTIALITY

### 7.1 Definition
"Confidential Information" means any non-public information disclosed by one Party to the other that is designated as confidential or that reasonably should be understood to be confidential given the nature of the information.

### 7.2 Obligations
Each Party shall: (a) hold the other's Confidential Information in strict confidence; (b) use Confidential Information only in connection with this Agreement; (c) disclose Confidential Information only to employees and contractors with a need to know who are bound by confidentiality obligations at least as protective as this Agreement.

### 7.3 Exceptions
Confidentiality obligations do not apply to information that: (a) is or becomes publicly known without breach; (b) was known to the receiving Party before disclosure; (c) is received from a third party without restriction; (d) is required to be disclosed by law or court order (with prompt written notice to the disclosing Party where legally permitted).

### 7.4 Term
Confidentiality obligations survive termination of this Agreement for **3 years**, except for trade secrets which are protected indefinitely.

---

## 8. WARRANTIES AND DISCLAIMERS

### 8.1 EDON Warranties
EDON warrants that: (a) it has the right to enter into this Agreement; (b) the Services will perform materially in accordance with the documentation; (c) EDON will use commercially reasonable efforts to maintain the security of the Services.

### 8.2 Customer Warranties
Customer warrants that: (a) it has the right to enter into this Agreement; (b) it has all necessary rights and consents to provide Customer Data to EDON; (c) its use of the Services will comply with applicable law.

### 8.3 Disclaimer
EXCEPT AS EXPRESSLY SET FORTH HEREIN, THE SERVICES ARE PROVIDED "AS IS." EDON DISCLAIMS ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT. EDON DOES NOT WARRANT THAT THE SERVICES WILL BE UNINTERRUPTED OR ERROR-FREE.

---

## 9. LIMITATION OF LIABILITY

### 9.1 Exclusion of Consequential Damages
NEITHER PARTY SHALL BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING LOST PROFITS, LOSS OF DATA, OR BUSINESS INTERRUPTION, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

### 9.2 Cap on Liability
EACH PARTY'S TOTAL CUMULATIVE LIABILITY ARISING OUT OF OR RELATED TO THIS AGREEMENT SHALL NOT EXCEED THE FEES PAID OR PAYABLE BY CUSTOMER IN THE **12 MONTHS** PRECEDING THE CLAIM.

### 9.3 Exceptions
The limitations in 9.1 and 9.2 do not apply to: (a) either Party's indemnification obligations; (b) damages arising from gross negligence or willful misconduct; (c) Customer's payment obligations; (d) breaches of Section 7 (Confidentiality).

---

## 10. INDEMNIFICATION

### 10.1 By EDON
EDON shall defend and indemnify Customer against third-party claims alleging that the Services, as provided and used in accordance with this Agreement, infringe a third party's intellectual property rights.

### 10.2 By Customer
Customer shall defend and indemnify EDON against third-party claims arising from: (a) Customer Data; (b) Customer's use of the Services in violation of this Agreement or applicable law; (c) Customer's agents or AI systems.

### 10.3 Procedure
The indemnified party must: (a) promptly notify the indemnifying party of the claim; (b) grant the indemnifying party sole control of the defense; (c) provide reasonable cooperation. The indemnifying party may not settle any claim that imposes obligations on the indemnified party without prior written consent.

---

## 11. TERM AND TERMINATION

### 11.1 Term
This Agreement begins on the Agreement Date and continues until all Order Forms have expired or been terminated.

### 11.2 Termination for Convenience
Either Party may terminate this Agreement or any Order Form upon **30 days' written notice**, subject to the minimum term specified in the Order Form.

### 11.3 Termination for Cause
Either Party may terminate immediately upon written notice if the other Party: (a) materially breaches this Agreement and fails to cure within **30 days** of written notice; (b) becomes insolvent or files for bankruptcy; (c) ceases to do business.

### 11.4 Effect of Termination
Upon termination: (a) Customer's access to the Services will be disabled; (b) Customer must cease all use of the Services; (c) each Party will return or destroy the other's Confidential Information upon request; (d) Sections 3, 5.4, 6, 7, 8.3, 9, 10, and 12 survive termination.

### 11.5 No Refunds
Fees paid are non-refundable except: (a) where EDON terminates for convenience before the end of a prepaid annual term (pro-rata refund); (b) as required by applicable law.

---

## 12. GENERAL

### 12.1 Governing Law
This Agreement is governed by the laws of the State of Delaware without regard to its conflict of law provisions. Any dispute shall be resolved exclusively in the state or federal courts located in Delaware, and each Party consents to personal jurisdiction therein.

### 12.2 Dispute Resolution
Before initiating litigation, the Parties shall attempt to resolve any dispute through good-faith negotiations for **30 days**. For Enterprise contracts, disputes over $50,000 shall be submitted to binding arbitration under JAMS rules before litigation.

### 12.3 Force Majeure
Neither Party is liable for delays or failures caused by events outside its reasonable control, including natural disasters, government actions, pandemics, or internet outages, provided the affected Party gives prompt notice and uses reasonable efforts to mitigate.

### 12.4 Assignment
Customer may not assign this Agreement without EDON's prior written consent, which shall not be unreasonably withheld. EDON may assign this Agreement in connection with a merger, acquisition, or sale of substantially all of its assets. Any assignment in violation of this section is void.

### 12.5 Amendments
This Agreement may be amended only by a written instrument signed by authorized representatives of both Parties.

### 12.6 Entire Agreement
This Agreement, including all Order Forms and addenda, constitutes the entire agreement between the Parties regarding its subject matter and supersedes all prior agreements, proposals, and understandings.

### 12.7 Severability
If any provision is found unenforceable, it will be modified to the minimum extent necessary to make it enforceable, and the remaining provisions will continue in full force.

### 12.8 No Waiver
Failure to enforce any provision does not waive the right to enforce it later.

### 12.9 Notices
Notices must be in writing and delivered by email (with delivery confirmation) or overnight courier to the addresses in the Order Form.

### 12.10 Counterparts
This Agreement may be signed in counterparts, including electronically, each of which shall be an original.

---

# ORDER FORM

**Order Form Number:** _______________
**Order Form Date:** _______________
**Effective Date of Service:** _______________

This Order Form is incorporated into the Master Service Agreement between EDON Technologies, Inc. and Customer.

---

## CUSTOMER INFORMATION

| Field | Details |
|-------|---------|
| Company Legal Name | |
| Registered Address | |
| Billing Address | |
| Billing Contact Name | |
| Billing Email | |
| Technical Contact Name | |
| Technical Contact Email | |
| Authorized Signatory Name | |
| Authorized Signatory Title | |

---

## SERVICE PLAN

| Item | Detail |
|------|--------|
| Plan | ☐ Pro  ☐ Team  ☐ Business  ☐ Enterprise |
| Deployment | ☐ Cloud (SaaS)  ☐ On-Premise  ☐ Private Cloud |
| Region | ☐ US East  ☐ US West  ☐ EU  ☐ Custom |
| Term | ☐ Monthly  ☐ Annual  ☐ Multi-year: _______ |
| Start Date | |
| Renewal | Auto-renews unless cancelled 30 days prior |

---

## FEES

| Line Item | Qty | Unit Price | Total |
|-----------|-----|-----------|-------|
| Base platform fee (monthly) | 1 | $ | $ |
| Included decisions / mo | — | Included | — |
| Overage rate (per 1K decisions over) | — | $ | — |
| On-premise deployment fee (one-time) | | $ | $ |
| Professional implementation services | ___ hrs | $250/hr | $ |
| Additional workspaces | | $ | $ |
| **Annual Total** | | | **$** |

**Payment Terms:** ☐ Net 15  ☐ Net 30  ☐ Net 45

**Billing Frequency:** ☐ Monthly  ☐ Annual (upfront)

---

## COMPLIANCE ADDENDA

The following addenda are incorporated into this Order Form:

| Addendum | Applicable |
|----------|-----------|
| Business Associate Agreement (BAA) | ☐ Yes  ☐ No |
| Data Processing Addendum (GDPR) | ☐ Yes  ☐ No |
| Security Addendum | ☐ Yes  ☐ No |
| Custom SLA | ☐ Yes — see Exhibit A |

---

## ENTERPRISE TERMS (if applicable)

| Item | Detail |
|------|--------|
| Dedicated account manager | ☐ Yes  ☐ No |
| Custom data retention (years) | |
| Custom data residency region | |
| Pen test report provided | ☐ Yes  ☐ No |
| Quarterly business review | ☐ Yes  ☐ No |
| Source code escrow | ☐ Yes  ☐ No |

---

## SIGNATURES

By signing below, the Parties agree to be bound by this Order Form and the Master Service Agreement.

**CUSTOMER**

Signature: ___________________________

Printed Name: ___________________________

Title: ___________________________

Date: ___________________________

---

**EDON Technologies, Inc.**

Signature: ___________________________

Printed Name: ___________________________

Title: ___________________________

Date: ___________________________

---

*Send executed Order Forms to: contracts@edoncore.com*
