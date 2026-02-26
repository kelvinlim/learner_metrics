import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { Plus, GitMerge, Edit2, X, Trash2, AlertCircle } from 'lucide-react';
import { useAuthStore } from '../store/authStore';

export const UnitManagement: React.FC = () => {
    const { hierarchy } = useAuthStore();
    const [units, setUnits] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [showForm, setShowForm] = useState(false);
    const [selectedUnit, setSelectedUnit] = useState<any>(null);
    const [formData, setFormData] = useState({ name: '', unit_level: 1, unit_type: '', parent_id: '' });
    const [deleteError, setDeleteError] = useState('');

    const fetchUnits = async () => {
        setLoading(true);
        try {
            const response = await api.get('/units');
            setUnits(response.data);
        } catch (err) {
            console.error('Failed to fetch units', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchUnits();
    }, []);

    useEffect(() => {
        if (selectedUnit) {
            setFormData({
                name: selectedUnit.name,
                unit_level: selectedUnit.unit_level,
                unit_type: selectedUnit.unit_type || '',
                parent_id: selectedUnit.parent_id || '',
            });
        } else {
            setFormData({ name: '', unit_level: 1, unit_type: '', parent_id: '' });
        }
    }, [selectedUnit]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            const payload = { ...formData, parent_id: formData.parent_id || null };
            if (selectedUnit) {
                await api.put(`/units/${selectedUnit.id}`, payload);
            } else {
                await api.post('/units', payload);
            }
            setShowForm(false);
            setSelectedUnit(null);
            fetchUnits();
        } catch (err) {
            console.error('Failed to save unit', err);
        }
    };

    const handleDelete = async (unitId: string) => {
        if (!window.confirm('Delete this unit? This cannot be undone.')) return;
        setDeleteError('');
        try {
            await api.delete(`/units/${unitId}`);
            fetchUnits();
        } catch (err: any) {
            setDeleteError(err.response?.data?.detail || 'Failed to delete unit');
            setTimeout(() => setDeleteError(''), 5000);
        }
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Unit Management</h1>
                    <p className="text-sm text-gray-500">Define and manage organizational units for this tenant</p>
                </div>
                <button
                    onClick={() => { setSelectedUnit(null); setShowForm(true); }}
                    className="flex items-center px-4 py-2 bg-brand-primary text-white font-medium rounded-lg hover:bg-opacity-90 transition-colors shadow-sm"
                >
                    <Plus className="mr-2 h-4 w-4" />
                    Add Unit
                </button>
            </div>

            {deleteError && (
                <div className="p-3 bg-red-50 border border-red-100 text-red-600 text-sm rounded-lg flex items-center">
                    <AlertCircle className="h-4 w-4 mr-2 shrink-0" />
                    {deleteError}
                </div>
            )}

            {showForm && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                    <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden">
                        <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center">
                            <h2 className="font-bold text-gray-900">
                                {selectedUnit ? 'Edit Unit' : 'New Organizational Unit'}
                            </h2>
                            <button onClick={() => { setShowForm(false); setSelectedUnit(null); }} className="text-gray-400 hover:text-gray-600">
                                <X className="h-5 w-5" />
                            </button>
                        </div>
                        <form onSubmit={handleSubmit} className="p-6 space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Unit Name</label>
                                <input
                                    type="text"
                                    required
                                    className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none"
                                    value={formData.name}
                                    onChange={e => setFormData({ ...formData, name: e.target.value })}
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Level</label>
                                    <select
                                        required
                                        className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none"
                                        value={formData.unit_level}
                                        onChange={e => setFormData({ ...formData, unit_level: parseInt(e.target.value) })}
                                    >
                                        {hierarchy ? (
                                            Object.entries(hierarchy).map(([lvl, label]) => (
                                                <option key={lvl} value={lvl}>{lvl} — {label}</option>
                                            ))
                                        ) : (
                                            [1, 2, 3, 4].map(n => (
                                                <option key={n} value={n}>Level {n}</option>
                                            ))
                                        )}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Type</label>
                                    <input
                                        type="text"
                                        placeholder="Dept, College…"
                                        className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none"
                                        value={formData.unit_type}
                                        onChange={e => setFormData({ ...formData, unit_type: e.target.value })}
                                    />
                                </div>
                            </div>
                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-1">Parent Unit</label>
                                <select
                                    className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-brand-primary outline-none"
                                    value={formData.parent_id}
                                    onChange={e => setFormData({ ...formData, parent_id: e.target.value })}
                                >
                                    <option value="">None (Root)</option>
                                    {units.filter((u: any) => u.id !== selectedUnit?.id).map((u: any) => (
                                        <option key={u.id} value={u.id}>{u.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex justify-end space-x-3 pt-2">
                                <button type="button" onClick={() => { setShowForm(false); setSelectedUnit(null); }} className="px-4 py-2 text-gray-600 hover:bg-gray-50 rounded-lg">Cancel</button>
                                <button type="submit" className="px-4 py-2 bg-brand-primary text-white rounded-lg font-medium">
                                    {selectedUnit ? 'Save Changes' : 'Create Unit'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            <div className="bg-white rounded-xl shadow-sm border border-gray-100 divide-y divide-gray-100">
                {loading && <div className="p-8 text-center text-gray-400">Loading units…</div>}
                {!loading && units.length === 0 && (
                    <div className="p-12 text-center text-gray-500 italic">No units defined yet.</div>
                )}
                {units.map((unit: any) => (
                    <div key={unit.id} className="p-4 flex items-center justify-between hover:bg-gray-50 transition-colors group">
                        <div className="flex items-center space-x-4">
                            <div className="p-2 bg-gray-100 rounded-lg">
                                <GitMerge className="h-5 w-5 text-gray-500" />
                            </div>
                            <div>
                                <h3 className="font-semibold text-gray-900">{unit.name}</h3>
                                <div className="flex items-center gap-2 text-xs text-gray-500 mt-0.5">
                                    <span className="bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded font-medium border border-blue-100">
                                        {hierarchy?.[unit.unit_level] || `Level ${unit.unit_level}`}
                                    </span>
                                    {unit.unit_type && <span className="text-gray-400">&bull;</span>}
                                    {unit.unit_type && <span>{unit.unit_type}</span>}
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button
                                onClick={() => { setSelectedUnit(unit); setShowForm(true); }}
                                className="p-2 hover:bg-blue-50 rounded-full text-blue-600"
                                title="Edit"
                            >
                                <Edit2 className="h-4 w-4" />
                            </button>
                            <button
                                onClick={() => handleDelete(unit.id)}
                                className="p-2 hover:bg-red-50 rounded-full text-red-500"
                                title="Delete"
                            >
                                <Trash2 className="h-4 w-4" />
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default UnitManagement;
