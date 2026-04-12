# BUSINESS ASSOCIATE AGREEMENT

**Effective Date:** _______________

This Business Associate Agreement ("BAA") is entered into between **EDON Technologies, Inc.** ("Business Associate") and **[COVERED ENTITY NAME]** ("Covered Entity"), collectively referred to as the "Parties."

This BAA supplements and is incorporated into the Master Service Agreement or Order Form between the Parties (the "Underlying Agreement").

---

## 1. DEFINITIONS

Terms used but not defined in this BAA have the meanings given in the HIPAA Rules (45 C.F.R. Parts 160 and 164).

**"Business Associate"** means EDON Technologies, Inc., which provides AI governance, audit logging, and policy enforcement services to Covered Entity.

**"Covered Entity"** means the healthcare organization identified above that is subject to the HIPAA Privacy Rule and Security Rule.

**"Protected Health Information" (PHI)** means individually identifiable health information that is created, received, maintained, or transmitted by Business Associate on behalf of Covered Entity, in any form or media.

**"Electronic PHI" (ePHI)** means PHI that is created, received, maintained, or transmitted in electronic form.

**"HIPAA Rules"** means the Privacy, Security, Breach Notification, and Enforcement Rules promulgated under HIPAA and HITECH, as amended.

**"Services"** means the AI agent governance and audit logging services described in the Underlying Agreement.

---

## 2. OBLIGATIONS OF BUSINESS ASSOCIATE

### 2.1 Permitted Uses and Disclosures
Business Associate may use or disclose PHI only:
- As necessary to perform the Services described in the Underlying Agreement
- As required by law
- As permitted under this BAA or directed in writing by Covered Entity
- For Business Associate's proper management and administration, provided such use is necessary or required by law

Business Associate shall not use or disclose PHI in a manner that would violate the HIPAA Privacy Rule if done by Covered Entity, except as permitted under this BAA.

### 2.2 Safeguards
Business Associate shall:
- Implement and maintain appropriate administrative, physical, and technical safeguards to protect the confidentiality, integrity, and availability of ePHI in accordance with 45 C.F.R. Part 164, Subpart C (the Security Rule)
- Encrypt all ePHI at rest (AES-256) and in transit (TLS 1.2+)
- Implement access controls limiting PHI access to authorized personnel only
- Maintain audit logs of all access to ePHI
- Apply data masking to PHI fields in audit logs where configured by Covered Entity

### 2.3 Reporting
Business Associate shall report to Covered Entity, without unreasonable delay and no later than **60 days** after discovery:
- Any use or disclosure of PHI not permitted by this BAA
- Any Security Incident (as defined in 45 C.F.R. § 164.304)
- Any Breach of Unsecured PHI (as defined in 45 C.F.R. § 164.402), including information required under 45 C.F.R. § 164.410

### 2.4 Subcontractors
Business Associate shall ensure that any subcontractor that creates, receives, maintains, or transmits PHI on behalf of Business Associate agrees to the same restrictions, conditions, and requirements that apply to Business Associate under this BAA. Business Associate shall obtain a written agreement from each such subcontractor prior to disclosing PHI.

Current subprocessors that may handle ePHI:
- **Supabase** (database hosting) — U.S. region, SOC 2 Type II certified
- **Fly.io** (compute infrastructure) — U.S. region

### 2.5 Access to PHI
Business Associate shall make PHI available to Covered Entity as necessary for Covered Entity to fulfill its obligations under 45 C.F.R. § 164.524 (individual right of access).

### 2.6 Amendment of PHI
Business Associate shall make PHI available for amendment and incorporate any amendments to PHI as directed by Covered Entity in accordance with 45 C.F.R. § 164.526.

### 2.7 Accounting of Disclosures
Business Associate shall maintain and make available to Covered Entity information required for an accounting of disclosures in accordance with 45 C.F.R. § 164.528. Business Associate shall provide such information within **30 days** of a request.

### 2.8 Access to Books and Records
Business Associate shall make its internal practices, books, and records relating to the use and disclosure of PHI available to the Secretary of the U.S. Department of Health and Human Services for purposes of determining Covered Entity's compliance with the HIPAA Rules.

### 2.9 Minimum Necessary
Business Associate shall, to the extent practicable, use, disclose, and request only the minimum amount of PHI necessary to accomplish the intended purpose of the use, disclosure, or request.

---

## 3. OBLIGATIONS OF COVERED ENTITY

### 3.1 Notice of Privacy Practices
Covered Entity shall notify Business Associate of any limitation in its Notice of Privacy Practices that would affect Business Associate's use or disclosure of PHI.

### 3.2 Permissions
Covered Entity shall notify Business Associate of any changes in, or revocation of, the permission by individuals to use or disclose PHI, to the extent that such changes affect Business Associate's permitted uses or disclosures.

### 3.3 Restrictions
Covered Entity shall notify Business Associate of any restrictions agreed to by Covered Entity on the use or disclosure of PHI that would affect Business Associate's use or disclosure.

### 3.4 Lawful Requests
Covered Entity shall not request that Business Associate use or disclose PHI in any manner that would not be permissible under the HIPAA Privacy Rule if done by Covered Entity.

---

## 4. PERMITTED USES BY BUSINESS ASSOCIATE

Business Associate may use PHI for the following purposes:
- To provide the Services under the Underlying Agreement
- For data aggregation services relating to the healthcare operations of Covered Entity
- For Business Associate's proper management and administration
- To carry out Business Associate's legal responsibilities

Business Associate may use de-identified data (as defined under 45 C.F.R. § 164.514) derived from PHI for product improvement and analytics, provided such data cannot reasonably be used to identify an individual.

---

## 5. TERM AND TERMINATION

### 5.1 Term
This BAA is effective as of the Effective Date and shall continue until the Underlying Agreement is terminated or expires, or until terminated as provided herein.

### 5.2 Termination for Cause
Either Party may terminate this BAA and the Underlying Agreement upon **30 days' written notice** if the other Party materially breaches this BAA and fails to cure such breach within the notice period.

If cure is not possible, the non-breaching Party may immediately terminate this BAA.

### 5.3 Effect of Termination
Upon termination of this BAA for any reason:
- Business Associate shall return or destroy all PHI received from, or created or received on behalf of, Covered Entity that Business Associate still maintains, within **30 days**
- If return or destruction is not feasible, Business Associate shall extend the protections of this BAA to such PHI and limit further uses and disclosures to the purposes that make return or destruction infeasible
- Business Associate shall certify in writing to Covered Entity that all PHI has been returned or destroyed

---

## 6. BREACH NOTIFICATION PROCEDURES

In the event of a Breach or suspected Breach:

1. Business Associate will notify Covered Entity's designated privacy contact within **10 business days** of discovery
2. Notice will include, to the extent known: identity of individuals affected, description of what occurred, types of PHI involved, steps taken to mitigate harm, and corrective actions implemented
3. Business Associate will cooperate fully with Covered Entity's breach investigation and required notifications to affected individuals and regulators
4. Business Associate maintains cyber liability insurance with minimum limits of **$2,000,000** per occurrence

---

## 7. SECURITY STANDARDS

Business Associate certifies and shall maintain the following security measures for the term of this BAA:

| Safeguard | Standard |
|-----------|----------|
| Encryption at rest | AES-256 |
| Encryption in transit | TLS 1.2 or higher |
| Authentication | MFA required for all internal access to PHI |
| Access control | Role-based access; least privilege principle |
| Audit logging | All access to ePHI logged with timestamp, user, and action |
| Vulnerability management | Quarterly security assessments; annual penetration test |
| Incident response | Written incident response plan; tested annually |
| Employee training | Annual HIPAA training for all personnel with PHI access |
| Background checks | Required for all employees with PHI access |

---

## 8. MISCELLANEOUS

### 8.1 Amendments
This BAA may be amended by mutual written agreement. Business Associate may amend this BAA to comply with changes in the HIPAA Rules upon **30 days' notice** to Covered Entity.

### 8.2 Survival
The obligations of Business Associate under Section 5.3 (Effect of Termination) shall survive the termination of this BAA.

### 8.3 Interpretation
This BAA shall be interpreted as broadly as necessary to implement and comply with the HIPAA Rules. Any ambiguity shall be resolved in favor of meaning that best effectuates compliance.

### 8.4 No Third-Party Beneficiaries
Nothing in this BAA shall be construed to create any rights in any third party.

### 8.5 Entire Agreement
This BAA, together with the Underlying Agreement, constitutes the entire agreement between the Parties regarding the subject matter hereof and supersedes all prior agreements and understandings relating to the same.

### 8.6 Governing Law
This BAA shall be governed by the laws of the State of Delaware, without regard to conflicts of law principles.

---

## 9. SIGNATURES

**COVERED ENTITY**

Signature: ___________________________

Printed Name: ___________________________

Title: ___________________________

Organization: ___________________________

Date: ___________________________

---

**BUSINESS ASSOCIATE — EDON Technologies, Inc.**

Signature: ___________________________

Printed Name: ___________________________

Title: ___________________________

Date: ___________________________

---

*For questions regarding this BAA, contact: privacy@edoncore.com*
