import React, { useEffect, useRef, useState } from "react";
import { API } from "@/lib/api";
import { Microphone, MicrophoneSlash, Gear, SpeakerHigh, ArrowsClockwise, Lightning, WaveSine, X } from "@phosphor-icons/react";

/**
 * Voice controls: push-to-talk OR continuous-with-VAD recording (Whisper STT),
 * plus free browser speechSynthesis playback of Sheldon's replies.
 *
 * Props:
 *   onTranscript(text)  — called when an utterance is transcribed
 *   sheldonLastReply    — string; when this changes and TTS is on, we speak it
 *   onListeningChange?  — optional callback (bool)
 */
export default function VoiceControls({ onTranscript, sheldonLastReply, onListeningChange }) {
    const [mode, setMode] = useState(() => localStorage.getItem("sheldon-mode") || "push"); // push | continuous
    const [ttsEnabled, setTtsEnabled] = useState(() => localStorage.getItem("sheldon-tts") !== "off");
    const [voices, setVoices] = useState([]);
    const [selectedVoiceName, setSelectedVoiceName] = useState(() => localStorage.getItem("sheldon-voice") || "");
    const [isRecording, setIsRecording] = useState(false);
    const [isListening, setIsListening] = useState(false); // continuous-mode session on
    const [transcribing, setTranscribing] = useState(false);
    const [showSettings, setShowSettings] = useState(false);
    const [permissionDenied, setPermissionDenied] = useState(false);
    const [unsupported, setUnsupported] = useState(false);
    const [amplitude, setAmplitude] = useState(0);

    const mediaRecorderRef = useRef(null);
    const audioChunksRef = useRef([]);
    const streamRef = useRef(null);
    const audioCtxRef = useRef(null);
    const analyserRef = useRef(null);
    const vadRafRef = useRef(null);
    const lastSpokenRef = useRef("");

    // Load available voices (auto-pick Aussie when possible)
    useEffect(() => {
        if (typeof window === "undefined" || !window.speechSynthesis) {
            setUnsupported(true);
            return;
        }
        const load = () => {
            const v = window.speechSynthesis.getVoices();
            setVoices(v);
            if (!selectedVoiceName && v.length > 0) {
                const auto =
                    v.find((x) => x.lang === "en-AU") ||
                    v.find((x) => x.lang.startsWith("en-AU")) ||
                    v.find((x) => x.lang.startsWith("en-GB")) ||
                    v.find((x) => x.lang.startsWith("en")) ||
                    v[0];
                if (auto) setSelectedVoiceName(auto.name);
            }
        };
        load();
        window.speechSynthesis.onvoiceschanged = load;
        return () => {
            if (window.speechSynthesis) window.speechSynthesis.onvoiceschanged = null;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Speak Sheldon's reply when it changes
    useEffect(() => {
        if (!ttsEnabled || !sheldonLastReply || sheldonLastReply === lastSpokenRef.current) return;
        if (!("speechSynthesis" in window)) return;
        lastSpokenRef.current = sheldonLastReply;
        try {
            window.speechSynthesis.cancel();
            const utter = new SpeechSynthesisUtterance(sheldonLastReply);
            const v = voices.find((x) => x.name === selectedVoiceName);
            if (v) utter.voice = v;
            utter.rate = 1.02;
            utter.pitch = 1.0;
            window.speechSynthesis.speak(utter);
        } catch (e) {
            console.error("TTS failed", e);
        }
    }, [sheldonLastReply, ttsEnabled, voices, selectedVoiceName]);

    // Persist settings
    useEffect(() => {
        localStorage.setItem("sheldon-mode", mode);
        localStorage.setItem("sheldon-tts", ttsEnabled ? "on" : "off");
        if (selectedVoiceName) localStorage.setItem("sheldon-voice", selectedVoiceName);
    }, [mode, ttsEnabled, selectedVoiceName]);

    // Tell parent when "listening" state changes (used for visual cues)
    useEffect(() => {
        if (onListeningChange) onListeningChange(isRecording || isListening);
    }, [isRecording, isListening, onListeningChange]);

    const cleanupStreams = () => {
        if (vadRafRef.current) cancelAnimationFrame(vadRafRef.current);
        vadRafRef.current = null;
        if (audioCtxRef.current) {
            try {
                audioCtxRef.current.close();
            } catch (e) { /* noop */ }
            audioCtxRef.current = null;
        }
        analyserRef.current = null;
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((t) => t.stop());
            streamRef.current = null;
        }
        setAmplitude(0);
    };

    const startRecording = async () => {
        if (isRecording) return;
        try {
            // When Sheldon's speaking, hush him while user talks
            if ("speechSynthesis" in window) window.speechSynthesis.cancel();

            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            streamRef.current = stream;

            const candidates = [
                "audio/webm;codecs=opus",
                "audio/webm",
                "audio/mp4",
                "audio/ogg;codecs=opus",
            ];
            const mime = candidates.find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";
            const rec = mime
                ? new MediaRecorder(stream, { mimeType: mime })
                : new MediaRecorder(stream);
            mediaRecorderRef.current = rec;
            audioChunksRef.current = [];
            rec.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) audioChunksRef.current.push(e.data);
            };
            rec.onstop = handleStop;
            rec.start();
            setIsRecording(true);
            setPermissionDenied(false);

            // Live amplitude bar + (in continuous mode) silence-based stop
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            audioCtxRef.current = ctx;
            const src = ctx.createMediaStreamSource(stream);
            const analyser = ctx.createAnalyser();
            analyser.fftSize = 512;
            src.connect(analyser);
            analyserRef.current = analyser;

            const data = new Uint8Array(analyser.frequencyBinCount);
            let voiceDetectedAt = 0;
            let everHeardVoice = false;
            const VOICE_THRESHOLD = 12; // average frequency-bin level
            const SILENCE_MS = 1200;

            const tick = () => {
                if (!mediaRecorderRef.current || mediaRecorderRef.current.state !== "recording") return;
                analyser.getByteFrequencyData(data);
                let sum = 0;
                for (let i = 0; i < data.length; i++) sum += data[i];
                const avg = sum / data.length;
                setAmplitude(Math.min(1, avg / 60));

                if (mode === "continuous") {
                    if (avg > VOICE_THRESHOLD) {
                        voiceDetectedAt = performance.now();
                        everHeardVoice = true;
                    }
                    if (everHeardVoice && voiceDetectedAt && performance.now() - voiceDetectedAt > SILENCE_MS) {
                        stopRecording();
                        return;
                    }
                }
                vadRafRef.current = requestAnimationFrame(tick);
            };
            vadRafRef.current = requestAnimationFrame(tick);
        } catch (e) {
            console.error(e);
            setPermissionDenied(true);
            cleanupStreams();
        }
    };

    const stopRecording = () => {
        const rec = mediaRecorderRef.current;
        if (rec && rec.state === "recording") {
            rec.stop();
        }
        setIsRecording(false);
        // cleanup happens in handleStop -> finally
    };

    const handleStop = async () => {
        const rec = mediaRecorderRef.current;
        const mime = rec ? rec.mimeType : "audio/webm";
        const blob = new Blob(audioChunksRef.current, { type: mime || "audio/webm" });
        audioChunksRef.current = [];

        // tracks
        cleanupStreams();

        // Tiny blob = silence/empty
        if (blob.size < 1500) {
            if (mode === "continuous" && isListening) {
                // restart for next utterance
                setTimeout(() => startRecording(), 100);
            }
            return;
        }

        setTranscribing(true);
        try {
            const ext = mime.includes("webm") ? "webm" : mime.includes("mp4") ? "mp4" : mime.includes("ogg") ? "ogg" : "wav";
            const fd = new FormData();
            fd.append("audio", blob, `voice.${ext}`);
            const res = await fetch(`${API}/voice/transcribe`, { method: "POST", body: fd });
            if (!res.ok) {
                console.error("Transcribe error", res.status);
                return;
            }
            const data = await res.json();
            const text = (data.text || "").trim();
            if (text && onTranscript) onTranscript(text);
        } catch (e) {
            console.error(e);
        } finally {
            setTranscribing(false);
            // continuous mode: loop
            if (mode === "continuous" && isListening) {
                setTimeout(() => startRecording(), 200);
            }
        }
    };

    // Push-to-talk handlers
    const handlePushStart = (e) => {
        if (e && e.preventDefault) e.preventDefault();
        if (mode !== "push" || isRecording || transcribing) return;
        startRecording();
    };
    const handlePushEnd = (e) => {
        if (e && e.preventDefault) e.preventDefault();
        if (mode !== "push" || !isRecording) return;
        stopRecording();
    };

    // Continuous mode toggle
    const toggleContinuous = () => {
        if (isListening) {
            setIsListening(false);
            stopRecording();
            if ("speechSynthesis" in window) window.speechSynthesis.cancel();
        } else {
            setIsListening(true);
            startRecording();
        }
    };

    // Spacebar push-to-talk (when not typing in an input)
    useEffect(() => {
        if (mode !== "push") return;
        const isTextField = (el) => el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
        const down = (e) => {
            if (e.code === "Space" && !isTextField(document.activeElement) && !e.repeat) {
                e.preventDefault();
                handlePushStart();
            }
        };
        const up = (e) => {
            if (e.code === "Space" && !isTextField(document.activeElement)) {
                e.preventDefault();
                handlePushEnd();
            }
        };
        window.addEventListener("keydown", down);
        window.addEventListener("keyup", up);
        return () => {
            window.removeEventListener("keydown", down);
            window.removeEventListener("keyup", up);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [mode, isRecording, transcribing]);

    // Cleanup on unmount
    useEffect(() => () => cleanupStreams(), []);

    const stopSpeaking = () => {
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    };

    if (unsupported) {
        return null;
    }

    const micActive = isRecording || isListening;
    const micLabel = mode === "push"
        ? (isRecording ? "Listening — release to send" : "Hold to talk · or press space")
        : (isListening ? "Listening — tap to stop" : "Tap to start hands-free");

    return (
        <div className="flex items-center gap-2" data-testid="voice-controls">
            {/* Mic button */}
            <button
                type="button"
                onMouseDown={mode === "push" ? handlePushStart : undefined}
                onMouseUp={mode === "push" ? handlePushEnd : undefined}
                onMouseLeave={mode === "push" ? handlePushEnd : undefined}
                onTouchStart={mode === "push" ? handlePushStart : undefined}
                onTouchEnd={mode === "push" ? handlePushEnd : undefined}
                onClick={mode === "continuous" ? toggleContinuous : undefined}
                disabled={transcribing}
                className="relative flex items-center justify-center"
                style={{
                    width: 48,
                    height: 48,
                    borderRadius: "50%",
                    background: micActive ? "var(--accent)" : "rgba(255,255,255,0.04)",
                    border: `1px solid ${micActive ? "var(--accent)" : "rgba(255,255,255,0.1)"}`,
                    color: micActive ? "#0A0A0C" : "var(--text-primary)",
                    cursor: transcribing ? "wait" : "pointer",
                    transition: "all 200ms ease",
                    boxShadow: micActive ? "0 0 0 6px rgba(224,145,50,0.18)" : "none",
                }}
                title={micLabel}
                data-testid="mic-button"
            >
                {transcribing ? (
                    <ArrowsClockwise size={20} weight="bold" className="animate-spin" />
                ) : micActive ? (
                    <MicrophoneSlash size={20} weight="fill" />
                ) : (
                    <Microphone size={20} weight="fill" />
                )}
                {micActive && (
                    <span
                        style={{
                            position: "absolute",
                            inset: -2 - amplitude * 6,
                            borderRadius: "50%",
                            border: "1px solid var(--accent)",
                            opacity: 0.4 + amplitude * 0.5,
                            pointerEvents: "none",
                            transition: "inset 80ms ease, opacity 80ms ease",
                        }}
                    />
                )}
            </button>

            {/* Settings gear */}
            <button
                type="button"
                onClick={() => setShowSettings((s) => !s)}
                className="p-2 rounded-lg"
                style={{ color: "var(--text-secondary)", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)" }}
                title="Voice settings"
                data-testid="voice-settings-toggle"
            >
                <Gear size={16} weight="bold" />
            </button>

            {/* Stop speaking — only show while TTS is active */}
            {ttsEnabled && (
                <button
                    type="button"
                    onClick={stopSpeaking}
                    className="p-2 rounded-lg"
                    style={{ color: "var(--text-secondary)", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.1)" }}
                    title="Stop speaking"
                    data-testid="stop-tts"
                >
                    <SpeakerHigh size={16} weight="bold" />
                </button>
            )}

            {/* Inline status text */}
            <span className="text-xs hidden sm:inline" style={{ color: "var(--text-secondary)" }} data-testid="mic-status">
                {permissionDenied ? "Mic blocked — check browser permissions" : transcribing ? "Transcribing…" : micLabel}
            </span>

            {/* Settings panel */}
            {showSettings && (
                <div
                    className="absolute glass-strong rounded-xl p-5 z-40"
                    style={{ bottom: 70, left: 12, width: 320, maxWidth: "calc(100vw - 24px)" }}
                    data-testid="voice-settings-panel"
                >
                    <div className="flex items-center justify-between mb-4">
                        <div className="font-serif text-xl" style={{ color: "var(--accent)" }}>Voice</div>
                        <button onClick={() => setShowSettings(false)} className="p-1 rounded hover:bg-white/5">
                            <X size={16} />
                        </button>
                    </div>

                    {/* Mode */}
                    <div className="mb-4">
                        <div className="label-tiny mb-2">Mode</div>
                        <div className="grid grid-cols-2 gap-2">
                            <button
                                onClick={() => { setMode("push"); if (isListening) toggleContinuous(); }}
                                className={`tool-card text-sm flex items-center justify-center gap-2 ${mode === "push" ? "border-amber-500/40" : ""}`}
                                style={{ padding: "12px", borderColor: mode === "push" ? "var(--accent)" : undefined }}
                                data-testid="mode-push"
                            >
                                <Lightning size={14} weight="fill" /> Push to talk
                            </button>
                            <button
                                onClick={() => setMode("continuous")}
                                className="tool-card text-sm flex items-center justify-center gap-2"
                                style={{ padding: "12px", borderColor: mode === "continuous" ? "var(--accent)" : undefined }}
                                data-testid="mode-continuous"
                            >
                                <WaveSine size={14} weight="fill" /> Hands-free
                            </button>
                        </div>
                        <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
                            Push: hold the mic or press <kbd className="px-1 rounded border border-white/10">space</kbd>. Hands-free: detects when you stop speaking.
                        </p>
                    </div>

                    {/* TTS */}
                    <div className="mb-4">
                        <div className="flex items-center justify-between mb-2">
                            <div className="label-tiny">Sheldon speaks his replies</div>
                            <button
                                onClick={() => setTtsEnabled((v) => !v)}
                                className={`px-3 py-1 rounded-full text-xs font-semibold ${ttsEnabled ? "" : "opacity-50"}`}
                                style={{
                                    background: ttsEnabled ? "var(--accent)" : "rgba(255,255,255,0.06)",
                                    color: ttsEnabled ? "#0A0A0C" : "var(--text-secondary)",
                                }}
                                data-testid="tts-toggle"
                            >
                                {ttsEnabled ? "On" : "Off"}
                            </button>
                        </div>
                    </div>

                    {/* Voice picker */}
                    <div>
                        <div className="label-tiny mb-2">Voice</div>
                        <select
                            className="input-dark"
                            value={selectedVoiceName}
                            onChange={(e) => setSelectedVoiceName(e.target.value)}
                            data-testid="voice-select"
                        >
                            {voices.length === 0 && <option>Loading voices…</option>}
                            {voices.map((v) => (
                                <option key={v.name} value={v.name}>
                                    {v.name} ({v.lang})
                                </option>
                            ))}
                        </select>
                        {voices.find((v) => v.lang.startsWith("en-AU")) ? (
                            <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
                                Aussie voice detected — Sheldon sounds at home.
                            </p>
                        ) : (
                            <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
                                No en-AU voice on this device. Browser's default English voice is selected.
                            </p>
                        )}
                        <button
                            onClick={() => {
                                if (!("speechSynthesis" in window)) return;
                                window.speechSynthesis.cancel();
                                const u = new SpeechSynthesisUtterance("G'day mate. Sheldon here. What're we drinking?");
                                const v = voices.find((x) => x.name === selectedVoiceName);
                                if (v) u.voice = v;
                                u.rate = 1.02;
                                window.speechSynthesis.speak(u);
                            }}
                            className="btn-ghost text-xs mt-3"
                            data-testid="voice-preview"
                        >
                            Preview voice
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
