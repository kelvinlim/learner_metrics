import { useState, useEffect } from 'react';
import { X, Search, Loader2 } from 'lucide-react';
import { nihLookup, type NIHProfileResult, type UserSummary } from '../api/client';

interface NIHProfileModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSelect: (profileId: number) => void;
    user: UserSummary | null;
}

export default function NIHProfileModal({ isOpen, onClose, onSelect, user }: NIHProfileModalProps) {
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [state, setState] = useState('');
    const [results, setResults] = useState<NIHProfileResult[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searched, setSearched] = useState(false);

    useEffect(() => {
        if (user && isOpen) {
            setFirstName(user.first_name || '');
            setLastName(user.last_name || '');
            setState('');
            setResults([]);
            setError(null);
            setSearched(false);
        }
    }, [user, isOpen]);

    if (!isOpen) return null;

    const handleLookup = async () => {
        if (!firstName.trim() || !lastName.trim()) return;
        setLoading(true);
        setError(null);
        setSearched(true);
        try {
            const res = await nihLookup(firstName.trim(), lastName.trim(), state.trim() || undefined);
            setResults(res.data);
            if (res.data.length === 0) {
                setError('No profiles found. Try without a state filter, or check the name spelling.');
            }
        } catch {
            setError('Failed to reach NIH RePORTER. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') handleLookup();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="fixed inset-0 bg-black/40" onClick={onClose} />
            <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-lg z-10">
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                    <div>
                        <h3 className="text-base font-semibold text-gray-900">NIH Profile Lookup</h3>
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

                    <div className="w-28">
                        <label className="block text-xs font-medium text-gray-700 mb-1">
                            State <span className="text-gray-400">(optional)</span>
                        </label>
                        <input
                            type="text"
                            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm uppercase focus:outline-none focus:ring-2 focus:ring-brand-primary/30 focus:border-brand-primary"
                            maxLength={2}
                            placeholder="e.g. MN"
                            value={state}
                            onChange={(e) => setState(e.target.value.toUpperCase())}
                            onKeyDown={handleKeyDown}
                        />
                    </div>

                    <button
                        onClick={handleLookup}
                        disabled={loading || !firstName.trim() || !lastName.trim()}
                        className="flex items-center gap-2 w-full justify-center rounded-lg bg-brand-primary text-white px-4 py-2 text-sm font-medium hover:bg-brand-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        {loading ? (
                            <><Loader2 className="w-4 h-4 animate-spin" /> Searching NIH RePORTER...</>
                        ) : (
                            <><Search className="w-4 h-4" /> Search NIH RePORTER</>
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
                                        key={r.profile_id}
                                        onClick={() => onSelect(r.profile_id)}
                                        className="w-full text-left px-4 py-3 hover:bg-blue-50 transition-colors"
                                    >
                                        <div className="text-sm font-semibold text-gray-900">{r.full_name}</div>
                                        <div className="text-xs text-gray-500 mt-0.5">
                                            Profile ID: {r.profile_id}
                                            {r.org && <span className="ml-2 italic text-gray-400">{r.org}</span>}
                                        </div>
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
