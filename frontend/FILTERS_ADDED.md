# Filters Added to Decisions and Audit Pages

## Overview

Added comprehensive filtering capabilities to both Decisions and Audit pages to enable clean demo scenarios and better governance visibility.

## Filters Added

### 1. Intent ID Filter
- **Purpose**: Filter by specific intent_id (e.g., `intent_clawdbot_safe_...`)
- **Backend Support**: ✅ Yes (`/decisions/query?intent_id=...` and `/audit/query?intent_id=...`)
- **UI**: Text input with monospace font
- **Use Case**: "Show me everything under clawdbot_safe"

### 2. Policy Version Filter
- **Purpose**: Filter by policy version (e.g., `1.0.0`)
- **Backend Support**: ❌ No (client-side filtering)
- **UI**: Text input with monospace font
- **Use Case**: Filter decisions by policy version

### 3. Time Range Filter
- **Purpose**: Filter by created_at timestamp range
- **Backend Support**: ❌ No (client-side filtering)
- **UI**: Two datetime-local inputs (Start Date, End Date)
- **Use Case**: "Show me everything in the last 5 minutes"

### 4. Verdict Filter
- **Purpose**: Filter by verdict (allowed/blocked/confirm)
- **Backend Support**: ✅ Yes (already existed)
- **UI**: Dropdown select
- **Use Case**: Show only blocked decisions

## Quick Actions

### "Last 5 Min" Button
- Automatically sets time range to last 5 minutes
- Useful for demos: "Show me everything under clawdbot_safe in the last 5 minutes"
- Available on both Decisions and Audit pages

### "Clear" Button
- Clears all filters
- Resets to default view

## Table Columns Added

Both pages now display:
- **Intent ID** column (truncated with tooltip for long IDs)
- **Policy Version** column

## Implementation Details

### Backend Filters (Server-Side)
- `intent_id` - Passed directly to API
- `verdict` - Passed directly to API
- `agent_id` - Passed directly to API

### Client-Side Filters
- `policy_version` - Filtered after fetching results
- `time_range` - Filtered after fetching results (using `created_at` or `timestamp`)

### API Changes
- Updated `getDecisions()` to accept `intent_id` parameter
- Updated `getAudit()` to accept `intent_id` parameter (already existed)
- Updated `Decision` interface to include `intent_id` and `created_at` fields

## Demo Workflow

**Example**: "Show me everything under clawdbot_safe in the last 5 minutes"

1. Navigate to Decisions or Audit page
2. Enter intent_id: `intent_clawdbot_safe_...` (or partial match)
3. Click "Last 5 Min" button (sets time range)
4. Click "Apply Filters"
5. View filtered results showing only:
   - Decisions/events with matching intent_id
   - Created within last 5 minutes
   - Clean view without older policy pack noise

## Files Modified

1. `src/lib/api.ts`
   - Updated `getDecisions()` to accept `intent_id`
   - Updated `Decision` interface

2. `src/pages/Decisions.tsx`
   - Added filter UI (intent_id, policy_version, time range)
   - Added Intent ID and Policy Version columns
   - Added "Last 5 Min" and "Clear" buttons
   - Client-side filtering logic

3. `src/pages/Audit.tsx`
   - Added filter UI (intent_id, policy_version, time range)
   - Added Intent ID and Policy Version columns
   - Added "Last 5 Min" and "Clear" buttons
   - Client-side filtering logic

## Benefits

✅ **Clean Demos**: Filter out noise from older policy packs
✅ **Better Visibility**: See exactly what happened under a specific intent
✅ **Time-Based Analysis**: Focus on recent events
✅ **Policy Tracking**: Filter by policy version to see changes over time
✅ **Quick Actions**: "Last 5 Min" button for instant recent view
