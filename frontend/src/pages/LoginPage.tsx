import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { googleIdentify, googleAuthenticate, devLogin } from '../api/client';
import type { TenantOption } from '../api/client';

declare global {
    interface Window {
        google?: any;
    }
}

export default function LoginPage() {
    const navigate = useNavigate();
    const { setAuth, setAvailableTenants } = useAuthStore();

    const [step, setStep] = useState<'signin' | 'select-tenant'>('signin');
    const [identityId, setIdentityId] = useState<string>('');
    const [tenants, setTenants] = useState<TenantOption[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const [devEmail, setDevEmail] = useState('');

    async function handleGoogleCredential(credential: string) {
        setLoading(true);
        setError(null);
        try {
            const res = await googleIdentify(credential);
            const { identity_id, tenants: availableTenants } = res.data;

            setIdentityId(identity_id);
            setTenants(availableTenants);
            setAvailableTenants(availableTenants);

            if (availableTenants.length === 1) {
                await selectTenant(identity_id, availableTenants[0].tenant_id, availableTenants[0].tenant_name);
            } else if (availableTenants.length > 1) {
                setStep('select-tenant');
            } else {
                setError('No tenants found for this account. Contact your administrator.');
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Login failed. Please try again.');
        } finally {
            setLoading(false);
        }
    }

    async function selectTenant(iid: string, tenantId: string, tenantName: string) {
        setLoading(true);
        setError(null);
        try {
            const res = await googleAuthenticate(iid, tenantId);
            setAuth(res.data.access_token, res.data.tenant_id, res.data.tenant_name);
            navigate('/');
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Authentication failed.');
        } finally {
            setLoading(false);
        }
    }

    async function handleDevLogin(e: React.FormEvent) {
        e.preventDefault();
        setLoading(true);
        setError(null);
        try {
            const res = await devLogin(devEmail.trim());
            const { identity_id, tenants: availableTenants } = res.data;
            setIdentityId(identity_id);
            setTenants(availableTenants);
            setAvailableTenants(availableTenants);
            if (availableTenants.length === 1) {
                await selectTenant(identity_id, availableTenants[0].tenant_id, availableTenants[0].tenant_name);
            } else {
                setStep('select-tenant');
            }
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Dev login failed.');
        } finally {
            setLoading(false);
        }
    }

    // Load Google Identity Services script and render button
    function initGoogleButton(el: HTMLDivElement | null) {
        if (!el) return;
        const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
        if (!clientId) return;

        const script = document.createElement('script');
        script.src = 'https://accounts.google.com/gsi/client';
        script.async = true;
        script.defer = true;
        script.onload = () => {
            window.google?.accounts.id.initialize({
                client_id: clientId,
                callback: (response: any) => { if (response?.credential) handleGoogleCredential(response.credential); },
            });
            window.google?.accounts.id.renderButton(el, {
                theme: 'outline',
                size: 'large',
                width: 300,
            });
        };
        document.head.appendChild(script);
    }

    return (
        <div className="min-h-screen bg-gray-50 flex items-center justify-center">
            <div className="bg-white rounded-2xl shadow-lg p-8 w-full max-w-sm">
                <div className="text-center mb-8">
                    <h1 className="text-2xl font-bold text-gray-900">Learner Metrics</h1>
                    <p className="text-sm text-gray-500 mt-1">NIH Training Program Tracking</p>
                </div>

                {error && (
                    <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                        {error}
                    </div>
                )}

                {step === 'signin' && (
                    <div className="flex flex-col items-center gap-4">
                        <p className="text-sm text-gray-600">Sign in with your institutional Google account</p>
                        {loading ? (
                            <div className="text-sm text-gray-400">Signing in…</div>
                        ) : (
                            <div ref={initGoogleButton} />
                        )}
                        {import.meta.env.DEV && (
                            <form onSubmit={handleDevLogin} className="w-full border-t border-gray-100 pt-4 flex flex-col gap-2">
                                <p className="text-xs text-amber-600 font-medium text-center">Dev bypass</p>
                                <input
                                    type="email"
                                    value={devEmail}
                                    onChange={e => setDevEmail(e.target.value)}
                                    placeholder="email@example.com"
                                    required
                                    disabled={loading}
                                    className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-300"
                                />
                                <button
                                    type="submit"
                                    disabled={loading || !devEmail}
                                    className="w-full py-2 text-sm font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-lg hover:bg-amber-100 disabled:opacity-50"
                                >
                                    Sign in (dev)
                                </button>
                            </form>
                        )}
                    </div>
                )}

                {step === 'select-tenant' && (
                    <div>
                        <p className="text-sm text-gray-600 mb-4">Select your institution:</p>
                        <div className="space-y-2">
                            {tenants.map((t) => (
                                <button
                                    key={t.tenant_id}
                                    onClick={() => selectTenant(identityId, t.tenant_id, t.tenant_name)}
                                    disabled={loading}
                                    className="w-full text-left px-4 py-3 rounded-lg border border-gray-200 hover:border-blue-400 hover:bg-blue-50 transition-colors"
                                >
                                    <span className="text-sm font-medium text-gray-900">{t.tenant_name}</span>
                                </button>
                            ))}
                        </div>
                        {loading && <p className="text-sm text-gray-400 mt-3 text-center">Authenticating…</p>}
                    </div>
                )}
            </div>
        </div>
    );
}
