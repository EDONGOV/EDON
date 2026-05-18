/**
 * EDON JS SDK — basic governed agent example
 *
 * Run:
 *   EDON_API_KEY=edon-... node sdk/examples/basic_agent.mjs
 */
import { EdonClient } from '@edon/sdk'

const client = new EdonClient({
  token: process.env.EDON_API_KEY ?? 'dev-token',
  baseUrl: process.env.EDON_GATEWAY_URL ?? 'https://edon-gateway-prod.fly.dev',
  agentId: 'example-agent-js',
})

// Step 0: Check gateway
const health = await client.health()
console.log('Gateway status:', health.status ?? 'unknown')

// Step 1: Declare intent upfront
const intentId = await client.beginIntent({
  objective: 'Query patient database and email daily summary to care team',
  allowedTools: ['database.query', 'email.send'],
  riskCeiling: 'MEDIUM',
})
console.log('Intent registered:', intentId)

// Step 2: Govern the action before executing
const result = await client.evaluate({
  actionType: 'database.query',
  payload: { table: 'patients', filter: { ward: 'cardiology' }, limit: 10 },
  statedIntent: 'fetch today\'s cardiology patients for daily summary',
})

console.log('\nVerdict:   ', result.verdict)
console.log('Reason:    ', result.reasonCode || 'N/A')

if (result.verdict === 'ALLOW') {
  // Simulate tool execution
  const rawDbResponse = {
    rows: [
      { patient_id: 'P001', name: 'John Doe', ward: 'cardiology' },
      { patient_id: 'P002', name: 'Jane Smith', ward: 'cardiology' },
    ],
    count: 2,
  }

  // Step 3: Scan the response before using it
  const output = await client.scanOutput({
    response: rawDbResponse,
    actionType: 'database.query',
    actionId: result.actionId,
  })

  if (output.verdict === 'PASS') {
    console.log(`\nOutput clean — ${output.payload.rows.length} rows safe to use`)
  } else if (output.verdict === 'REDACT') {
    console.log(`\nOutput redacted — ${output.findings.length} findings. Using cleaned payload.`)
  } else {
    console.log('\nOutput BLOCKED — cannot use this response:', output.findings)
  }
} else if (result.verdict === 'BLOCK') {
  console.log('Action blocked:', result.explanation)
} else if (result.verdict === 'ESCALATE') {
  console.log('Human review required:', result.escalationQuestion)
} else if (result.verdict === 'DEGRADE') {
  console.log('Using safe alternative:', result.safeAlternative)
}

// Step 4: End intent at close of session
client.endIntent()
