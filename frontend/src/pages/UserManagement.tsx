import React, { useEffect, useState } from 'react';
import api, {
    assignNIHProfile,
    assignORCID,
    syncNIHProjects,
    type UserSummary,
} from '../api/client';
import {
    Plus,
    Search,
    Edit2,
    X,
    Trash2,
    AlertCircle,
    Users,
    CheckCircle,
    Circle,
    RefreshCw,
    Loader2,
} from 'lucide-react';
import NIHProfileModal from '../components/NIHProfileModal';
import ORCIDLookupModal from '../components/ORCIDLookupModal';

interface Unit {
    id: string;
    name: string;
    unit_level: number;
}

const emptyForm = {
    email: '',
    first_name: '',
    last_name: '',
    unit_id: '',
    is_active: true,
    is_covered_investigator: false,
    nih_profile_id: '',
    orcid_id: '',
    pubmed_query: '',
};

export default function UserManagement() {
    const [users, setUsers] = useState<UserSummary[]>([]);
    const [units, setUnits] = useState<Unit[]>([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [showForm, setShowForm] = useState(false);
    const [selectedUser, setSelectedUser] = useState<UserSummary | null>(null);
    const [formData, setFormData] = useState(emptyForm);
    const [formError, setFormError] = useState('');
    const [deleteError, setDeleteError] = useState('');

    // NIH profile lookup modal
    const [nihModalUser, setNihModalUser] = useState<UserSummary | null>(null);
    // ORCID lookup modal
    const [orcidModalUser, setOrcidModalUser] = useState<UserSummary | null>(null);
    const [syncingUserId, setSyncingUserId] = useState<string | null>(null);
    const [syncMessages, setSyncMessages] = useState<Record<string, string>>({});

    const fetchData = async () => {
        setLoading(true);
        try {
            const [usersRes, unitsRes] = await Promise.all([
                api.get('/users'),
                api.get('/units'),
            ]);
            // Handle both array and paginated response
            const rawUsers = Array.isArray(usersRes.data) ? usersRes.data : usersRes.data.items ?? [];
            setUsers(rawUsers);
            setUnits(unitsRes.data);
        } catch (err) {
            console.error('Failed to fetch data', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchData(); }, []);

    useEffect(() => {
        if (selectedUser) {
            setFormData({
                email: selectedUser.email,
                first_name: selectedUser.first_name || '',
                last_name: selectedUser.last_name || '',
                unit_id: selectedUser.unit_id || '',
                is_active: selectedUser.is_active,
                is_covered_investigator: selectedUser.is_covered_investigator,
                nih_profile_id: selectedUser.nih_profile_id?.toString() || '',
                orcid_id: selectedUser.orcid_id || '',
                pubmed_query: selectedUser.pubmed_query || '',
            });
        } else {
            setFormData(emptyForm);
        }
    }, [selectedUser]);

    const openAdd = () => { setSelectedUser(null); setFormError(''); setShowForm(true); };
    const openEdit = (u: UserSummary) => { setSelectedUser(u); setFormError(''); setShowForm(true); };
    const closeForm = () => { setShowForm(false); setSelectedUser(null); setFormError(''); };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setFormError('');
        try {
            const payload: Record<string, unknown> = {
                email: formData.email,
                first_name: formData.first_name || null,
                last_name: formData.last_name || null,
                unit_id: formData.unit_id || null,
                is_active: formData.is_active,
                is_covered_investigator: formData.is_covered_investigator,
            };
            if (selectedUser) {
                if (formData.nih_profile_id) payload.nih_profile_id = parseInt(formData.nih_profile_id);
                if (formData.orcid_id) payload.orcid_id = formData.orcid_id;
                if (formData.pubmed_query) payload.pubmed_query = formData.pubmed_query;
                await api.put(`/users/${selectedUser.id}`, payload);
            } else {
                await api.post('/users', payload);
            }
            closeForm();
            fetchData();
        } catch (err: unknown) {
            const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
            setFormError(msg || 'Failed to save investigator');
        }
    };

    const handleDelete = async (userId: string) => {
        if (!window.confirm('Delete this investigator? This cannot be undone.')) return;
        setDeleteError('');
        try {
            await api.delete(`/users/${userId}`);
            fetchData();
        } catch (err: unknown) {
            const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
            setDeleteError(msg || 'Failed to delete investigator');
            setTimeout(() => setDeleteError(''), 5000);
        }
    };

    const handleNIHProfileSelected = async (profileId: number) => {
        if (!nihModalUser) return;
        try {
            await assignNIHProfile(nihModalUser.id, profileId);
            setNihModalUser(null);
            fetchData();
        } catch {
            // Leave modal open on error
        }
    };

    const handleORCIDSelected = async (orcidId: string) => {
        if (!orcidModalUser) return;
        try {
            await assignORCID(orcidModalUser.id, orcidId);
            setOrcidModalUser(null);
            fetchData();
        } catch {
            // Leave modal open on error
        }
    };

    const handleSyncUser = async (userId: string) => {
        setSyncingUserId(userId);
        try {
            const r = await syncNIHProjects(userId);
            const d = r.data as { new: number; updated: number; status: string };
            const msg = d.status === 'success'
                ? `Synced: ${d.new} new, ${d.updated} updated`
                : d.status;
            setSyncMessages((prev) => ({ ...prev, [userId]: msg }));
            setTimeout(() => setSyncMessages((prev) => { const n = { ...prev }; delete n[userId]; return n; }), 4000);
            fetchData();
        } catch {
            setSyncMessages((prev) => ({ ...prev, [userId]: 'Sync failed' }));
            setTimeout(() => setSyncMessages((prev) => { const n = { ...prev }; delete n[userId]; return n; }), 4000);
        } finally {
            setSyncingUserId(null);
        }
    };

    const filtered = users.filter(u => {
        const q = search.toLowerCase();
        return (
            u.email.toLowerCase().includes(q) ||
            (u.first_name || '').toLowerCase().includes(q) ||
            (u.last_name || '').toLowerCase().includes(q)
        );
    });

    const unitName = (id: string | null) => {
        if (!id) return null;
        return units.find(u => u.id === id)?.name ?? null;
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Investigators</h1>
                    <p className="text-sm text-gray-500">Manage investigators and their integration settings</p>
                </div>
                <button
                    onClick={openAdd}
                    className="flex items-center px-4 py-2 bg-brand-primary text-white font-medium rounded-lg hover:bg-opacity-90 transition-colors shadow-sm"
                >
                    <Plus className="mr-2 h-4 w-4" />
                    Add Investigator
                </button>
            </div>

            {deleteError && (
                <div className="p-3 bg-red-50 border border-red-100 text-red-600 text-sm rounded-lg flex items-center">
                    <AlertCircle className="h-4 w-4 mr-2 shrink-0" />
                    {deleteError}
                </div>
            )}

            {/* Search */}
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                    type="text"
                    placeholder="Search by name or email…"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none text-sm"
                />
            </div>

            {/* Table */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b border-gray-100">
                        <tr>
                            <th className="text-left px-4 py-3 text-xs font-bold text-gray-500 uppercase tracking-wider">Name</th>
                            <th className="text-left px-4 py-3 text-xs font-bold text-gray-500 uppercase tracking-wider">Unit</th>
                            <th className="px-4 py-3 text-xs font-bold text-gray-500 uppercase tracking-wider">NIH Profile</th>
                            <th className="text-center px-4 py-3 text-xs font-bold text-gray-500 uppercase tracking-wider">ORCID</th>
                            <th className="text-center px-4 py-3 text-xs font-bold text-gray-500 uppercase tracking-wider">PubMed</th>
                            <th className="text-center px-4 py-3 text-xs font-bold text-gray-500 uppercase tracking-wider">Status</th>
                            <th className="px-4 py-3" />
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                        {loading && (
                            <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">Loading…</td></tr>
                        )}
                        {!loading && filtered.length === 0 && (
                            <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500 italic">No investigators found.</td></tr>
                        )}
                        {filtered.map(u => (
                            <tr key={u.id} className="hover:bg-gray-50 group">
                                <td className="px-4 py-3">
                                    <div className="font-medium text-gray-900">
                                        {u.first_name || u.last_name ? `${u.first_name || ''} ${u.last_name || ''}`.trim() : '—'}
                                    </div>
                                    <div className="text-xs text-gray-500">{u.email}</div>
                                </td>
                                <td className="px-4 py-3 text-gray-600 text-xs">
                                    {unitName(u.unit_id) || <span className="italic text-gray-400">unassigned</span>}
                                </td>
                                <td className="px-4 py-3">
                                    {u.nih_profile_id ? (
                                        <div className="flex items-center gap-2">
                                            <span className="inline-flex items-center gap-1 text-green-600">
                                                <CheckCircle className="h-4 w-4" />
                                                <span className="text-xs font-mono">{u.nih_profile_id}</span>
                                            </span>
                                            <button
                                                onClick={() => handleSyncUser(u.id)}
                                                disabled={syncingUserId === u.id}
                                                className="p-1 rounded hover:bg-blue-50 text-blue-500 disabled:opacity-50"
                                                title="Sync NIH projects"
                                            >
                                                {syncingUserId === u.id
                                                    ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                                    : <RefreshCw className="h-3.5 w-3.5" />}
                                            </button>
                                            {syncMessages[u.id] && (
                                                <span className="text-xs text-green-600">{syncMessages[u.id]}</span>
                                            )}
                                        </div>
                                    ) : (
                                        <button
                                            onClick={() => setNihModalUser(u)}
                                            className="flex items-center gap-1 text-xs text-gray-400 hover:text-brand-primary hover:underline"
                                        >
                                            <Circle className="h-4 w-4" />
                                            <span>Find profile</span>
                                        </button>
                                    )}
                                </td>
                                <td className="px-4 py-3 text-center">
                                    {u.orcid_id ? (
                                        <span className="inline-flex items-center gap-1 text-green-600">
                                            <CheckCircle className="h-4 w-4" />
                                            <span className="text-xs font-mono truncate max-w-[90px]">{u.orcid_id}</span>
                                        </span>
                                    ) : (
                                        <button
                                            onClick={() => setOrcidModalUser(u)}
                                            className="flex items-center gap-1 text-xs text-gray-400 hover:text-green-600 hover:underline mx-auto"
                                        >
                                            <Circle className="h-4 w-4" />
                                            <span>Find</span>
                                        </button>
                                    )}
                                </td>
                                <td className="px-4 py-3 text-center">
                                    {u.pubmed_query ? (
                                        <CheckCircle className="h-4 w-4 text-green-600 mx-auto" />
                                    ) : <Circle className="h-4 w-4 text-gray-300 mx-auto" />}
                                </td>
                                <td className="px-4 py-3 text-center">
                                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                                        u.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                                    }`}>
                                        {u.is_active ? 'Active' : 'Inactive'}
                                    </span>
                                </td>
                                <td className="px-4 py-3">
                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity justify-end">
                                        <button onClick={() => openEdit(u)} className="p-1.5 hover:bg-blue-50 rounded text-blue-600" title="Edit">
                                            <Edit2 className="h-4 w-4" />
                                        </button>
                                        <button onClick={() => handleDelete(u.id)} className="p-1.5 hover:bg-red-50 rounded text-red-500" title="Delete">
                                            <Trash2 className="h-4 w-4" />
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Form modal */}
            {showForm && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg overflow-hidden">
                        <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center">
                            <div className="flex items-center gap-2">
                                <Users className="h-5 w-5 text-brand-primary" />
                                <h2 className="font-bold text-gray-900">
                                    {selectedUser ? 'Edit Investigator' : 'Add Investigator'}
                                </h2>
                            </div>
                            <button onClick={closeForm} className="text-gray-400 hover:text-gray-600">
                                <X className="h-5 w-5" />
                            </button>
                        </div>

                        <form onSubmit={handleSubmit} className="p-6 space-y-4 max-h-[80vh] overflow-y-auto">
                            {formError && (
                                <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg flex items-center gap-2">
                                    <AlertCircle className="h-4 w-4 shrink-0" />
                                    {formError}
                                </div>
                            )}

                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Email *</label>
                                <input
                                    type="email"
                                    required
                                    className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none text-sm"
                                    value={formData.email}
                                    onChange={e => setFormData({ ...formData, email: e.target.value })}
                                    disabled={!!selectedUser}
                                />
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">First Name</label>
                                    <input
                                        type="text"
                                        className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none text-sm"
                                        value={formData.first_name}
                                        onChange={e => setFormData({ ...formData, first_name: e.target.value })}
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Last Name</label>
                                    <input
                                        type="text"
                                        className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none text-sm"
                                        value={formData.last_name}
                                        onChange={e => setFormData({ ...formData, last_name: e.target.value })}
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Unit</label>
                                <select
                                    className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none text-sm"
                                    value={formData.unit_id}
                                    onChange={e => setFormData({ ...formData, unit_id: e.target.value })}
                                >
                                    <option value="">Unassigned</option>
                                    {units.map(u => (
                                        <option key={u.id} value={u.id}>{u.name}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="flex gap-6">
                                <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-700">
                                    <input
                                        type="checkbox"
                                        className="rounded border-gray-300 text-brand-primary"
                                        checked={formData.is_active}
                                        onChange={e => setFormData({ ...formData, is_active: e.target.checked })}
                                    />
                                    Active
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-700">
                                    <input
                                        type="checkbox"
                                        className="rounded border-gray-300 text-brand-primary"
                                        checked={formData.is_covered_investigator}
                                        onChange={e => setFormData({ ...formData, is_covered_investigator: e.target.checked })}
                                    />
                                    Covered Investigator
                                </label>
                            </div>

                            {/* Integration fields (edit only) */}
                            {selectedUser && (
                                <>
                                    <hr className="border-gray-100" />
                                    <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">Integration Settings</p>

                                    <div>
                                        <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">NIH Profile ID</label>
                                        <div className="flex gap-2">
                                            <input
                                                type="number"
                                                placeholder="e.g. 1234567"
                                                className="flex-1 px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none text-sm"
                                                value={formData.nih_profile_id}
                                                onChange={e => setFormData({ ...formData, nih_profile_id: e.target.value })}
                                            />
                                            <button
                                                type="button"
                                                onClick={() => { closeForm(); setNihModalUser(selectedUser); }}
                                                className="px-3 py-2 text-xs border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 whitespace-nowrap"
                                            >
                                                Lookup
                                            </button>
                                        </div>
                                    </div>

                                    <div>
                                        <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">ORCID iD</label>
                                        <input
                                            type="text"
                                            placeholder="0000-0000-0000-0000"
                                            className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none text-sm font-mono"
                                            value={formData.orcid_id}
                                            onChange={e => setFormData({ ...formData, orcid_id: e.target.value })}
                                        />
                                    </div>

                                    <div>
                                        <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">PubMed Query</label>
                                        <textarea
                                            placeholder='e.g. Smith J[Author] AND "University of Minnesota"[Affiliation]'
                                            rows={2}
                                            className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none text-sm font-mono resize-none"
                                            value={formData.pubmed_query}
                                            onChange={e => setFormData({ ...formData, pubmed_query: e.target.value })}
                                        />
                                    </div>
                                </>
                            )}

                            <div className="flex justify-end gap-3 pt-2">
                                <button type="button" onClick={closeForm} className="px-4 py-2 text-gray-600 hover:bg-gray-50 rounded-lg text-sm">Cancel</button>
                                <button type="submit" className="px-4 py-2 bg-brand-primary text-white rounded-lg font-medium text-sm">
                                    {selectedUser ? 'Save Changes' : 'Add Investigator'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* NIH Profile Lookup Modal */}
            <NIHProfileModal
                isOpen={nihModalUser !== null}
                onClose={() => setNihModalUser(null)}
                onSelect={handleNIHProfileSelected}
                user={nihModalUser}
            />

            {/* ORCID Lookup Modal */}
            <ORCIDLookupModal
                isOpen={orcidModalUser !== null}
                onClose={() => setOrcidModalUser(null)}
                onSelect={handleORCIDSelected}
                user={orcidModalUser}
            />
        </div>
    );
}
