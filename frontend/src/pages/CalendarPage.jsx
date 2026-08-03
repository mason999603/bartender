import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Toaster, toast } from "sonner";
import {
    CalendarBlank,
    Plus,
    ArrowClockwise,
    Trash,
    Briefcase,
    House,
    Warning,
} from "@phosphor-icons/react";

const CATEGORY_STYLES = {
    shift:           { color: "#FCA5A5", label: "Shift" },
    travel_vacation: { color: "#FBBF24", label: "Travel" },
    ceremony:        { color: "#FBBF24", label: "Ceremony" },
    paid_ticket:     { color: "#E09132", label: "Ticket" },
    medical:         { color: "#FCA5A5", label: "Medical" },
    birthday:        { color: "#E09132", label: "Birthday" },
    appointment:     { color: "#D4A574", label: "Appointment" },
    personal:        { color: "#D4A574", label: "Personal" },
    meeting:         { color: "#A0937D", label: "Meeting" },
    routine:         { color: "#7A6E5C", label: "Routine" },
    reminder:        { color: "#7A6E5C", label: "Reminder" },
    ordinary:        { color: "#7A6E5C", label: "Ordinary" },
};

function fmtWhen(iso) {
    try {
        const d = new Date(iso);
        return d.toLocaleString(undefined, {
            weekday: "short",
            day: "numeric",
            month: "short",
            hour: "numeric",
            minute: "2-digit",
        });
    } catch {
        return iso;
    }
}

function groupByDay(events) {
    const buckets = new Map();
    for (const ev of events) {
        const key = (ev.start || "").slice(0, 10);
        if (!buckets.has(key)) buckets.set(key, []);
        buckets.get(key).push(ev);
    }
    // Sort inside each day by start time
    for (const arr of buckets.values()) arr.sort((a, b) => a.start.localeCompare(b.start));
    // Sort day keys ascending
    return [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b));
}

export default function CalendarPage() {
    const [sources, setSources] = useState([]);
    const [events, setEvents] = useState([]);
    const [days, setDays] = useState(7);
    const [loading, setLoading] = useState(false);
    const [showAdd, setShowAdd] = useState(false);
    const [newName, setNewName] = useState("");
    const [newUrl, setNewUrl] = useState("");
    const [newIsWork, setNewIsWork] = useState(false);

    const load = async () => {
        try {
            const r = await api.get(`/calendar/upcoming?days=${days}`);
            setSources(r.data.sources || []);
            setEvents(r.data.events || []);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Load failed");
        }
    };

    useEffect(() => {
        load();
    }, [days]);

    const refresh = async () => {
        setLoading(true);
        try {
            await api.post("/calendar/refresh");
            toast.success("Calendars refreshed");
            load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Refresh failed");
        } finally {
            setLoading(false);
        }
    };

    const addSource = async () => {
        if (!newName.trim() || !newUrl.trim()) return toast.error("Name + URL required");
        try {
            await api.post("/calendar/sources", {
                name: newName.trim(),
                url: newUrl.trim(),
                is_work: newIsWork,
            });
            setNewName("");
            setNewUrl("");
            setNewIsWork(false);
            setShowAdd(false);
            toast.success("Calendar added — fetching events...");
            setTimeout(load, 2500);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Add failed");
        }
    };

    const removeSource = async (id) => {
        try {
            await api.delete(`/calendar/sources/${id}`);
            toast.success("Removed");
            load();
        } catch {
            toast.error("Remove failed");
        }
    };

    const grouped = groupByDay(events);

    return (
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8" data-testid="calendar-page">
            <Toaster position="top-center" theme="dark" />
            <PageHeader
                eyebrow="Calendar"
                title="What's on the roster"
                subtitle="Russell reads your iCloud calendars and ranks what actually matters."
            />

            {/* ── Sources ─────────────────────────────────────────── */}
            <section className="mb-8">
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                        <CalendarBlank size={18} weight="fill" style={{ color: "var(--accent)" }} />
                        <span className="label-tiny">Connected calendars</span>
                    </div>
                    <div className="flex gap-2">
                        <button
                            className="btn-ghost text-sm"
                            onClick={refresh}
                            disabled={loading}
                            data-testid="cal-refresh"
                        >
                            <ArrowClockwise
                                size={12}
                                weight="bold"
                                className={`inline mr-1 ${loading ? "animate-spin" : ""}`}
                            />
                            Refresh
                        </button>
                        <button
                            className="btn-amber text-sm"
                            onClick={() => setShowAdd((v) => !v)}
                            data-testid="cal-add-toggle"
                        >
                            <Plus size={12} weight="bold" className="inline mr-1" />
                            Add calendar
                        </button>
                    </div>
                </div>

                {showAdd && (
                    <div className="tool-card mb-3" data-testid="cal-add-form">
                        <input
                            className="input-dark w-full mb-2"
                            placeholder="Name (e.g. Work Shifts, Family)"
                            value={newName}
                            onChange={(e) => setNewName(e.target.value)}
                            data-testid="cal-add-name"
                        />
                        <input
                            className="input-dark w-full mb-2"
                            placeholder="webcal:// or https:// .ics URL"
                            value={newUrl}
                            onChange={(e) => setNewUrl(e.target.value)}
                            data-testid="cal-add-url"
                        />
                        <label className="flex items-center gap-2 text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
                            <input
                                type="checkbox"
                                checked={newIsWork}
                                onChange={(e) => setNewIsWork(e.target.checked)}
                                data-testid="cal-add-iswork"
                            />
                            <span>This is my work calendar (unknown long events → treat as shifts)</span>
                        </label>
                        <div className="flex gap-2">
                            <button className="btn-amber text-sm" onClick={addSource} data-testid="cal-add-save">
                                Save
                            </button>
                            <button
                                className="btn-ghost text-sm"
                                onClick={() => setShowAdd(false)}
                                data-testid="cal-add-cancel"
                            >
                                Cancel
                            </button>
                        </div>
                        <div className="text-xs mt-3" style={{ color: "var(--text-muted)" }}>
                            <b>Where do I get this URL?</b> In Apple Calendar → right-click any calendar → <b>Share Calendar → Public Calendar</b> → copy URL. Or on iCloud.com: Settings → Publish. On Google Calendar: Settings → Integrate calendar → <b>Public URL in iCal format</b>.
                        </div>
                    </div>
                )}

                <div className="grid sm:grid-cols-2 gap-2">
                    {sources.length === 0 && (
                        <div className="tool-card text-sm" style={{ color: "var(--text-muted)" }}>
                            No calendars connected yet.
                        </div>
                    )}
                    {sources.map((s) => (
                        <div
                            key={s.id}
                            className="tool-card flex items-center justify-between gap-3"
                            data-testid={`cal-source-${s.id}`}
                        >
                            <div className="flex items-center gap-2 min-w-0">
                                {s.is_work ? (
                                    <Briefcase
                                        size={16}
                                        weight="fill"
                                        style={{ color: "var(--accent)" }}
                                    />
                                ) : (
                                    <House size={16} weight="fill" style={{ color: "var(--accent)" }} />
                                )}
                                <div className="min-w-0">
                                    <div
                                        className="font-serif truncate"
                                        style={{ color: "var(--accent)" }}
                                    >
                                        {s.name}
                                    </div>
                                    <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                                        {s.last_event_count === null
                                            ? "fetching..."
                                            : `${s.last_event_count} event${s.last_event_count === 1 ? "" : "s"}`}
                                        {s.last_error && (
                                            <>
                                                {" · "}
                                                <span style={{ color: "#FCA5A5" }}>
                                                    <Warning size={10} weight="fill" className="inline" />{" "}
                                                    {s.last_error}
                                                </span>
                                            </>
                                        )}
                                    </div>
                                </div>
                            </div>
                            <button
                                onClick={() => removeSource(s.id)}
                                className="btn-ghost text-sm"
                                data-testid={`cal-remove-${s.id}`}
                            >
                                <Trash size={12} weight="bold" />
                            </button>
                        </div>
                    ))}
                </div>
            </section>

            {/* ── Horizon ──────────────────────────────────────────── */}
            <div className="flex items-center gap-2 mb-4">
                <span className="label-tiny">Show</span>
                {[1, 7, 14, 30].map((d) => (
                    <button
                        key={d}
                        onClick={() => setDays(d)}
                        className={`nav-link ${days === d ? "active" : ""}`}
                        data-testid={`cal-days-${d}`}
                    >
                        {d === 1 ? "Today" : d === 7 ? "This week" : d === 14 ? "2 weeks" : "This month"}
                    </button>
                ))}
                <span className="text-xs ml-auto" style={{ color: "var(--text-muted)" }}>
                    {events.length} event{events.length === 1 ? "" : "s"} ranked
                </span>
            </div>

            {/* ── Grouped events ───────────────────────────────────── */}
            {grouped.length === 0 ? (
                <div className="tool-card text-sm" style={{ color: "var(--text-muted)" }}>
                    Nothing scheduled in this window. Ask Russell: &quot;run down my week for me&quot;.
                </div>
            ) : (
                <div className="space-y-6" data-testid="cal-events">
                    {grouped.map(([day, dayEvents]) => (
                        <div key={day}>
                            <div
                                className="font-serif text-lg mb-2"
                                style={{ color: "var(--accent)" }}
                            >
                                {new Date(day + "T00:00:00").toLocaleDateString(undefined, {
                                    weekday: "long",
                                    day: "numeric",
                                    month: "long",
                                })}
                            </div>
                            <div className="space-y-2">
                                {dayEvents.map((ev) => {
                                    const style = CATEGORY_STYLES[ev.category] || CATEGORY_STYLES.ordinary;
                                    return (
                                        <div
                                            key={ev.uid}
                                            className="tool-card flex items-start gap-3"
                                            style={{
                                                borderLeft: `3px solid ${style.color}`,
                                            }}
                                            data-testid={`cal-event-${ev.uid}`}
                                        >
                                            <div className="min-w-0 flex-1">
                                                <div className="flex items-center gap-2 mb-1 flex-wrap">
                                                    <span
                                                        className="text-xs font-mono px-2 py-0.5 rounded"
                                                        style={{
                                                            background: "rgba(0,0,0,0.4)",
                                                            color: style.color,
                                                        }}
                                                    >
                                                        {ev.priority}/10 · {style.label}
                                                    </span>
                                                    <span
                                                        className="text-xs"
                                                        style={{ color: "var(--text-muted)" }}
                                                    >
                                                        {ev.source_name}
                                                    </span>
                                                </div>
                                                <div
                                                    className="text-base font-medium"
                                                    style={{ color: "var(--text-primary)" }}
                                                >
                                                    {ev.summary || "(no title)"}
                                                </div>
                                                <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                                                    {fmtWhen(ev.start)}
                                                    {ev.location ? ` · ${ev.location}` : ""}
                                                    {ev.all_day ? " · all day" : ""}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
