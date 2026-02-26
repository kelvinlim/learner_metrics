import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
    LayoutDashboard,
    GitMerge,
    Users,
    FlaskConical,
    BookOpen,
    LogOut,
    ChevronDown,
} from 'lucide-react';
import { useAuthStore } from '../store/authStore';

interface NavItemProps {
    to: string;
    icon: React.ReactNode;
    label: string;
}

function NavItem({ to, icon, label }: NavItemProps) {
    return (
        <NavLink
            to={to}
            className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                        ? 'bg-brand-primary text-white'
                        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                }`
            }
        >
            {icon}
            {label}
        </NavLink>
    );
}

interface Props {
    children: React.ReactNode;
}

export default function DashboardLayout({ children }: Props) {
    const { tenantName, logout } = useAuthStore();
    const navigate = useNavigate();

    function handleLogout() {
        logout();
        navigate('/login');
    }

    return (
        <div className="flex h-screen bg-gray-50">
            {/* Sidebar */}
            <aside className="w-56 bg-white border-r border-gray-200 flex flex-col">
                {/* Brand */}
                <div className="px-4 py-5 border-b border-gray-100">
                    <h1 className="text-base font-bold text-brand-primary">Learner Metrics</h1>
                    {tenantName && (
                        <p className="text-xs text-gray-500 truncate mt-0.5">{tenantName}</p>
                    )}
                </div>

                {/* Nav */}
                <nav className="flex-1 px-3 py-4 space-y-1">
                    <NavItem to="/" icon={<LayoutDashboard className="h-4 w-4" />} label="Dashboard" />
                    <NavItem to="/units" icon={<GitMerge className="h-4 w-4" />} label="Units" />
                    <NavItem to="/users" icon={<Users className="h-4 w-4" />} label="Investigators" />
                    <NavItem to="/grants" icon={<FlaskConical className="h-4 w-4" />} label="NIH Grants" />
                    <NavItem to="/publications" icon={<BookOpen className="h-4 w-4" />} label="Publications" />
                </nav>

                {/* Footer */}
                <div className="px-3 py-4 border-t border-gray-100">
                    <button
                        onClick={handleLogout}
                        className="flex items-center gap-3 px-3 py-2 w-full rounded-lg text-sm text-gray-600 hover:bg-gray-100 hover:text-gray-900 transition-colors"
                    >
                        <LogOut className="h-4 w-4" />
                        Sign out
                    </button>
                </div>
            </aside>

            {/* Main */}
            <main className="flex-1 overflow-auto">
                <div className="max-w-6xl mx-auto px-6 py-8">
                    {children}
                </div>
            </main>
        </div>
    );
}
