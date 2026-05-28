import React from "react";

export default function PageHeader({ eyebrow, title, subtitle, children }) {
    return (
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 mb-8 fade-in">
            <div>
                {eyebrow && <div className="label-tiny mb-2">{eyebrow}</div>}
                <h1
                    className="font-serif font-light tracking-tight"
                    style={{ fontSize: "clamp(2rem, 4vw, 3rem)", color: "var(--text-primary)", lineHeight: 1.05 }}
                >
                    {title}
                </h1>
                {subtitle && (
                    <p className="mt-2 text-sm md:text-base" style={{ color: "var(--text-secondary)", maxWidth: "60ch" }}>
                        {subtitle}
                    </p>
                )}
            </div>
            {children && <div className="flex gap-2 flex-wrap">{children}</div>}
        </div>
    );
}
