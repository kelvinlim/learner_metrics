import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './store/authStore';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import UnitManagement from './pages/UnitManagement';
import UserManagement from './pages/UserManagement';
import NIHGrantsPage from './pages/NIHGrantsPage';
import PublicationsPage from './pages/PublicationsPage';
import DashboardLayout from './components/DashboardLayout';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
    const token = useAuthStore((s) => s.token);
    if (!token) return <Navigate to="/login" replace />;
    return <DashboardLayout>{children}</DashboardLayout>;
}

export default function App() {
    return (
        <BrowserRouter basename={import.meta.env.VITE_BASE_PATH || '/'}>
            <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
                <Route path="/units" element={<ProtectedRoute><UnitManagement /></ProtectedRoute>} />
                <Route path="/users" element={<ProtectedRoute><UserManagement /></ProtectedRoute>} />
                <Route path="/grants" element={<ProtectedRoute><NIHGrantsPage /></ProtectedRoute>} />
                <Route path="/publications" element={<ProtectedRoute><PublicationsPage /></ProtectedRoute>} />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </BrowserRouter>
    );
}
