import { useQuery } from '@tanstack/react-query'
import { Bot, RefreshCw } from 'lucide-react'
import AccountLayout, { PageHeader, StatusBadge, Spinner, EmptyState } from './AccountLayout'
import { gwAgents } from '../../lib/gateway'

export default function Agents() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['agents'],
    queryFn: gwAgents,
    refetchInterval: 20_000,
  })

  const agents = data?.agents ?? []
  const online = agents.filter((a) => a.status !== 'offline').length

  return (
    <AccountLayout>
      <div className="p-6 max-w-5xl">
        <PageHeader
          title="Agent Fleet"
          description={agents.length ? `${online} of ${agents.length} agents active` : 'Connected AI agents and their status.'}
          action={
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          }
        />

        {isLoading ? (
          <Spinner />
        ) : agents.length === 0 ? (
          <div className="rounded-lg border border-border bg-card">
            <EmptyState message="No agents registered. Connect your first agent via the SDK." />
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {agents.map((agent) => (
              <div key={agent.id} className="rounded-lg border border-border bg-card p-4 hover:border-border/80 transition-colors">
                <div className="flex items-start justify-between mb-3">
                  <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center">
                    <Bot className="h-4.5 w-4.5 text-primary" />
                  </div>
                  <StatusBadge status={agent.status} />
                </div>

                <h3 className="font-space font-semibold text-sm mb-0.5 truncate">{agent.name}</h3>
                <p className="text-xs font-mono text-muted-foreground truncate mb-3">{agent.id}</p>

                <div className="grid grid-cols-2 gap-2 text-xs">
                  {agent.model && (
                    <div>
                      <p className="text-muted-foreground/60">Model</p>
                      <p className="text-muted-foreground truncate">{agent.model}</p>
                    </div>
                  )}
                  {agent.decisions_today != null && (
                    <div>
                      <p className="text-muted-foreground/60">Today</p>
                      <p className="text-muted-foreground">{agent.decisions_today.toLocaleString()} decisions</p>
                    </div>
                  )}
                  {agent.last_seen && (
                    <div className="col-span-2">
                      <p className="text-muted-foreground/60">Last seen</p>
                      <p className="text-muted-foreground">{new Date(agent.last_seen).toLocaleString()}</p>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-6 rounded-lg border border-border/50 bg-card/50 p-4 text-sm text-muted-foreground">
          <p className="font-medium text-foreground mb-1">Register a new agent</p>
          <p className="text-xs mb-2">Agents register automatically when they connect via the SDK.</p>
          <code className="text-xs bg-secondary px-2 py-1 rounded font-mono">
            from edon_sdk import EdonGateway; client = EdonGateway(your_llm_client)
          </code>
        </div>
      </div>
    </AccountLayout>
  )
}
