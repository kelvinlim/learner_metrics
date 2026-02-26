import { create } from 'zustand';
import { jwtDecode } from 'jwt-decode';
import api from '../api/client';

interface TenantOption {
    tenant_id: string;
    tenant_name: string;
}

interface Branding {
    primaryColor: string | null;
    secondaryColor: string | null;
    icon: string | null;
    iconFilename: string | null;
}

interface AuthState {
    token: string | null;
    tenantId: string | null;
    tenantName: string | null;
    identityId: string | null;
    hierarchy: Record<number, string> | null;
    branding: Branding;
    user: any | null;
    availableTenants: TenantOption[];
    setAuth: (token: string, tenantId: string, tenantName?: string) => void;
    setAvailableTenants: (tenants: TenantOption[]) => void;
    setHierarchy: (hierarchy: Record<number, string>) => void;
    setBranding: (branding: Branding) => void;
    setTenantName: (name: string) => void;
    switchTenant: (tenantId: string) => Promise<void>;
    fetchAvailableTenants: () => Promise<void>;
    logout: () => void;
}

function applyBrandingColors(branding: Branding) {
    if (branding.primaryColor) {
        document.documentElement.style.setProperty('--color-brand-primary', branding.primaryColor);
    } else {
        document.documentElement.style.removeProperty('--color-brand-primary');
    }
    if (branding.secondaryColor) {
        document.documentElement.style.setProperty('--color-brand-secondary', branding.secondaryColor);
    } else {
        document.documentElement.style.removeProperty('--color-brand-secondary');
    }
}

const defaultBranding: Branding = { primaryColor: null, secondaryColor: null, icon: null, iconFilename: null };

function loadBranding(): Branding {
    const stored = localStorage.getItem('tenant_branding');
    if (stored) {
        try {
            const parsed = JSON.parse(stored);
            applyBrandingColors(parsed);
            return parsed;
        } catch { /* ignore */ }
    }
    return defaultBranding;
}

export const useAuthStore = create<AuthState>((set) => ({
    token: localStorage.getItem('token'),
    tenantId: localStorage.getItem('tenant_id'),
    tenantName: localStorage.getItem('tenant_name'),
    identityId: localStorage.getItem('identity_id'),
    hierarchy: localStorage.getItem('tenant_hierarchy') ? JSON.parse(localStorage.getItem('tenant_hierarchy')!) : null,
    branding: loadBranding(),
    user: localStorage.getItem('token') ? jwtDecode(localStorage.getItem('token')!) : null,
    availableTenants: localStorage.getItem('available_tenants') ? JSON.parse(localStorage.getItem('available_tenants')!) : [],

    setAuth: (token, tenantId, tenantName) => {
        localStorage.setItem('token', token);
        localStorage.setItem('tenant_id', tenantId);
        if (tenantName) localStorage.setItem('tenant_name', tenantName);

        const decoded: any = jwtDecode(token);
        if (decoded.identity_id) {
            localStorage.setItem('identity_id', decoded.identity_id);
        }

        set({
            token,
            tenantId,
            tenantName: tenantName || null,
            identityId: decoded.identity_id || null,
            user: decoded,
        });
    },

    setAvailableTenants: (tenants) => {
        localStorage.setItem('available_tenants', JSON.stringify(tenants));
        set({ availableTenants: tenants });
    },

    setHierarchy: (hierarchy) => {
        localStorage.setItem('tenant_hierarchy', JSON.stringify(hierarchy));
        set({ hierarchy });
    },

    setBranding: (branding) => {
        localStorage.setItem('tenant_branding', JSON.stringify(branding));
        applyBrandingColors(branding);
        set({ branding });
    },

    setTenantName: (name) => {
        localStorage.setItem('tenant_name', name);
        set({ tenantName: name });
    },

    switchTenant: async (tenantId: string) => {
        try {
            const response = await api.post('/auth/switch-tenant', { new_tenant_id: tenantId });
            const { access_token, tenant_id, tenant_name } = response.data;

            localStorage.setItem('token', access_token);
            localStorage.setItem('tenant_id', tenant_id);
            localStorage.setItem('tenant_name', tenant_name);
            localStorage.removeItem('tenant_hierarchy');
            localStorage.removeItem('tenant_branding');

            const decoded: any = jwtDecode(access_token);

            document.documentElement.style.removeProperty('--color-brand-primary');
            document.documentElement.style.removeProperty('--color-brand-secondary');

            set({
                token: access_token,
                tenantId: tenant_id,
                tenantName: tenant_name,
                identityId: decoded.identity_id || null,
                user: decoded,
                hierarchy: null,
                branding: defaultBranding,
            });

            window.location.href = '/';
        } catch (error) {
            console.error('Failed to switch tenant:', error);
            throw error;
        }
    },

    fetchAvailableTenants: async () => {
        try {
            const response = await api.get('/auth/tenants');
            const tenants = response.data.map((t: any) => ({
                tenant_id: t.tenant_id,
                tenant_name: t.tenant_name,
            }));
            localStorage.setItem('available_tenants', JSON.stringify(tenants));
            set({ availableTenants: tenants });
        } catch (error) {
            console.error('Failed to fetch available tenants:', error);
        }
    },

    logout: () => {
        localStorage.removeItem('token');
        localStorage.removeItem('tenant_id');
        localStorage.removeItem('tenant_name');
        localStorage.removeItem('tenant_hierarchy');
        localStorage.removeItem('identity_id');
        localStorage.removeItem('available_tenants');
        localStorage.removeItem('tenant_branding');

        document.documentElement.style.removeProperty('--color-brand-primary');
        document.documentElement.style.removeProperty('--color-brand-secondary');

        set({
            token: null,
            tenantId: null,
            tenantName: null,
            identityId: null,
            hierarchy: null,
            branding: defaultBranding,
            user: null,
            availableTenants: [],
        });
    },
}));
