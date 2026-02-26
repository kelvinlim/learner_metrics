import { useState, useEffect } from 'react';
import { X, Search, Loader2 } from 'lucide-react';
import { orcidSearch, type ORCIDResult, type UserSummary } from '../api/client';

interface ORCIDLookupModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSelect: (orcidId: string) => void;
    user: UserSummary | null;
}

export default function ORCIDLookupModal({ isOpen, onClose, onSelect, user }: ORCIDLookupModalProps) {
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [institution, setInstitution] = useState('');
    const [results, setResults] = useState<ORCIDResult[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searched, setSearched] = useState(false);

    useEffect(() => {
        if (user && isOpen) {
            setFirstName(user.first_name || '');
            setLastName(user.last_name || '');
            setInstitution('');
            setResults([]);
            setError(null);
            setSearched(false);
        }
    }, [user, isOpen]);

    if (!isOpen) return null;

    const handleSearch = async () => {
        if (!firstName.trim() || !lastName.trim()) return;
        setLoading(true);
        setError(null);
        setSearched(true);
        try {
            const res = await orcidSearch(
                firstName.trim(),
                lastName.trim(),
                institution.trim() || undefined
            );
            setResults(res.data);
            if (res.data.length === 0) {
                setError('No ORCID profiles found. Try without an institution filter.');
            }
        } catch {
            setError('Failed to reach ORCID. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') handleSearch();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="fixed inset-0 bg-black/40" onClick={onClose} />
            <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-lg z-10">
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                    <div>
                        <h3 className="text-base font-semibold text-gray-900">ORCID iD Lookup</h3>
                        {user && (
                            <p className="text-sm text-gray-500">
                                Searching for: {user.first_name} {user.last_name}
                            </p>
                        )}
                    </div>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="px-6 py-5 space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-medium text-gray-700 mb-1">First Name</label>
                            <input
                                type="text"
                                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary/30 focus:border-brand-primary"
                                value={firstName}
                                onChange={(e) => setFirstName(e.target.value)}
                                onKeyDown={handleKeyDown}
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-medium text-gray-700 mb-1">Last Name</label>
                            <input
                                type="text"
                                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary/30 focus:border-brand-primary"
                                value={lastName}
                                onChange={(e) => setLastName(e.target.value)}
                                onKeyDown={handleKeyDown}
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-medium text-gray-700 mb-1">
                            Institution <span className="text-gray-400">(optional)</span>
                        </label>
                        <input
                            type="text"
                            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary/30 focus:border-brand-primary"
                            placeholder="e.g. University of Minnesota"
                            value={institution}
                            onChange={(e) => setInstitution(e.target.value)}
                            onKeyDown={handleKeyDown}
                        />
                    </div>

                    <button
                        onClick={handleSearch}
                        disabled={loading || !firstName.trim() || !lastName.trim()}
                        className="flex items-center gap-2 w-full justify-center rounded-lg bg-brand-primary text-white px-4 py-2 text-sm font-medium hover:bg-brand-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {loading ? (
                            <><Loader2 className="w-4 h-4 animate-spin" /> Searching ORCID...</>
                        ) : (
                            <><Search className="w-4 h-4" /> Search ORCID</>
                        )}
                    </button>

                    {error && (
                        <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
                    )}

                    {searched && !loading && results.length > 0 && (
                        <div>
                            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                                {results.length} profile{results.length > 1 ? 's' : ''} found — click to assign
                            </p>
                            <div className="max-h-64 overflow-y-auto rounded-lg border border-gray-100 divide-y divide-gray-50 shadow-inner">
                                {results.map((r) => (
                                    <button
                                        key={r.orcid_id}
                                        onClick={() => onSelect(r.orcid_id)}
                                        className="w-full text-left px-4 py-3 hover:bg-green-50 transition-colors"
                                    >
                                        <div className="text-sm font-semibold text-gray-900">{r.name || r.orcid_id}</div>
                                        <div className="text-xs font-mono text-green-700 mt-0.5">{r.orcid_id}</div>
                                        {r.affiliation && (
                                            <div className="text-xs text-gray-400 italic mt-0.5">{r.affiliation}</div>
                                        )}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                <div className="px-6 py-3 border-t border-gray-100 flex justify-end">
                    <button
                        onClick={onClose}
                        className="rounded-lg px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 transition-colors"
                    >
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    );
}
