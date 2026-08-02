import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
    ChatCircleDots,
    BookOpen,
    Wrench,
    Users,
    Brain,
    Package,
    Phone,
    Stack,
    Coffee,
    DotsThree,
    FilmSlate,
} from "@phosphor-icons/react";
import { useServiceMode } from "@/context/ServiceModeContext";

// Full nav for desktop and the mobile "More" drawer.
const NAV = [
    { to: "/", label: "Chat", icon: ChatCircleDots, end: true, testid: "nav-chat" },
    { to: "/cocktails", label: "Library", icon: BookOpen, testid: "nav-cocktails" },
    { to: "/tools", label: "Tools", icon: Wrench, testid: "nav-tools" },
    { to: "/inventory", label: "Bar", icon: Package, testid: "nav-inventory" },
    { to: "/regulars", label: "Regulars", icon: Users, testid: "nav-regulars" },
    { to: "/collections", label: "Crates", icon: Stack, testid: "nav-collections" },
    { to: "/studio", label: "Studio", icon: FilmSlate, testid: "nav-studio" },
    { to: "/memory", label: "Memory", icon: Brain, testid: "nav-memory" },
    { to: "/phone", label: "Phone", icon: Phone, testid: "nav-phone" },
];

// Bottom tab bar shows only the 4 most-used; rest live behind the "More" sheet.
const BOTTOM_TABS = ["/", "/cocktails", "/inventory", "/regulars"];

export default function Topbar() {
    const { serviceMode, toggle } = useServiceMode();
    const location = useLocation();
    const [moreOpen, setMoreOpen] = React.useState(false);

    // Close "More" sheet whenever route changes.
    React.useEffect(() => { setMoreOpen(false); }, [location.pathname]);

    const bottomItems = NAV.filter((n) => BOTTOM_TABS.includes(n.to));
    const moreItems = NAV.filter((n) => !BOTTOM_TABS.includes(n.to));

    return (
        <>
            <header className="topbar" data-testid="topbar">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 sm:py-4 flex items-center justify-between gap-3">
                    <NavLink to="/" className="flex items-center gap-3 group" data-testid="brand-link">
                        <span className="brand-mark" />
                        <div className="flex flex-col leading-tight">
                            <span className="font-serif text-xl sm:text-2xl tracking-tight" style={{ color: "var(--text-primary)" }}>
                                Russell
                            </span>
                            <span className="label-tiny hidden sm:block">behind the stick</span>
                        </div>
                    </NavLink>

                    {/* Desktop nav */}
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

                    <button
                        onClick={toggle}
                        className={`service-mode-toggle ${serviceMode ? "is-on" : ""}`}
                        title={serviceMode ? "Switch back to standard view" : "Bigger fonts for behind the bar"}
                        aria-pressed={serviceMode}
                        data-testid="service-mode-toggle"
                    >
                        <Coffee size={14} weight={serviceMode ? "fill" : "bold"} />
                        <span className="hidden sm:inline">{serviceMode ? "Service" : "Service mode"}</span>
                    </button>
                </div>
            </header>

            {/* Mobile bottom tab bar */}
            <nav className="bottom-nav md:hidden" data-testid="mobile-bottom-nav">
                {bottomItems.map(({ to, label, icon: Icon, end, testid }) => (
                    <NavLink
                        key={to}
                        to={to}
                        end={end}
                        className={({ isActive }) => `bottom-tab ${isActive ? "active" : ""}`}
                        data-testid={`mobile-${testid}`}
                    >
                        <Icon size={22} weight="regular" />
                        <span>{label}</span>
                    </NavLink>
                ))}
                <button
                    className={`bottom-tab ${moreOpen ? "active" : ""}`}
                    onClick={() => setMoreOpen((v) => !v)}
                    data-testid="mobile-more-btn"
                    aria-label="More"
                >
                    <DotsThree size={26} weight="bold" />
                    <span>More</span>
                </button>
            </nav>

            {/* "More" bottom sheet */}
            {moreOpen && (
                <div
                    className="md:hidden fixed inset-0 z-40"
                    style={{ background: "rgba(0,0,0,0.55)", backdropFilter: "blur(6px)" }}
                    onClick={() => setMoreOpen(false)}
                >
                    <div
                        className="absolute bottom-0 left-0 right-0 glass-strong rounded-t-2xl p-4"
                        style={{ paddingBottom: "calc(1rem + env(safe-area-inset-bottom))" }}
                        onClick={(e) => e.stopPropagation()}
                        data-testid="mobile-more-sheet"
                    >
                        <div className="grid grid-cols-2 gap-2">
                            {moreItems.map(({ to, label, icon: Icon, end, testid }) => (
                                <NavLink
                                    key={to}
                                    to={to}
                                    end={end}
                                    className={({ isActive }) =>
                                        `flex items-center gap-3 px-4 py-3 rounded-xl ${isActive ? "active" : ""}`
                                    }
                                    style={{
                                        border: "1px solid var(--border-subtle)",
                                        background: "rgba(255,255,255,0.02)",
                                        color: "var(--text-primary)",
                                    }}
                                    data-testid={`mobile-more-${testid}`}
                                >
                                    <Icon size={20} weight="bold" style={{ color: "var(--accent)" }} />
                                    <span className="font-serif text-lg">{label}</span>
                                </NavLink>
                            ))}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
