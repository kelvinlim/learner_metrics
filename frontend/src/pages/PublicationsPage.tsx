import { useState, useEffect } from 'react';
import { Search, RefreshCw, Loader2, AlertCircle, ExternalLink } from 'lucide-react';
import {
    getPublications,
    getUsers,
    syncAllORCID,
    syncAllPubMed,
    type PublicationItem,
    type UserSummary,
} from '../api/client';

const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
    orcid:  { label: 'ORCID',  color: 'bg-green-100 text-green-700' },
    pubmed: { label: 'PubMed', color: 'bg-blue-100 text-blue-700' },
    both:   { label: 'Both',   color: 'bg-purple-100 text-purple-700' },
    manual: { label: 'Manual', color: 'bg-gray-100 text-gray-600' },
};

function SourceBadge({ source }: { source: string }) {
    const cfg = SOURCE_LABELS[source] ?? SOURCE_LABELS.manual;
    return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
            {cfg.label}
        </span>
    );
}

export default function PublicationsPage() {
    const [pubs, setPubs] = useState<PublicationItem[]>([]);
    const [users, setUsers] = useState<UserSummary[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [search, setSearch] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [selectedUserId, setSelectedUserId] = useState('');
    const [selectedSource, setSelectedSource] = useState('');
    const [yearFrom, setYearFrom] = useState('');
    const [yearTo, setYearTo] = useState('');
    const [page, setPage] = useState(0);
    const LIMIT = 50;

    const [syncingOrcid, setSyncingOrcid] = useState(false);
    const [syncingPubmed, setSyncingPubmed] = useState(false);
    const [syncMsg, setSyncMsg] = useState<string | null>(null);

    useEffect(() => {
        getUsers({ limit: 500 })
            .then((r) => setUsers(r.data.items))
            .catch(() => {});
    }, []);

    useEffect(() => {
        const t = setTimeout(() => { setDebouncedSearch(search); setPage(0); }, 300);
        return () => clearTimeout(t);
    }, [search]);

    const loadPubs = async () => {
        setLoading(true);
        setError(null);
        try {
            const r = await getPublications({
                user_id: selectedUserId || undefined,
                source: selectedSource || undefined,
                year_from: yearFrom ? parseInt(yearFrom) : undefined,
                year_to: yearTo ? parseInt(yearTo) : undefined,
                search: debouncedSearch || undefined,
                limit: LIMIT,
                offset: page * LIMIT,
            });
            setPubs(r.data.items);
            setTotal(r.data.total);
        } catch {
            setError('Failed to load publications.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadPubs();
    }, [selectedUserId, selectedSource, yearFrom, yearTo, debouncedSearch, page]);

    const showSyncMsg = (msg: string) => {
        setSyncMsg(msg);
        setTimeout(() => setSyncMsg(null), 5000);
    };

    const handleSyncOrcid = async () => {
        setSyncingOrcid(true);
        try {
            const r = await syncAllORCID();
            const d = r.data as { new: number; updated: number; users_synced: number };
            showSyncMsg(`ORCID sync: ${d.new} new, ${d.updated} updated across ${d.users_synced} investigator(s).`);
            await loadPubs();
        } catch {
            showSyncMsg('ORCID sync failed.');
        } finally {
            setSyncingOrcid(false);
        }
    };

    const handleSyncPubmed = async () => {
        setSyncingPubmed(true);
        try {
            const r = await syncAllPubMed();
            const d = r.data as { new: number; updated: number; users_synced: number };
            showSyncMsg(`PubMed sync: ${d.new} new, ${d.updated} updated across ${d.users_synced} investigator(s).`);
            await loadPubs();
        } catch {
            showSyncMsg('PubMed sync failed.');
        } finally {
            setSyncingPubmed(false);
        }
    };

    const userMap = Object.fromEntries(users.map((u) => [u.id, u]));
    const totalPages = Math.ceil(total / LIMIT);

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Publications</h1>
                    <p className="text-sm text-gray-500 mt-0.5">
                        Publications sourced from ORCID and PubMed
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={handleSyncOrcid}
                        disabled={syncingOrcid}
                        className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 text-green-700 px-3 py-2 text-sm font-medium hover:bg-green-100 disabled:opacity-50 transition-colors"
                    >
                        {syncingOrcid ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                        Sync ORCID
                    </button>
                    <button
                        onClick={handleSyncPubmed}
                        disabled={syncingPubmed}
                        className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 text-blue-700 px-3 py-2 text-sm font-medium hover:bg-blue-100 disabled:opacity-50 transition-colors"
                    >
                        {syncingPubmed ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                        Sync PubMed
                    </button>
                </div>
            </div>

            {syncMsg && (
                <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800">
                    {syncMsg}
                </div>
            )}

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-3">
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                    <input
                        type="text"
                        placeholder="Search by title..."
                        className="pl-9 pr-4 py-2 text-sm rounded-lg border border-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-primary/30 focus:border-brand-primary w-64"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>

                <select
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary/30 focus:border-brand-primary"
                    value={selectedUserId}
                    onChange={(e) => { setSelectedUserId(e.target.value); setPage(0); }}
                >
                    <option value="">All Investigators</option>
                    {users.map((u) => (
                        <option key={u.id} value={u.id}>
                            {u.first_name} {u.last_name}
                        </option>
                    ))}
                </select>

                <select
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary/30 focus:border-brand-primary"
                    value={selectedSource}
                    onChange={(e) => { setSelectedSource(e.target.value); setPage(0); }}
                >
                    <option value="">All Sources</option>
                    <option value="orcid">ORCID</option>
                    <option value="pubmed">PubMed</option>
                    <option value="both">Both</option>
                    <option value="manual">Manual</option>
                </select>

                <div className="flex items-center gap-2 text-sm text-gray-600">
                    <span>Year:</span>
                    <input
                        type="number"
                        placeholder="From"
                        className="w-20 rounded-lg border border-gray-200 px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary/30"
                        value={yearFrom}
                        onChange={(e) => { setYearFrom(e.target.value); setPage(0); }}
                    />
                    <span>–</span>
                    <input
                        type="number"
                        placeholder="To"
                        className="w-20 rounded-lg border border-gray-200 px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary/30"
                        value={yearTo}
                        onChange={(e) => { setYearTo(e.target.value); setPage(0); }}
                    />
                </div>

                {!loading && (
                    <span className="text-xs text-gray-400 ml-auto">
                        {total.toLocaleString()} publication{total !== 1 ? 's' : ''}
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
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-16">Year</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Title</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">PI</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Journal</th>
                            <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider">Source</th>
                            <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wider">Links</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                        {loading ? (
                            <tr>
                                <td colSpan={6} className="px-6 py-16 text-center">
                                    <Loader2 className="w-6 h-6 animate-spin text-gray-400 mx-auto" />
                                    <p className="text-sm text-gray-400 mt-2">Loading publications...</p>
                                </td>
                            </tr>
                        ) : pubs.length === 0 ? (
                            <tr>
                                <td colSpan={6} className="px-6 py-16 text-center text-sm text-gray-400 italic">
                                    No publications found.
                                    {total === 0 && !debouncedSearch && (
                                        <span> Assign ORCID iDs or PubMed queries to investigators and run a sync.</span>
                                    )}
                                </td>
                            </tr>
                        ) : (
                            pubs.map((p) => {
                                const pi = userMap[p.user_id];
                                const piName = pi ? `${pi.first_name} ${pi.last_name}` : '—';
                                return (
                                    <tr key={p.id} className="hover:bg-gray-50">
                                        <td className="px-4 py-3 text-sm text-gray-500 whitespace-nowrap">
                                            {p.pub_year ?? '—'}
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="text-sm font-medium text-gray-900 max-w-lg">
                                                {p.title}
                                            </div>
                                            {p.authors && (
                                                <div className="text-xs text-gray-400 mt-0.5 truncate max-w-lg" title={p.authors}>
                                                    {p.authors}
                                                </div>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-gray-600 whitespace-nowrap">
                                            {piName}
                                        </td>
                                        <td className="px-4 py-3 text-sm text-gray-500 max-w-[180px] truncate" title={p.journal ?? ''}>
                                            {p.journal || '—'}
                                        </td>
                                        <td className="px-4 py-3 text-center">
                                            <SourceBadge source={p.source} />
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex items-center justify-center gap-2">
                                                {p.pmid && (
                                                    <a
                                                        href={`https://pubmed.ncbi.nlm.nih.gov/${p.pmid}/`}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-xs text-blue-600 hover:underline flex items-center gap-0.5"
                                                        title="PubMed"
                                                    >
                                                        PMID <ExternalLink className="w-3 h-3" />
                                                    </a>
                                                )}
                                                {p.doi && (
                                                    <a
                                                        href={`https://doi.org/${p.doi}`}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-xs text-gray-500 hover:underline flex items-center gap-0.5"
                                                        title="DOI"
                                                    >
                                                        DOI <ExternalLink className="w-3 h-3" />
                                                    </a>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })
                        )}
                    </tbody>
                </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between text-sm text-gray-600">
                    <span>
                        Showing {page * LIMIT + 1}–{Math.min((page + 1) * LIMIT, total)} of {total.toLocaleString()}
                    </span>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setPage((p) => Math.max(0, p - 1))}
                            disabled={page === 0}
                            className="px-3 py-1.5 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            Previous
                        </button>
                        <span className="px-3 py-1.5 text-xs">
                            Page {page + 1} of {totalPages}
                        </span>
                        <button
                            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                            disabled={page >= totalPages - 1}
                            className="px-3 py-1.5 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            Next
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
