import React, { useState, useEffect, useRef } from "react";
import { api, API } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Toaster, toast } from "sonner";
import {
    FilmSlate,
    Lightbulb,
    ArrowRight,
    SpeakerHigh,
    FloppyDisk,
    Trash,
    Copy,
    Play,
    Pause,
    ArrowClockwise,
} from "@phosphor-icons/react";

const PLATFORMS = [
    { key: "tiktok", label: "TikTok" },
    { key: "youtube-shorts", label: "YT Shorts" },
    { key: "youtube-long", label: "YT Long" },
    { key: "both", label: "Both" },
];

export default function StudioPage() {
    const [topic, setTopic] = useState("");
    const [count, setCount] = useState(5);
    const [loadingIdeas, setLoadingIdeas] = useState(false);
    const [ideas, setIdeas] = useState([]);

    const [selectedIdea, setSelectedIdea] = useState(null);
    const [platform, setPlatform] = useState("tiktok");
    const [loadingScript, setLoadingScript] = useState(false);
    const [script, setScript] = useState("");

    const [saved, setSaved] = useState([]);
    const [saving, setSaving] = useState(false);
    const scriptRef = useRef(null);

    const loadSaved = async () => {
        try {
            const r = await api.get("/studio/scripts");
            setSaved(r.data || []);
        } catch {
            /* ignore */
        }
    };

    useEffect(() => {
        loadSaved();
    }, []);

    const generateIdeas = async () => {
        if (!topic.trim()) return toast.error("Give Russell a topic first");
        setLoadingIdeas(true);
        setIdeas([]);
        try {
            const r = await api.post("/studio/ideas", { topic, count });
            setIdeas(r.data?.ideas || []);
            if (!(r.data?.ideas || []).length) toast.error("Russell drew a blank. Try a different angle.");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Idea generation failed");
        } finally {
            setLoadingIdeas(false);
        }
    };

    const chooseIdea = async (idea) => {
        setSelectedIdea(idea);
        setPlatform(idea.platform && PLATFORMS.some((p) => p.key === idea.platform) ? idea.platform : "tiktok");
        setScript("");
        // scroll to script area
        setTimeout(() => scriptRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    };

    const generateScript = async () => {
        if (!selectedIdea) return;
        setLoadingScript(true);
        setScript("");
        try {
            const r = await api.post("/studio/script", {
                title: selectedIdea.title,
                hook: selectedIdea.hook,
                angle: selectedIdea.angle || "",
                platform,
            });
            setScript(r.data?.script_markdown || "");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Script generation failed");
        } finally {
            setLoadingScript(false);
        }
    };

    const saveScript = async () => {
        if (!selectedIdea || !script) return;
        setSaving(true);
        try {
            await api.post("/studio/scripts", {
                title: selectedIdea.title,
                hook: selectedIdea.hook,
                platform,
                script_markdown: script,
            });
            toast.success("Saved to the vault");
            loadSaved();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Save failed");
        } finally {
            setSaving(false);
        }
    };

    const deleteScript = async (id) => {
        try {
            await api.delete(`/studio/scripts/${id}`);
            setSaved((prev) => prev.filter((s) => s.id !== id));
            toast.success("Deleted");
        } catch {
            toast.error("Delete failed");
        }
    };

    const loadSavedScript = (s) => {
        setSelectedIdea({ title: s.title, hook: s.hook, angle: "" });
        setPlatform(s.platform || "tiktok");
        setScript(s.script_markdown);
        setTimeout(() => scriptRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    };

    // Extract just the spoken script section for voiceover playback
    const spokenScript = React.useMemo(() => {
        if (!script) return "";
        const m = script.match(/##\s*SPOKEN SCRIPT\s*\n([\s\S]*?)(?=\n##\s|$)/i);
        return (m ? m[1] : script).trim();
    }, [script]);

    const copyScript = async () => {
        if (!script) return;
        try {
            await navigator.clipboard.writeText(script);
            toast.success("Script copied");
        } catch {
            toast.error("Clipboard blocked");
        }
    };

    return (
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
            <Toaster position="top-center" theme="dark" />
            <PageHeader
                eyebrow="Russell's Studio"
                title="Faceless content pipeline"
                subtitle="Hook → script → voiceover. Built for TikTok and YouTube in Russell's voice."
            />

            {/* ── Step 1: Topic + Ideas ───────────────────────────── */}
            <section className="mb-10">
                <div className="flex items-center gap-2 mb-3">
                    <Lightbulb size={18} weight="fill" style={{ color: "var(--accent)" }} />
                    <span className="label-tiny">Step 1 — Ideas</span>
                </div>
                <div className="tool-card">
                    <div className="grid sm:grid-cols-[1fr_auto_auto] gap-2 mb-2">
                        <input
                            className="input-dark"
                            placeholder="e.g. Old fashioned variations, dive bar drinks, mezcal for beginners"
                            value={topic}
                            onChange={(e) => setTopic(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && generateIdeas()}
                            data-testid="studio-topic-input"
                        />
                        <input
                            type="number"
                            min={1}
                            max={15}
                            className="input-dark w-24"
                            value={count}
                            onChange={(e) => setCount(parseInt(e.target.value) || 5)}
                            data-testid="studio-idea-count"
                        />
                        <button
                            className="btn-amber"
                            onClick={generateIdeas}
                            disabled={loadingIdeas}
                            data-testid="studio-generate-ideas"
                        >
                            {loadingIdeas ? "Cooking..." : "Give me hooks"}
                        </button>
                    </div>
                    <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                        Russell writes hook-first, opinion-forward ideas. Try controversial takes, myth-busters, or a specific
                        technique.
                    </p>
                </div>

                {ideas.length > 0 && (
                    <div className="grid md:grid-cols-2 gap-3 mt-4" data-testid="studio-ideas-list">
                        {ideas.map((idea, i) => {
                            const active = selectedIdea?.title === idea.title;
                            return (
                                <button
                                    key={i}
                                    onClick={() => chooseIdea(idea)}
                                    className="tool-card text-left hover:border-white/20 transition-all"
                                    style={{
                                        borderColor: active ? "var(--accent)" : undefined,
                                        cursor: "pointer",
                                    }}
                                    data-testid={`studio-idea-${i}`}
                                >
                                    <div className="flex items-baseline justify-between gap-2 mb-2">
                                        <h3 className="font-serif text-lg" style={{ color: "var(--accent)" }}>
                                            {idea.title}
                                        </h3>
                                        <span className="badge">{idea.platform || "tiktok"}</span>
                                    </div>
                                    <p className="text-sm mb-2" style={{ color: "var(--text-primary)" }}>
                                        &ldquo;{idea.hook}&rdquo;
                                    </p>
                                    {idea.angle && (
                                        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
                                            {idea.angle}
                                        </p>
                                    )}
                                    {active && (
                                        <div
                                            className="text-xs mt-3 flex items-center gap-1"
                                            style={{ color: "var(--accent)" }}
                                        >
                                            Selected <ArrowRight size={12} weight="bold" />
                                        </div>
                                    )}
                                </button>
                            );
                        })}
                    </div>
                )}
            </section>

            {/* ── Step 2: Script ──────────────────────────────────── */}
            <section className="mb-10" ref={scriptRef}>
                <div className="flex items-center gap-2 mb-3">
                    <FilmSlate size={18} weight="fill" style={{ color: "var(--accent)" }} />
                    <span className="label-tiny">Step 2 — Script</span>
                </div>

                {!selectedIdea && (
                    <div
                        className="tool-card text-sm"
                        style={{ color: "var(--text-secondary)" }}
                        data-testid="studio-script-empty"
                    >
                        Pick an idea above to write the full script.
                    </div>
                )}

                {selectedIdea && (
                    <div className="tool-card">
                        <div className="mb-3">
                            <div className="label-tiny">Working on</div>
                            <div className="font-serif text-xl" style={{ color: "var(--accent)" }}>
                                {selectedIdea.title}
                            </div>
                            <div className="text-sm mt-1" style={{ color: "var(--text-primary)" }}>
                                &ldquo;{selectedIdea.hook}&rdquo;
                            </div>
                        </div>
                        <div className="flex flex-wrap gap-2 mb-3">
                            {PLATFORMS.map((p) => (
                                <button
                                    key={p.key}
                                    onClick={() => setPlatform(p.key)}
                                    className={`nav-link ${platform === p.key ? "active" : ""}`}
                                    data-testid={`studio-platform-${p.key}`}
                                >
                                    {p.label}
                                </button>
                            ))}
                        </div>
                        <div className="flex flex-wrap gap-2">
                            <button
                                className="btn-amber"
                                onClick={generateScript}
                                disabled={loadingScript}
                                data-testid="studio-generate-script"
                            >
                                {loadingScript ? (
                                    <>
                                        <ArrowClockwise size={14} weight="bold" className="inline mr-2 animate-spin" />
                                        Writing...
                                    </>
                                ) : script ? (
                                    "Regenerate"
                                ) : (
                                    "Write the script"
                                )}
                            </button>
                            {script && (
                                <>
                                    <button
                                        className="btn-ghost"
                                        onClick={copyScript}
                                        data-testid="studio-copy-script"
                                    >
                                        <Copy size={14} weight="bold" className="inline mr-1" /> Copy
                                    </button>
                                    <button
                                        className="btn-ghost"
                                        onClick={saveScript}
                                        disabled={saving}
                                        data-testid="studio-save-script"
                                    >
                                        <FloppyDisk size={14} weight="bold" className="inline mr-1" />
                                        {saving ? "Saving..." : "Save"}
                                    </button>
                                </>
                            )}
                        </div>

                        {script && (
                            <pre
                                className="mt-4 whitespace-pre-wrap font-mono text-sm p-4 rounded-lg"
                                style={{
                                    background: "rgba(0,0,0,0.35)",
                                    color: "var(--text-primary)",
                                    border: "1px solid var(--border-subtle)",
                                    maxHeight: "60vh",
                                    overflow: "auto",
                                }}
                                data-testid="studio-script-output"
                            >
                                {script}
                            </pre>
                        )}
                    </div>
                )}
            </section>

            {/* ── Step 3: Voiceover ───────────────────────────────── */}
            {spokenScript && (
                <section className="mb-10">
                    <div className="flex items-center gap-2 mb-3">
                        <SpeakerHigh size={18} weight="fill" style={{ color: "var(--accent)" }} />
                        <span className="label-tiny">Step 3 — Voiceover</span>
                    </div>
                    <VoiceoverPlayer text={spokenScript} />
                </section>
            )}

            {/* ── Vault ───────────────────────────────────────────── */}
            <section className="mt-12">
                <div className="flex items-center gap-2 mb-3">
                    <FloppyDisk size={18} weight="fill" style={{ color: "var(--accent)" }} />
                    <span className="label-tiny">Vault — Saved scripts</span>
                </div>
                {saved.length === 0 ? (
                    <div className="tool-card text-sm" style={{ color: "var(--text-secondary)" }}>
                        Nothing saved yet. Write a script and hit save to build your library.
                    </div>
                ) : (
                    <div className="grid md:grid-cols-2 gap-3" data-testid="studio-saved-list">
                        {saved.map((s) => (
                            <div key={s.id} className="tool-card" data-testid={`studio-saved-${s.id}`}>
                                <div className="flex items-baseline justify-between gap-2 mb-1">
                                    <h4 className="font-serif text-lg" style={{ color: "var(--accent)" }}>
                                        {s.title}
                                    </h4>
                                    <span className="badge">{s.platform}</span>
                                </div>
                                <p className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
                                    &ldquo;{s.hook}&rdquo;
                                </p>
                                <div className="flex gap-2">
                                    <button
                                        className="btn-ghost text-sm"
                                        onClick={() => loadSavedScript(s)}
                                        data-testid={`studio-load-${s.id}`}
                                    >
                                        Open
                                    </button>
                                    <button
                                        className="btn-ghost text-sm"
                                        onClick={() => deleteScript(s.id)}
                                        data-testid={`studio-delete-${s.id}`}
                                    >
                                        <Trash size={14} weight="bold" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </section>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────
// Voiceover player — calls existing /api/voice/speak with 'onyx'
// ─────────────────────────────────────────────────────────────────
function VoiceoverPlayer({ text }) {
    const [loading, setLoading] = useState(false);
    const [audioUrl, setAudioUrl] = useState(null);
    const [playing, setPlaying] = useState(false);
    const audioRef = useRef(null);

    // Reset when script text changes
    useEffect(() => {
        setAudioUrl(null);
        setPlaying(false);
    }, [text]);

    const generate = async () => {
        setLoading(true);
        try {
            const res = await fetch(`${API}/voice/speak`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text, voice: "onyx", format: "mp3", model: "tts-1" }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            setAudioUrl(url);
        } catch (e) {
            toast.error(e.message || "Voiceover failed");
        } finally {
            setLoading(false);
        }
    };

    const togglePlay = () => {
        const a = audioRef.current;
        if (!a) return;
        if (a.paused) a.play();
        else a.pause();
    };

    return (
        <div className="tool-card">
            <p className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
                Russell narrates the spoken script section with his own voice. Download the file to drop into CapCut or
                Premiere.
            </p>
            <div className="flex flex-wrap gap-2 items-center">
                <button
                    className="btn-amber"
                    onClick={generate}
                    disabled={loading}
                    data-testid="studio-generate-voiceover"
                >
                    {loading ? (
                        <>
                            <ArrowClockwise size={14} weight="bold" className="inline mr-2 animate-spin" />
                            Rendering...
                        </>
                    ) : audioUrl ? (
                        "Re-render voiceover"
                    ) : (
                        <>
                            <SpeakerHigh size={14} weight="bold" className="inline mr-2" />
                            Generate voiceover
                        </>
                    )}
                </button>
                {audioUrl && (
                    <>
                        <button
                            className="btn-ghost"
                            onClick={togglePlay}
                            data-testid="studio-play-voiceover"
                        >
                            {playing ? (
                                <>
                                    <Pause size={14} weight="fill" className="inline mr-1" /> Pause
                                </>
                            ) : (
                                <>
                                    <Play size={14} weight="fill" className="inline mr-1" /> Play
                                </>
                            )}
                        </button>
                        <a
                            href={audioUrl}
                            download="russell-voiceover.mp3"
                            className="btn-ghost"
                            data-testid="studio-download-voiceover"
                        >
                            Download MP3
                        </a>
                    </>
                )}
            </div>
            {audioUrl && (
                <audio
                    ref={audioRef}
                    src={audioUrl}
                    onPlay={() => setPlaying(true)}
                    onPause={() => setPlaying(false)}
                    onEnded={() => setPlaying(false)}
                    className="w-full mt-4"
                    controls
                    data-testid="studio-audio-el"
                />
            )}
        </div>
    );
}
