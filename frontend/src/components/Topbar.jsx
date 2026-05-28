import React from "react";
import { NavLink } from "react-router-dom";
import { ChatCircleDots, BookOpen, Wrench, Users, Brain, Package, Phone, Stack } from "@phosphor-icons/react";

const NAV = [
    { to: "/", label: "Chat", icon: ChatCircleDots, end: true, testid: "nav-chat" },
    { to: "/cocktails", label: "Library", icon: BookOpen, testid: "nav-cocktails" },
    { to: "/tools", label: "Tools", icon: Wrench, testid: "nav-tools" },
    { to: "/inventory", label: "Bar", icon: Package, testid: "nav-inventory" },
    { to: "/regulars", label: "Regulars", icon: Users, testid: "nav-regulars" },
    { to: "/collections", label: "Crates", icon: Stack, testid: "nav-collections" },
    { to: "/memory", label: "Memory", icon: Brain, testid: "nav-memory" },
    { to: "/phone", label: "Phone", icon: Phone, testid: "nav-phone" },
];

export default function Topbar() {
    return (
        <header className="topbar" data-testid="topbar">
            <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between gap-6">
                <NavLink to="/" className="flex items-center gap-3 group" data-testid="brand-link">
                    <span className="brand-mark" />
                    <div className="flex flex-col leading-tight">
                        <span className="font-serif text-2xl tracking-tight" style={{ color: "var(--text-primary)" }}>
                            Russell
                        </span>
                        <span className="label-tiny">behind the stick</span>
                    </div>
                </NavLink>

                <nav className="hidden md:flex items-center gap-1">
                    {NAV.map(({ to, label, icon: Icon, end, testid }) => (
                        <NavLink
                            key={to}
                            to={to}
                            end={end}
                            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
                            data-testid={testid}
                        >
                            <Icon size={16} weight="bold" />
                            {label}
                        </NavLink>
                    ))}
                </nav>
            </div>

            {/* Mobile nav */}
            <nav className="md:hidden flex overflow-x-auto px-4 pb-2 gap-1 border-t border-white/5">
                {NAV.map(({ to, label, icon: Icon, end, testid }) => (
                    <NavLink
                        key={to}
                        to={to}
                        end={end}
                        className={({ isActive }) => `nav-link whitespace-nowrap ${isActive ? "active" : ""}`}
                        data-testid={`mobile-${testid}`}
                    >
                        <Icon size={14} weight="bold" />
                        {label}
                    </NavLink>
                ))}
            </nav>
        </header>
    );
}
