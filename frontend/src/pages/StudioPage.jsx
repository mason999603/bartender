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
    VideoCamera,
    Image as ImageIcon,
    Download,
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
                        <div className="flex flex-wrap gap-2 mb-1">
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
                        {platform === "both" && (
                            <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
                                Heads up — &ldquo;Both&rdquo; generates short + long-form. Takes ~90s and can time out. Prefer picking one.
                            </p>
                        )}
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

            {/* ── Step 4: Video Production (Phase 2) ──────────────── */}
            {spokenScript && (
                <section className="mb-10">
                    <div className="flex items-center gap-2 mb-3">
                        <VideoCamera size={18} weight="fill" style={{ color: "var(--accent)" }} />
                        <span className="label-tiny">Step 4 — Video production</span>
                    </div>
                    <VideoProducer spokenScript={spokenScript} hookText={selectedIdea?.hook || ""} />
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


// ─────────────────────────────────────────────────────────────────
// Video producer — Sora 2 hero clip + optional image card + ffmpeg
// ─────────────────────────────────────────────────────────────────
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

function VideoProducer({ spokenScript, hookText }) {
    const [heroPrompt, setHeroPrompt] = useState(
        "Cinematic slow-motion close up of amber whisky pouring over ice in a rocks glass, warm dim bar lighting, moody film photograph"
    );
    const [duration, setDuration] = useState(4);
    const [model, setModel] = useState("sora-2");

    const [cardPrompt, setCardPrompt] = useState("");
    const [captionText, setCaptionText] = useState(hookText || "");

    const [heroJob, setHeroJob] = useState(null);
    const [voiceJob, setVoiceJob] = useState(null);
    const [cardJob, setCardJob] = useState(null);
    const [finalJob, setFinalJob] = useState(null);

    useEffect(() => {
        if (hookText && !captionText) setCaptionText(hookText);
    }, [hookText, captionText]);

    const pollJob = async (id, setter) => {
        for (let i = 0; i < 240; i++) {
            try {
                const r = await api.get(`/studio/jobs/${id}`);
                setter(r.data);
                if (r.data.status === "done" || r.data.status === "failed") return r.data;
            } catch {
                /* keep polling */
            }
            await new Promise((res) => setTimeout(res, 5000));
        }
        return null;
    };

    const generateHero = async () => {
        if (!heroPrompt.trim()) return toast.error("Give Sora a prompt");
        try {
            const r = await api.post("/studio/jobs/hero-clip", {
                prompt: heroPrompt,
                aspect: "portrait",
                duration,
                model,
            });
            setHeroJob({ id: r.data.id, status: "queued" });
            const result = await pollJob(r.data.id, setHeroJob);
            if (result?.status === "failed") toast.error(result.error || "Hero render failed");
            else if (result?.status === "done") toast.success("Hero clip rendered");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Sora request failed");
        }
    };

    const generateVoice = async () => {
        try {
            const r = await api.post("/studio/jobs/voiceover", { text: spokenScript, voice: "onyx" });
            setVoiceJob(r.data);
            toast.success("Voiceover saved");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Voiceover failed");
        }
    };

    const generateCard = async () => {
        const prompt = cardPrompt.trim();
        if (!prompt) return toast.error("Give the image card a prompt");
        try {
            setCardJob({ status: "rendering" });
            const r = await api.post("/studio/jobs/image-card", { prompt, quality: "medium" });
            setCardJob(r.data);
            toast.success("Image card ready");
        } catch (e) {
            setCardJob(null);
            toast.error(e?.response?.data?.detail || "Image card failed");
        }
    };

    const assemble = async () => {
        if (!heroJob?.output?.filename) return toast.error("Render the hero clip first");
        if (!voiceJob?.filename) return toast.error("Generate the voiceover first");
        try {
            const r = await api.post("/studio/jobs/assemble", {
                hero_filename: heroJob.output.filename,
                voice_filename: voiceJob.filename,
                caption: captionText,
                outro_image_filename: cardJob?.filename || null,
            });
            setFinalJob({ id: r.data.id, status: "queued" });
            const result = await pollJob(r.data.id, setFinalJob);
            if (result?.status === "failed") toast.error(result.error || "Assembly failed");
            else if (result?.status === "done") toast.success("Final MP4 ready");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Assemble failed");
        }
    };

    const heroDone = heroJob?.status === "done" && heroJob?.output?.url;
    const voiceDone = !!voiceJob?.url;
    const cardDone = cardJob?.status === "done" && cardJob?.url;
    const finalDone = finalJob?.status === "done" && finalJob?.output?.url;

    return (
        <div className="tool-card space-y-8">
            {/* Hero clip */}
            <div>
                <div className="flex items-center gap-2 mb-2">
                    <VideoCamera size={16} weight="fill" style={{ color: "var(--accent)" }} />
                    <span className="label-tiny">Sora 2 hero clip (portrait, 720x1280)</span>
                </div>
                <textarea
                    className="input-dark w-full"
                    rows={3}
                    value={heroPrompt}
                    onChange={(e) => setHeroPrompt(e.target.value)}
                    placeholder="Describe the hero shot Sora should render..."
                    data-testid="studio-hero-prompt"
                />
                <div className="flex flex-wrap gap-2 mt-2 items-center">
                    <label className="text-xs" style={{ color: "var(--text-muted)" }}>
                        Duration
                    </label>
                    {[4, 8, 12].map((d) => (
                        <button
                            key={d}
                            onClick={() => setDuration(d)}
                            className={`nav-link ${duration === d ? "active" : ""}`}
                            data-testid={`studio-hero-dur-${d}`}
                        >
                            {d}s
                        </button>
                    ))}
                    <label className="text-xs ml-4" style={{ color: "var(--text-muted)" }}>
                        Model
                    </label>
                    {["sora-2", "sora-2-pro"].map((m) => (
                        <button
                            key={m}
                            onClick={() => setModel(m)}
                            className={`nav-link ${model === m ? "active" : ""}`}
                            data-testid={`studio-hero-model-${m}`}
                        >
                            {m}
                        </button>
                    ))}
                </div>
                <div className="flex flex-wrap gap-2 mt-3">
                    <button
                        className="btn-amber"
                        onClick={generateHero}
                        disabled={heroJob?.status === "rendering" || heroJob?.status === "queued"}
                        data-testid="studio-hero-generate"
                    >
                        {heroJob?.status === "rendering" || heroJob?.status === "queued" ? (
                            <>
                                <ArrowClockwise size={14} weight="bold" className="inline mr-2 animate-spin" />
                                Sora is cooking... ({heroJob?.status})
                            </>
                        ) : heroDone ? (
                            "Re-render hero"
                        ) : (
                            "Render hero clip"
                        )}
                    </button>
                    {heroDone && (
                        <a
                            href={`${BACKEND_URL}${heroJob.output.url}`}
                            target="_blank"
                            rel="noreferrer"
                            className="btn-ghost"
                            data-testid="studio-hero-preview"
                        >
                            <Play size={14} weight="fill" className="inline mr-1" /> Preview
                        </a>
                    )}
                </div>
                {heroJob?.status === "failed" && (
                    <p className="text-xs mt-2" style={{ color: "#FCA5A5" }}>
                        {heroJob.error}
                    </p>
                )}
                {heroDone && (
                    <video
                        src={`${BACKEND_URL}${heroJob.output.url}`}
                        controls
                        className="w-full max-w-xs mt-3 rounded-lg"
                        data-testid="studio-hero-video"
                    />
                )}
            </div>

            {/* Voiceover (uses spoken script) */}
            <div>
                <div className="flex items-center gap-2 mb-2">
                    <SpeakerHigh size={16} weight="fill" style={{ color: "var(--accent)" }} />
                    <span className="label-tiny">Save voiceover (needed for assembly)</span>
                </div>
                <button
                    className={`${voiceDone ? "btn-ghost" : "btn-amber"}`}
                    onClick={generateVoice}
                    data-testid="studio-voice-save"
                >
                    {voiceDone ? "Re-render voiceover" : "Save voiceover to server"}
                </button>
                {voiceDone && (
                    <audio
                        src={`${BACKEND_URL}${voiceJob.url}`}
                        controls
                        className="w-full mt-3"
                        data-testid="studio-voice-audio"
                    />
                )}
            </div>

            {/* Optional image outro */}
            <div>
                <div className="flex items-center gap-2 mb-2">
                    <ImageIcon size={16} weight="fill" style={{ color: "var(--accent)" }} />
                    <span className="label-tiny">Optional outro card (GPT-Image-1)</span>
                </div>
                <input
                    className="input-dark w-full"
                    placeholder="e.g. 'Text overlay: Follow for more. Amber neon on black.'"
                    value={cardPrompt}
                    onChange={(e) => setCardPrompt(e.target.value)}
                    data-testid="studio-card-prompt"
                />
                <button
                    className="btn-ghost mt-2"
                    onClick={generateCard}
                    disabled={cardJob?.status === "rendering"}
                    data-testid="studio-card-generate"
                >
                    {cardJob?.status === "rendering"
                        ? "Painting..."
                        : cardDone
                        ? "Re-render card"
                        : "Render outro card"}
                </button>
                {cardDone && (
                    <img
                        src={`${BACKEND_URL}${cardJob.url}`}
                        alt="outro card"
                        className="mt-3 max-w-xs rounded-lg"
                        data-testid="studio-card-img"
                    />
                )}
            </div>

            {/* Assembly */}
            <div>
                <div className="flex items-center gap-2 mb-2">
                    <FilmSlate size={16} weight="fill" style={{ color: "var(--accent)" }} />
                    <span className="label-tiny">Assemble final MP4</span>
                </div>
                <input
                    className="input-dark w-full mb-2"
                    placeholder="Caption overlay text (optional)"
                    value={captionText}
                    onChange={(e) => setCaptionText(e.target.value)}
                    data-testid="studio-caption-input"
                />
                <button
                    className="btn-amber"
                    onClick={assemble}
                    disabled={
                        !heroDone ||
                        !voiceDone ||
                        finalJob?.status === "rendering" ||
                        finalJob?.status === "queued"
                    }
                    data-testid="studio-assemble"
                >
                    {finalJob?.status === "rendering" || finalJob?.status === "queued" ? (
                        <>
                            <ArrowClockwise size={14} weight="bold" className="inline mr-2 animate-spin" />
                            Stitching...
                        </>
                    ) : finalDone ? (
                        "Re-assemble"
                    ) : (
                        "Assemble MP4"
                    )}
                </button>
                {finalJob?.status === "failed" && (
                    <p className="text-xs mt-2" style={{ color: "#FCA5A5" }}>
                        {finalJob.error}
                    </p>
                )}
                {finalDone && (
                    <div className="mt-4">
                        <video
                            src={`${BACKEND_URL}${finalJob.output.url}`}
                            controls
                            className="w-full max-w-xs rounded-lg"
                            data-testid="studio-final-video"
                        />
                        <a
                            href={`${BACKEND_URL}${finalJob.output.url}`}
                            download={`russell-${finalJob.id}.mp4`}
                            className="btn-ghost mt-3 inline-flex"
                            data-testid="studio-final-download"
                        >
                            <Download size={14} weight="bold" className="inline mr-1" /> Download MP4
                        </a>
                    </div>
                )}
                {(!heroDone || !voiceDone) && (
                    <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
                        Render the hero clip and save the voiceover before assembling.
                    </p>
                )}
            </div>
        </div>
    );
}
