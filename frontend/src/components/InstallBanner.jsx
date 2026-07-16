import React, { useEffect, useState } from "react";
import { X, ShareNetwork, Plus } from "@phosphor-icons/react";

/**
 * iOS Home Screen install prompt.
 *
 * iOS Safari doesn't fire beforeinstallprompt like Android/Chrome, so we have to
 * teach the user manually: "Share → Add to Home Screen". We only show this when:
 *   • the user is on iOS Safari (heuristic)
 *   • the app isn't already running standalone (already installed)
 *   • the user hasn't dismissed this banner before
 *
 * Zero cost if not applicable — the component just returns null.
 */
export default function InstallBanner() {
    const [visible, setVisible] = useState(false);

    useEffect(() => {
        const ua = window.navigator.userAgent;
        const isIOS = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
        // Skip if already installed (standalone or fullscreen).
        const standalone =
            (window.navigator && window.navigator.standalone) ||
            window.matchMedia("(display-mode: standalone)").matches ||
            window.matchMedia("(display-mode: fullscreen)").matches;
        if (!isIOS || standalone) return;
        try {
            if (localStorage.getItem("russell.install_dismissed") === "1") return;
        } catch { /* noop */ }
        // Slight delay so it doesn't slap in front of first paint.
        const t = setTimeout(() => setVisible(true), 1500);
        return () => clearTimeout(t);
    }, []);

    const dismiss = () => {
        try { localStorage.setItem("russell.install_dismissed", "1"); } catch { /* noop */ }
        setVisible(false);
    };

    if (!visible) return null;

    return (
        <div
            className="md:hidden fixed inset-x-3 z-40 rounded-2xl shadow-xl fade-in"
            style={{
                bottom: "calc(80px + env(safe-area-inset-bottom))",
                background: "rgba(13, 10, 8, 0.96)",
                border: "1px solid var(--accent)",
                backdropFilter: "blur(18px)",
            }}
            data-testid="ios-install-banner"
        >
            <div className="p-4 pr-10 relative">
                <button
                    onClick={dismiss}
                    className="absolute top-2 right-2 p-2"
                    aria-label="Dismiss"
                    data-testid="install-banner-dismiss"
                    style={{ color: "var(--text-secondary)" }}
                >
                    <X size={16} weight="bold" />
                </button>
                <div className="flex items-center gap-3 mb-2">
                    <span className="brand-mark" style={{ width: 32, height: 32 }} />
                    <div>
                        <div className="font-serif text-lg leading-tight" style={{ color: "var(--text-primary)" }}>
                            Install Russell
                        </div>
                        <div className="label-tiny" style={{ color: "var(--accent)" }}>Add to Home Screen</div>
                    </div>
                </div>
                <div className="text-sm mb-1" style={{ color: "var(--text-secondary)" }}>
                    Tap <ShareNetwork size={14} className="inline align-text-bottom mx-1" /> below,
                    then <span style={{ color: "var(--text-primary)" }}>“Add to Home Screen”</span>
                    <Plus size={12} className="inline align-text-bottom ml-1" />.
                </div>
            </div>
        </div>
    );
}
