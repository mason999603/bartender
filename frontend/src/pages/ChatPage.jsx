import React, { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { PaperPlaneRight, Trash, Sparkle } from "@phosphor-icons/react";
import { Toaster, toast } from "sonner";
import VoiceControls from "@/components/VoiceControls";

const SUGGESTIONS = [
    "Make me a low-ABV aperitif using gin and grapefruit",
    "Can I put Baileys with lime? What happens?",
    "Build a Negroni variation with mezcal",
    "How do I pre-batch 30 Old Fashioneds with proper dilution?",
    "Suggest a smoky, citrusy drink with a hint of honey",
];

export default function ChatPage() {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState("");
    const [sending, setSending] = useState(false);
    const [loading, setLoading] = useState(true);
    const scrollRef = useRef(null);

    const loadHistory = async () => {
        try {
            const res = await api.get("/chat/history", { params: { session_id: "main" } });
            setMessages(res.data || []);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadHistory();
    }, []);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages, sending]);

    const send = async (text) => {
        const msg = (text ?? input).trim();
        if (!msg || sending) return;
        setInput("");
        setSending(true);

        // Optimistic user message
        const optimistic = {
            id: `tmp-${Date.now()}`,
            session_id: "main",
            role: "user",
            content: msg,
            timestamp: new Date().toISOString(),
        };
        setMessages((m) => [...m, optimistic]);

        try {
            const res = await api.post("/chat", { session_id: "main", message: msg });
            const russellReply = {
                id: `s-${Date.now()}`,
                session_id: "main",
                role: "russell",
                content: res.data.reply,
                timestamp: res.data.timestamp,
            };
            setMessages((m) => [...m, russellReply]);
        } catch (e) {
            console.error(e);
            toast.error("Russell's down for a smoke. Try again in a sec.");
            setMessages((m) => m.filter((x) => x.id !== optimistic.id));
        } finally {
            setSending(false);
        }
    };

    const clearChat = async () => {
        if (!window.confirm("Clear the whole chat? Russell's memories stay; only the conversation goes.")) return;
        try {
            await api.delete("/chat/history", { params: { session_id: "main" } });
            setMessages([]);
            toast.success("Chat wiped clean.");
        } catch {
            toast.error("Couldn't clear chat.");
        }
    };

    return (
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 flex flex-col" style={{ minHeight: "calc(100vh - 80px)" }}>
            <Toaster position="top-center" theme="dark" />

            {/* Hero / empty state */}
            {messages.length === 0 && !loading && (
                <div className="flex-1 flex flex-col items-center justify-center text-center fade-in py-12">
                    <div className="brand-mark mb-6" style={{ width: 64, height: 64 }} />
                    <div className="label-tiny mb-3">A mate behind the stick</div>
                    <h1
                        className="font-serif font-light"
                        style={{ fontSize: "clamp(2.5rem, 6vw, 4rem)", lineHeight: 1, color: "var(--text-primary)" }}
                    >
                        G'day. <span style={{ color: "var(--accent)" }}>I'm Russell.</span>
                    </h1>
                    <p
                        className="mt-4 text-base sm:text-lg max-w-xl"
                        style={{ color: "var(--text-secondary)" }}
                    >
                        Ask me about a build, a balance, a clash, a batch — anything across the bar.
                        I remember what you tell me.
                    </p>

                    <div className="mt-10 grid sm:grid-cols-2 gap-3 w-full max-w-2xl text-left">
                        {SUGGESTIONS.map((s, i) => (
                            <button
                                key={i}
                                onClick={() => send(s)}
                                className="tool-card text-sm flex items-start gap-3"
                                style={{ padding: "16px 18px", textAlign: "left" }}
                                data-testid={`suggestion-${i}`}
                            >
                                <Sparkle size={16} weight="fill" style={{ color: "var(--accent)", marginTop: 2 }} />
                                <span style={{ color: "var(--text-primary)" }}>{s}</span>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Messages */}
            {messages.length > 0 && (
                <>
                    <div className="flex items-center justify-between mb-4">
                        <div className="label-tiny">Conversation</div>
                        <button
                            onClick={clearChat}
                            className="text-xs flex items-center gap-1.5"
                            style={{ color: "var(--text-secondary)" }}
                            data-testid="clear-chat-btn"
                        >
                            <Trash size={14} /> Clear
                        </button>
                    </div>
                    <div
                        ref={scrollRef}
                        className="flex-1 overflow-y-auto space-y-4 pb-4"
                        style={{ maxHeight: "calc(100vh - 280px)" }}
                        data-testid="chat-scroll"
                    >
                        {messages.map((m) => (
                            <div
                                key={m.id}
                                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                                data-testid={`msg-${m.role}`}
                            >
                                {m.role === "russell" && (
                                    <div className="mr-3 mt-1">
                                        <div className="brand-mark" style={{ width: 28, height: 28 }} />
                                    </div>
                                )}
                                <div className={m.role === "user" ? "bubble-user" : "bubble-russell"}>{m.content}</div>
                            </div>
                        ))}
                        {sending && (
                            <div className="flex justify-start" data-testid="typing-indicator">
                                <div className="mr-3 mt-1">
                                    <div className="brand-mark" style={{ width: 28, height: 28 }} />
                                </div>
                                <div className="bubble-russell flex items-center gap-1.5 py-3 px-4">
                                    <span className="typing-dot" />
                                    <span className="typing-dot" />
                                    <span className="typing-dot" />
                                </div>
                            </div>
                        )}
                    </div>
                </>
            )}

            {/* Composer */}
            <div className="sticky bottom-4 mt-4 glass rounded-2xl p-3 relative" data-testid="chat-composer">
                <div className="flex items-end gap-2">
                    <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && !e.shiftKey) {
                                e.preventDefault();
                                send();
                            }
                        }}
                        placeholder="Ask Russell anything…"
                        rows={1}
                        className="flex-1 bg-transparent border-none outline-none px-3 py-3 text-base resize-none"
                        style={{ color: "var(--text-primary)", maxHeight: 200 }}
                        data-testid="chat-input"
                    />
                    <button
                        onClick={() => send()}
                        disabled={!input.trim() || sending}
                        className="btn-amber flex items-center gap-2"
                        data-testid="chat-send-btn"
                    >
                        <PaperPlaneRight size={16} weight="bold" />
                        <span className="hidden sm:inline">Send</span>
                    </button>
                </div>
                <div className="flex items-center justify-between gap-2 mt-2 px-1">
                    <VoiceControls
                        onTranscript={(text) => {
                            // Auto-send transcribed speech
                            send(text);
                        }}
                        russellLastReply={
                            messages.length > 0 && messages[messages.length - 1].role === "russell"
                                ? messages[messages.length - 1].content
                                : ""
                        }
                    />
                    <span className="text-xs hidden md:inline" style={{ color: "var(--text-muted)" }}>
                        Enter to send · Shift+Enter for newline · Space to talk
                    </span>
                </div>
            </div>
        </div>
    );
}
