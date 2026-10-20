import { AlertCircle, CheckCircle2 } from 'lucide-react';

export function IntegrationDiagnostic({ result }: { result?: string | {
  connected?: boolean;
  message?: string;
  latency_ms?: number;
} }) {
  if (!result) return null;
  if (typeof result === 'string') return <p role="status" className="mt-2 text-xs text-muted">{result}</p>;
  const Icon = result.connected ? CheckCircle2 : AlertCircle;
  return (
    <div role="status" className={`mt-2 border-t border-border pt-2 text-xs ${result.connected ? 'text-brand-800' : 'text-amber-800'}`}>
      <div className="flex items-start gap-1.5">
        <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>{result.message || 'The provider connection could not be verified.'}</span>
      </div>
      {typeof result.latency_ms === 'number' && <p className="mt-1 text-muted">API response: {result.latency_ms}ms</p>}
    </div>
  );
}
