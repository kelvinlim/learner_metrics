import { useState, useEffect, useRef, Fragment } from 'react';
import { createPortal } from 'react-dom';
import { RefreshCw, Search, ChevronRight, Loader2, AlertCircle } from 'lucide-react';
import {
    getNIHProjects,
    getUsers,
    syncAllNIHProjects,
    type NIHProject,
    type UserSummary,
} from '../api/client';

interface TooltipState {
    title: string;
    content: React.ReactNode;
    rect: DOMRect;
    direction: 'top' | 'bottom';
    width?: string;
}

function formatCost(n: number) {
    return '$' + n.toLocaleString();
}

export default function NIHGrantsPage() {
    const [projects, setProjects] = useState<NIHProject[]>([]);
    const [users, setUsers] = useState<UserSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [syncing, setSyncing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [syncMessage, setSyncMessage] = useState<string | null>(null);

    const [search, setSearch] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [selectedUserId, setSelectedUserId] = useState<string>('');
    const [activeOnly, setActiveOnly] = useState(true);

    const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
    const [activeTooltip, setActiveTooltip] = useState<TooltipState | null>(null);
    const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Load users for filter
    useEffect(() => {
        getUsers({ limit: 500 })
            .then((r) => setUsers(r.data.items.filter((u) => u.is_covered_investigator)))
            .catch(() => {});
    }, []);

    // Debounce search
    useEffect(() => {
        const t = setTimeout(() => setDebouncedSearch(search), 300);
        return () => clearTimeout(t);
    }, [search]);

    const loadProjects = async () => {
        setLoading(true);
        setError(null);
        try {
            const r = await getNIHProjects({
                user_id: selectedUserId || undefined,
                search: debouncedSearch || undefined,
                active_only: activeOnly,
                limit: 500,
            });
            setProjects(r.data.items);
        } catch {
            setError('Failed to load NIH projects. Check your connection and try again.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadProjects();
    }, [selectedUserId, debouncedSearch, activeOnly]);

    const handleSyncAll = async () => {
        setSyncing(true);
        setSyncMessage(null);
        try {
            const r = await syncAllNIHProjects();
            const d = r.data as { new: number; updated: number; users_synced: number; errors: number };
            setSyncMessage(
                `Sync complete: ${d.new} new, ${d.updated} updated across ${d.users_synced} investigator(s).${d.errors > 0 ? ` (${d.errors} errors)` : ''}`
            );
            await loadProjects();
        } catch {
            setSyncMessage('Sync failed. Please try again.');
        } finally {
            setSyncing(false);
        }
    };

    const toggleGroup = (coreNum: string) => {
        setExpandedGroups((prev) => {
            const next = new Set(prev);
            if (next.has(coreNum)) next.delete(coreNum);
            else next.add(coreNum);
            return next;
        });
    };

    const handleMouseEnter = (
        e: React.MouseEvent,
        title: string,
        content: React.ReactNode,
        width: string = 'w-96'
    ) => {
        if (closeTimeoutRef.current) {
            clearTimeout(closeTimeoutRef.current);
            closeTimeoutRef.current = null;
        }
        const rect = e.currentTarget.getBoundingClientRect();
        const spaceBelow = window.innerHeight - rect.bottom;
        setActiveTooltip({
            title,
            content,
            rect,
            direction: spaceBelow < 320 ? 'top' : 'bottom',
            width,
        });
    };

    const handleMouseLeave = () => {
        closeTimeoutRef.current = setTimeout(() => setActiveTooltip(null), 300);
    };

    // Group projects by core_project_num
    const grouped = projects.reduce<Record<string, NIHProject[]>>((acc, p) => {
        const k = p.core_project_num || p.project_num;
        if (!acc[k]) acc[k] = [];
        acc[k].push(p);
        return acc;
    }, {});

    // Sort each group by fiscal year desc
    Object.values(grouped).forEach((g) => g.sort((a, b) => b.fiscal_year - a.fiscal_year));

    // Sort groups by latest fiscal year desc
    const groupKeys = Object.keys(grouped).sort(
        (a, b) => grouped[b][0].fiscal_year - grouped[a][0].fiscal_year
    );

    const userMap = Object.fromEntries(users.map((u) => [u.id, u]));

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">NIH Grants</h1>
                    <p className="text-sm text-gray-500 mt-0.5">
                        Projects sourced from NIH RePORTER — grouped by core project number
                    </p>
                </div>
                <button
                    onClick={handleSyncAll}
                    disabled={syncing}
                    className="flex items-center gap-2 rounded-lg bg-brand-primary text-white px-4 py-2 text-sm font-medium hover:bg-brand-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    {syncing ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        <RefreshCw className="w-4 h-4" />
                    )}
                    Sync All Investigators
                </button>
            </div>

            {syncMessage && (
                <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800">
                    {syncMessage}
                </div>
            )}

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-3">
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                    <input
                        type="text"
                        placeholder="Search by title or grant number..."
                        className="pl-9 pr-4 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-primary/30 focus:border-brand-primary w-72"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>

                <select
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary/30 focus:border-brand-primary"
                    value={selectedUserId}
                    onChange={(e) => setSelectedUserId(e.target.value)}
                >
                    <option value="">All Investigators</option>
                    {users.map((u) => (
                        <option key={u.id} value={u.id}>
                            {u.first_name} {u.last_name}
                        </option>
                    ))}
                </select>

                <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                    <input
                        type="checkbox"
                        checked={activeOnly}
                        onChange={(e) => setActiveOnly(e.target.checked)}
                        className="rounded border-gray-300 text-brand-primary focus:ring-brand-primary"
                    />
                    Active projects only
                </label>

                {!loading && (
                    <span className="text-xs text-gray-400 ml-auto">
                        {groupKeys.length} grant{groupKeys.length !== 1 ? 's' : ''} ({projects.length} award years)
                    </span>
                )}
            </div>

            {error && (
                <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                    {error}
                </div>
            )}

            {/* Table */}
            <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
                <table className="min-w-full divide-y divide-gray-100">
                    <thead>
                        <tr className="bg-gray-50">
                            <th className="w-10 px-4 py-3" />
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                Project
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                PI
                            </th>
                            <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                Years
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                Latest End
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                Total Costs
                            </th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                        {loading ? (
                            <tr>
                                <td colSpan={6} className="px-6 py-16 text-center">
                                    <Loader2 className="w-6 h-6 animate-spin text-gray-400 mx-auto" />
                                    <p className="text-sm text-gray-400 mt-2">Loading NIH projects...</p>
                                </td>
                            </tr>
                        ) : groupKeys.length === 0 ? (
                            <tr>
                                <td colSpan={6} className="px-6 py-16 text-center text-sm text-gray-400 italic">
                                    No projects found.
                                    {projects.length === 0 && !debouncedSearch && (
                                        <span> Assign NIH Profile IDs to investigators and run a sync.</span>
                                    )}
                                </td>
                            </tr>
                        ) : (
                            groupKeys.map((coreNum) => {
                                const group = grouped[coreNum];
                                const latest = group[0];
                                const pi = userMap[latest.user_id];
                                const piName = pi
                                    ? `${pi.first_name} ${pi.last_name}`
                                    : 'Unknown';
                                const isExpanded = expandedGroups.has(coreNum);
                                const totalCosts = group.reduce((s, p) => s + (p.total_costs || 0), 0);
                                const yearRange =
                                    group.length > 1
                                        ? `${group[group.length - 1].fiscal_year}–${latest.fiscal_year}`
                                        : String(latest.fiscal_year);

                                return (
                                    <Fragment key={coreNum}>
                                        {/* Group header row */}
                                        <tr
                                            className="hover:bg-gray-50 cursor-pointer transition-colors"
                                            onClick={() => toggleGroup(coreNum)}
                                        >
                                            <td className="px-4 py-3 text-center">
                                                <ChevronRight
                                                    className={`w-4 h-4 text-gray-400 transition-transform inline ${isExpanded ? 'rotate-90' : ''}`}
                                                />
                                            </td>
                                            <td className="px-4 py-3">
                                                <div
                                                    className="inline-block"
                                                    onMouseEnter={(e) =>
                                                        handleMouseEnter(
                                                            e,
                                                            'Project Abstract',
                                                            <p className="text-sm leading-relaxed whitespace-pre-wrap">
                                                                {(latest as any).abstract_text || 'No abstract available.'}
                                                            </p>
                                                        )
                                                    }
                                                    onMouseLeave={handleMouseLeave}
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    <div className="text-sm font-bold text-brand-primary hover:underline cursor-help">
                                                        {coreNum}
                                                    </div>
                                                </div>
                                                <div
                                                    className="text-xs text-gray-700 mt-0.5 max-w-md truncate"
                                                    title={latest.project_title}
                                                >
                                                    {latest.project_title}
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                                                {piName}
                                            </td>
                                            <td className="px-4 py-3 text-sm text-gray-500 text-center whitespace-nowrap">
                                                {yearRange}
                                            </td>
                                            <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">
                                                {latest.project_end_date
                                                    ? new Date(latest.project_end_date + 'T00:00:00').toLocaleDateString()
                                                    : '—'}
                                            </td>
                                            <td className="px-4 py-3 text-sm font-semibold text-gray-900 text-right whitespace-nowrap">
                                                {formatCost(totalCosts)}
                                            </td>
                                        </tr>

                                        {/* Expanded award rows */}
                                        {isExpanded &&
                                            group.map((p) => (
                                                <tr key={p.id} className="bg-gray-50/70">
                                                    <td />
                                                    <td className="pl-10 pr-4 py-2 border-l-4 border-brand-primary/20">
                                                        <div className="text-xs font-medium text-gray-600">
                                                            {p.project_num}
                                                        </div>
                                                        <div
                                                            className="inline-block"
                                                            onMouseEnter={(e) =>
                                                                handleMouseEnter(
                                                                    e,
                                                                    'Award Details',
                                                                    <div className="space-y-2 text-xs">
                                                                        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                                                                            <span className="text-gray-500">Appl ID:</span>
                                                                            <span className="font-mono text-right">{p.appl_id}</span>
                                                                            <span className="text-gray-500">Fiscal Year:</span>
                                                                            <span className="text-right font-bold">{p.fiscal_year}</span>
                                                                            <span className="text-gray-500">Direct Costs:</span>
                                                                            <span className="text-right">{formatCost(p.direct_costs)}</span>
                                                                            <span className="text-gray-500">Indirect Costs:</span>
                                                                            <span className="text-right">{formatCost(p.indirect_costs)}</span>
                                                                            <span className="text-gray-500 font-semibold border-t pt-1">Total:</span>
                                                                            <span className="text-right font-bold border-t pt-1">{formatCost(p.total_costs)}</span>
                                                                        </div>
                                                                    </div>,
                                                                    'w-64'
                                                                )
                                                            }
                                                            onMouseLeave={handleMouseLeave}
                                                        >
                                                            <div className="text-xs text-gray-400 hover:text-brand-primary cursor-help hover:underline mt-0.5">
                                                                Appl ID: {p.appl_id}
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td />
                                                    <td className="px-4 py-2 text-xs text-gray-500 text-center">
                                                        FY {p.fiscal_year}
                                                    </td>
                                                    <td className="px-4 py-2 text-xs text-gray-500">
                                                        {p.project_end_date
                                                            ? new Date(p.project_end_date + 'T00:00:00').toLocaleDateString()
                                                            : '—'}
                                                    </td>
                                                    <td className="px-4 py-2 text-sm text-gray-600 text-right">
                                                        {formatCost(p.total_costs)}
                                                    </td>
                                                </tr>
                                            ))}
                                    </Fragment>
                                );
                            })
                        )}
                    </tbody>
                </table>
            </div>

            {/* Tooltip portal */}
            {activeTooltip &&
                createPortal(
                    <div
                        className={`${activeTooltip.width || 'w-96'} fixed z-[9999] p-4 bg-white border border-gray-200 shadow-2xl rounded-xl text-xs text-gray-700 pointer-events-auto`}
                        style={{
                            left: `${activeTooltip.rect.left}px`,
                            top:
                                activeTooltip.direction === 'top'
                                    ? `${activeTooltip.rect.top - 12}px`
                                    : `${activeTooltip.rect.bottom + 12}px`,
                            transform: activeTooltip.direction === 'top' ? 'translateY(-100%)' : 'none',
                        }}
                        onMouseEnter={() => {
                            if (closeTimeoutRef.current) {
                                clearTimeout(closeTimeoutRef.current);
                                closeTimeoutRef.current = null;
                            }
                        }}
                        onMouseLeave={handleMouseLeave}
                    >
                        <div className="font-semibold text-brand-primary border-b pb-2 mb-2">
                            {activeTooltip.title}
                        </div>
                        <div className="max-h-72 overflow-y-auto">{activeTooltip.content}</div>
                        <div
                            className={`absolute left-4 w-3 h-3 bg-white border-gray-200 transform rotate-45 ${
                                activeTooltip.direction === 'top'
                                    ? 'bottom-[-6px] border-r border-b'
                                    : 'top-[-6px] border-l border-t'
                            }`}
                        />
                    </div>,
                    document.body
                )}
        </div>
    );
}
