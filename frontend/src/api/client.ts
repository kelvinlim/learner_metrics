import axios from 'axios';

const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL || '/api',
});

api.interceptors.request.use((config) => {
    const token = localStorage.getItem('token');
    const tenantId = localStorage.getItem('tenant_id');

    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }

    if (tenantId) {
        config.headers['X-Tenant-ID'] = tenantId;
    }

    return config;
});

api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem('token');
            localStorage.removeItem('tenant_id');
            localStorage.removeItem('tenant_name');
            if (window.location.pathname !== '/login' && window.location.pathname !== '/') {
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
);

// ---- Auth types ----

export interface TenantOption {
    tenant_id: string;
    tenant_name: string;
}

export interface GoogleIdentifyResponse {
    identity_id: string;
    tenants: TenantOption[];
}

export interface GoogleAuthenticateResponse {
    access_token: string;
    token_type: string;
    tenant_id: string;
    tenant_name: string;
}

// ---- Auth API calls ----

export const googleIdentify = (googleToken: string) =>
    api.post<GoogleIdentifyResponse>('/auth/google/identify', { token: googleToken });

export const googleAuthenticate = (identityId: string, tenantId: string) =>
    api.post<GoogleAuthenticateResponse>('/auth/google/authenticate', {
        identity_id: identityId,
        tenant_id: tenantId,
    });

export const switchTenant = (newTenantId: string) =>
    api.post('/auth/switch-tenant', { new_tenant_id: newTenantId });

export const devLogin = (email: string) =>
    api.post<GoogleIdentifyResponse>('/auth/dev-login', { email });

export const getAvailableTenants = () =>
    api.get<TenantOption[]>('/auth/tenants');

export const getCurrentUser = () =>
    api.get('/users/me');

// ---- User types ----

export interface UserSummary {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    unit_id: string | null;
    is_active: boolean;
    is_covered_investigator: boolean;
    nih_profile_id: number | null;
    nih_reporter_last_updated: string | null;
    orcid_id: string | null;
    pubmed_query: string | null;
}

export interface UserListResponse {
    total: number;
    offset: number;
    limit: number;
    items: UserSummary[];
}

export const getUsers = (params?: { search?: string; unit_id?: string; limit?: number; offset?: number }) =>
    api.get<UserListResponse>('/users', { params });

// ---- NIH types ----

export interface NIHProfileResult {
    full_name: string;
    profile_id: number;
    org: string;
}

export interface NIHProject {
    id: string;
    appl_id: number;
    project_title: string;
    project_num: string;
    core_project_num: string;
    fiscal_year: number;
    total_costs: number;
    direct_costs: number;
    indirect_costs: number;
    project_start_date: string | null;
    project_end_date: string | null;
    user_id: string;
}

export interface NIHProjectsResponse {
    total: number;
    offset: number;
    limit: number;
    items: NIHProject[];
}

// ---- NIH API calls ----

export const nihLookup = (firstName: string, lastName: string, state?: string) =>
    api.get<NIHProfileResult[]>('/nih/lookup', {
        params: { first_name: firstName, last_name: lastName, state },
    });

export const assignNIHProfile = (userId: string, profileId: number) =>
    api.post(`/users/${userId}/assign-nih-profile`, null, {
        params: { profile_id: profileId },
    });

export const syncNIHProjects = (userId: string) =>
    api.post(`/users/${userId}/sync-nih-projects`);

export const syncAllNIHProjects = () =>
    api.post('/users/sync-all-nih-projects');

export const getNIHProjects = (params?: {
    user_id?: string;
    search?: string;
    fiscal_year?: number;
    active_only?: boolean;
    limit?: number;
    offset?: number;
}) =>
    api.get<NIHProjectsResponse>('/nih/projects', { params });

// ---- ORCID types ----

export interface ORCIDResult {
    orcid_id: string;
    name: string;
    affiliation: string;
}

// ---- ORCID API calls ----

export const orcidSearch = (firstName: string, lastName: string, institution?: string) =>
    api.get<ORCIDResult[]>('/orcid/search', {
        params: { first_name: firstName, last_name: lastName, institution },
    });

export const assignORCID = (userId: string, orcidId: string) =>
    api.put(`/users/${userId}/orcid`, null, { params: { orcid_id: orcidId } });

export const syncORCID = (userId: string) =>
    api.post(`/users/${userId}/sync-orcid`);

export const syncAllORCID = () =>
    api.post('/users/sync-all-orcid');

// ---- PubMed API calls ----

export const testPubMedQuery = (query: string) =>
    api.post<{ count: number; sample: PublicationItem[] }>('/pubmed/test-query', { query });

export const syncPubMed = (userId: string) =>
    api.post(`/users/${userId}/sync-pubmed`);

export const syncAllPubMed = () =>
    api.post('/users/sync-all-pubmed');

// ---- Publication types ----

export interface PublicationItem {
    id: string;
    user_id: string;
    title: string;
    journal: string | null;
    pub_year: number | null;
    pub_date: string | null;
    authors: string | null;
    doi: string | null;
    pmid: string | null;
    source: 'orcid' | 'pubmed' | 'both' | 'manual';
    orcid_put_code: string | null;
}

export interface PublicationsResponse {
    total: number;
    offset: number;
    limit: number;
    items: PublicationItem[];
}

// ---- Publication API calls ----

export const getPublications = (params?: {
    user_id?: string;
    source?: string;
    year_from?: number;
    year_to?: number;
    search?: string;
    limit?: number;
    offset?: number;
}) =>
    api.get<PublicationsResponse>('/publications', { params });

// ---- Metrics ----

export interface MetricsSummary {
    users: number;
    investigators: number;
    grants: number;
    publications: number;
    nih_linked: number;
    orcid_linked: number;
}

export const getMetricsSummary = () =>
    api.get<MetricsSummary>('/metrics/summary');

export default api;
