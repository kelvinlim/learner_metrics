import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Users, FlaskConical, BookOpen, GitMerge, ArrowRight } from 'lucide-react';
import { getMetricsSummary, type MetricsSummary } from '../api/client';
import { useAuthStore } from '../store/authStore';

export default function Dashboard() {
    const { user, tenantName } = useAuthStore();
    const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        getMetricsSummary()
            .then((r) => setMetrics(r.data))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    const displayName = user?.email || '';

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
                <p className="text-sm text-gray-500">
                    {tenantName ? `${tenantName} · ` : ''}{displayName}
                </p>
            </div>

            {/* Summary cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <SummaryCard
                    icon={<Users className="h-6 w-6 text-blue-500" />}
                    label="Investigators"
                    value={loading ? '—' : (metrics?.investigators ?? 0).toString()}
                    to="/users"
                />
                <SummaryCard
                    icon={<GitMerge className="h-6 w-6 text-purple-500" />}
                    label="NIH Grants"
                    value={loading ? '—' : (metrics?.grants ?? 0).toString()}
                    to="/grants"
                />
                <SummaryCard
                    icon={<FlaskConical className="h-6 w-6 text-green-500" />}
                    label="Publications"
                    value={loading ? '—' : (metrics?.publications ?? 0).toString()}
                    to="/publications"
                />
                <SummaryCard
                    icon={<BookOpen className="h-6 w-6 text-orange-500" />}
                    label="Units"
                    value={loading ? '—' : (metrics?.users ?? 0).toString()}
                    to="/units"
                />
            </div>

            {/* Integration status */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-white rounded-xl border border-gray-100 p-6">
                    <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4">Integration Coverage</h2>
                    <div className="space-y-3">
                        <IntegrationRow
                            label="NIH RePORTER"
                            linked={metrics?.nih_linked ?? 0}
                            total={metrics?.investigators ?? 0}
                            loading={loading}
                            color="bg-green-500"
                        />
                        <IntegrationRow
                            label="ORCID"
                            linked={metrics?.orcid_linked ?? 0}
                            total={metrics?.investigators ?? 0}
                            loading={loading}
                            color="bg-green-600"
                        />
                    </div>
                </div>

                <div className="bg-white rounded-xl border border-gray-100 p-6">
                    <h2 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4">Active Modules</h2>
                    <div className="space-y-2 text-sm">
                        <StatusRow done label="Multi-tenant auth (Google OAuth)" />
                        <StatusRow done label="Hierarchical units with RBAC" />
                        <StatusRow done label="NIH RePORTER integration" />
                        <StatusRow done label="ORCID public API integration" />
                        <StatusRow done label="PubMed E-utilities integration" />
                    </div>
                </div>
            </div>
        </div>
    );
}

function SummaryCard({ icon, label, value, to }: {
    icon: React.ReactNode;
    label: string;
    value: string;
    to: string;
}) {
    return (
        <Link to={to} className="bg-white rounded-xl border border-gray-100 p-4 hover:border-brand-primary/40 hover:shadow-sm transition-all group">
            <div className="flex items-center justify-between mb-3">
                {icon}
                <ArrowRight className="h-3 w-3 text-gray-300 group-hover:text-brand-primary transition-colors" />
            </div>
            <p className="text-2xl font-bold text-gray-900">{value}</p>
            <p className="text-xs text-gray-500 mt-0.5">{label}</p>
        </Link>
    );
}

function IntegrationRow({ label, linked, total, loading, color }: {
    label: string;
    linked: number;
    total: number;
    loading: boolean;
    color: string;
}) {
    const pct = total > 0 ? Math.round((linked / total) * 100) : 0;
    return (
        <div>
            <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-700">{label}</span>
                <span className="text-gray-400">{loading ? '—' : `${linked} / ${total}`}</span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                    className={`h-full rounded-full transition-all ${color}`}
                    style={{ width: loading ? '0%' : `${pct}%` }}
                />
            </div>
        </div>
    );
}

function StatusRow({ label, done }: { label: string; done?: boolean }) {
    return (
        <p className={done ? 'text-gray-700' : 'text-gray-400'}>
            {done ? '✅' : '⏳'} {label}
        </p>
    );
}
