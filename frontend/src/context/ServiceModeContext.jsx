import React, { createContext, useContext, useEffect, useState } from "react";

/**
 * Service Mode — a one-toggle "behind the bar" view.
 *
 * When active, the html element gets a `service-mode` class. Pages opt in via
 * CSS in index.css that scales typography, expands tap targets, and trims
 * dense content (chip filters, secondary sidebars) so glances are fast even
 * with one hand wet and the other on a tin.
 *
 * Persisted in localStorage so it survives reloads — once you put Russell into
 * service mode for the night, you don't want to flip it back every refresh.
 */
const ServiceModeContext = createContext({ serviceMode: false, toggle: () => { } });

export function ServiceModeProvider({ children }) {
    const [serviceMode, setServiceMode] = useState(() => {
        try {
            return localStorage.getItem("russell.service_mode") === "1";
        } catch {
            return false;
        }
    });

    useEffect(() => {
        const cls = "service-mode";
        const root = document.documentElement;
        if (serviceMode) root.classList.add(cls);
        else root.classList.remove(cls);
        try {
            localStorage.setItem("russell.service_mode", serviceMode ? "1" : "0");
        } catch {
            /* noop */
        }
    }, [serviceMode]);

    const toggle = () => setServiceMode((v) => !v);

    return (
        <ServiceModeContext.Provider value={{ serviceMode, toggle }}>
            {children}
        </ServiceModeContext.Provider>
    );
}

export function useServiceMode() {
    return useContext(ServiceModeContext);
}
