import React, { useEffect, useState } from "react";
import { api, API } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Toaster, toast } from "sonner";
import { Copy, Phone, ChatText, CheckCircle, Warning, TelegramLogo, ArrowSquareOut, Cpu, SpotifyLogo, MusicNote } from "@phosphor-icons/react";

export default function PhonePage() {
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);
    const [tg, setTg] = useState(null);
    const [tgLoading, setTgLoading] = useState(true);
    const [setupBusy, setSetupBusy] = useState(false);
    const [spotify, setSpotify] = useState(null);
    const [spotifyLoading, setSpotifyLoading] = useState(true);

    useEffect(() => {
        api.get("/twilio/status")
            .then((r) => setStatus(r.data))
            .catch(() => setStatus(null))
            .finally(() => setLoading(false));
        loadTelegram();
        loadSpotify();

        // When the OAuth popup closes via postMessage, refresh the status.
        const onMsg = (e) => {
            if (e?.data?.type === "spotify_connected") {
                setTimeout(loadSpotify, 400);
            }
        };
        window.addEventListener("message", onMsg);
        return () => window.removeEventListener("message", onMsg);
    }, []);

    const loadSpotify = () => {
        setSpotifyLoading(true);
        api.get("/spotify/status")
            .then((r) => setSpotify(r.data))
            .catch(() => setSpotify(null))
            .finally(() => setSpotifyLoading(false));
    };

    const connectSpotify = async () => {
        try {
            const r = await api.get("/spotify/login");
            window.open(r.data.auth_url, "_blank", "noopener,noreferrer");
            toast.info("Authorise in the popup, then come back here.");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Couldn't start Spotify login");
        }
    };

    const disconnectSpotify = async () => {
        await api.post("/spotify/disconnect");
        toast.success("Spotify disconnected");
        loadSpotify();
    };

    const loadTelegram = () => {
        setTgLoading(true);
        api.get("/telegram/status")
            .then((r) => setTg(r.data))
            .catch(() => setTg(null))
            .finally(() => setTgLoading(false));
    };

    const smsWebhook = `${API}/twilio/sms`;
    const voiceWebhook = `${API}/twilio/voice`;
    const tgWebhook = `${API}/telegram/webhook`;
    const publicBase = API.replace(/\/api$/, "");

    const copy = (text, label) => {
        navigator.clipboard.writeText(text);
        toast.success(`Copied ${label}`);
    };

    const runTelegramSetup = async () => {
        setSetupBusy(true);
        try {
            const r = await api.post("/telegram/setup", { public_base_url: publicBase });
            if (r.data.webhook_secret) {
                toast.success("Webhook registered. Save the generated secret to .env!", { duration: 6000 });
            } else {
                toast.success("Webhook registered with Telegram");
            }
            loadTelegram();
            // Show secret in a dialog-ish toast
            if (r.data.webhook_secret) {
                navigator.clipboard.writeText(r.data.webhook_secret);
                toast.info(`Generated secret copied to clipboard. Add TELEGRAM_WEBHOOK_SECRET=${r.data.webhook_secret} to /app/backend/.env`, { duration: 12000 });
            }
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Setup failed");
        } finally {
            setSetupBusy(false);
        }
    };

    const Step = ({ n, title, children }) => (
        <div className="tool-card mb-4">
            <div className="flex items-baseline gap-3 mb-3">
                <span
                    className="font-serif text-2xl"
                    style={{ color: "var(--accent)", minWidth: 32 }}
                >
                    {n}
                </span>
                <h3 className="font-serif text-2xl" style={{ color: "var(--text-primary)" }}>
                    {title}
                </h3>
            </div>
            <div className="ml-11" style={{ color: "var(--text-secondary)" }}>
                {children}
            </div>
        </div>
    );

    return (
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
            <Toaster position="top-center" theme="dark" />
            <PageHeader
                eyebrow="Channels"
                title="Russell beyond the web"
                subtitle="Hook Russell up to SMS, phone calls, and Telegram. One brain across every channel."
            />

            {/* Status card */}
            <div className="tool-card mb-8 flex items-center gap-4" data-testid="twilio-status-card">
                {loading ? (
                    <span style={{ color: "var(--text-secondary)" }}>Checking…</span>
                ) : status?.configured ? (
                    <>
                        <CheckCircle size={28} weight="fill" style={{ color: "var(--accent)" }} />
                        <div>
                            <div className="font-serif text-xl" style={{ color: "var(--text-primary)" }}>
                                Russell is live on the phone
                            </div>
                            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                                Twilio configured. Text or call your number to chat with him.
                            </div>
                        </div>
                    </>
                ) : (
                    <>
                        <Warning size={28} weight="fill" style={{ color: "#FCA5A5" }} />
                        <div>
                            <div className="font-serif text-xl" style={{ color: "var(--text-primary)" }}>
                                Twilio not configured yet
                            </div>
                            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                                Follow the 4 steps below. Takes about 5 minutes.
                            </div>
                        </div>
                    </>
                )}
            </div>

            {/* Spotify card */}
            <div className="tool-card mb-8" data-testid="spotify-status-card">
                <div className="flex items-start gap-4">
                    <SpotifyLogo size={36} weight="fill" style={{ color: spotify?.connected ? "#1DB954" : "var(--text-secondary)" }} />
                    <div className="flex-1 min-w-0">
                        <div className="font-serif text-2xl mb-1" style={{ color: "var(--text-primary)" }}>
                            Spotify
                        </div>
                        {spotifyLoading ? (
                            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>Checking…</div>
                        ) : spotify?.connected ? (
                            <>
                                <div className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
                                    Connected as <strong style={{ color: "var(--text-primary)" }}>{spotify.profile?.display_name || "—"}</strong>
                                    {spotify.profile?.is_premium ? (
                                        <span className="ml-2 badge" style={{ color: "#1DB954", borderColor: "#1DB954" }}>Premium</span>
                                    ) : (
                                        <span className="ml-2 badge" style={{ color: "#FCA5A5" }}>Free tier — playback control disabled</span>
                                    )}
                                </div>
                                {spotify.currently_playing ? (
                                    <div
                                        className="flex items-center gap-2 px-3 py-2 rounded-lg mb-3"
                                        style={{ background: "rgba(29, 185, 84, 0.08)", border: "1px solid rgba(29, 185, 84, 0.25)" }}
                                        data-testid="spotify-now-playing"
                                    >
                                        <MusicNote size={16} weight="fill" style={{ color: "#1DB954" }} />
                                        <div className="text-sm" style={{ color: "var(--text-primary)" }}>
                                            <strong>{spotify.currently_playing.track}</strong> — {spotify.currently_playing.artist}
                                            {spotify.currently_playing.device && (
                                                <span style={{ color: "var(--text-secondary)" }}> · on {spotify.currently_playing.device}</span>
                                            )}
                                            {!spotify.currently_playing.is_playing && (
                                                <span style={{ color: "var(--text-secondary)" }}> · paused</span>
                                            )}
                                        </div>
                                    </div>
                                ) : (
                                    <div className="text-sm mb-3" style={{ color: "var(--text-secondary)" }}>
                                        Nothing playing right now. Open Spotify on a device and Russell can take over from there.
                                    </div>
                                )}
                                <div className="flex gap-2">
                                    <button onClick={loadSpotify} className="btn-ghost text-sm" data-testid="spotify-refresh">
                                        Refresh
                                    </button>
                                    <button onClick={disconnectSpotify} className="btn-ghost text-sm" data-testid="spotify-disconnect">
                                        Disconnect
                                    </button>
                                </div>
                            </>
                        ) : (
                            <>
                                <div className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
                                    Connect once and Russell can play music on your behalf — "Hey Russell, throw on some Marley", queue tracks, change the vibe to match what you're drinking. Premium required for playback control.
                                </div>
                                <button onClick={connectSpotify} className="btn-amber flex items-center gap-2" data-testid="spotify-connect-btn">
                                    <SpotifyLogo size={16} weight="fill" /> Connect with Spotify
                                </button>
                            </>
                        )}
                    </div>
                </div>
            </div>
            <div className="tool-card mb-8">
                <h3 className="font-serif text-2xl mb-4" style={{ color: "var(--accent)" }}>
                    Your webhook URLs
                </h3>
                <p className="text-sm mb-4" style={{ color: "var(--text-secondary)" }}>
                    Paste these into your Twilio phone-number configuration (Voice & Messaging webhooks).
                </p>

                <div className="space-y-3">
                    <WebhookRow icon={ChatText} label="SMS webhook" url={smsWebhook} onCopy={() => copy(smsWebhook, "SMS URL")} testid="copy-sms" />
                    <WebhookRow icon={Phone} label="Voice webhook" url={voiceWebhook} onCopy={() => copy(voiceWebhook, "Voice URL")} testid="copy-voice" />
                </div>
            </div>

            {/* Setup steps */}
            <h2 className="font-serif text-3xl mb-6" style={{ color: "var(--text-primary)" }}>
                Setup
            </h2>

            <Step n="1" title="Sign up for Twilio">
                Head to <a href="https://www.twilio.com/try-twilio" target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>twilio.com</a> and create an account. You'll get a <strong style={{ color: "var(--text-primary)" }}>~US$15 trial credit</strong> — enough for months of personal use.
            </Step>

            <Step n="2" title="Buy an Australian number">
                In Twilio Console → <em>Phone Numbers → Manage → Buy a number</em>. Pick <strong style={{ color: "var(--text-primary)" }}>Australia (+61)</strong>, choose Mobile or Local. Make sure Voice + SMS capabilities are ticked. ~A$1.15/month.
            </Step>

            <Step n="3" title="Wire the webhooks">
                Open your new number's settings. Under <em>Voice Configuration</em>, set "A call comes in" to <strong style={{ color: "var(--text-primary)" }}>Webhook</strong> and paste the <strong style={{ color: "var(--text-primary)" }}>Voice webhook URL</strong> above (HTTP POST). Under <em>Messaging Configuration</em>, set "A message comes in" to <strong style={{ color: "var(--text-primary)" }}>Webhook</strong> and paste the <strong style={{ color: "var(--text-primary)" }}>SMS webhook URL</strong> (HTTP POST). Save.
            </Step>

            <Step n="4" title="Drop your credentials in">
                Grab your <strong style={{ color: "var(--text-primary)" }}>Account SID</strong>, <strong style={{ color: "var(--text-primary)" }}>Auth Token</strong>, and your new <strong style={{ color: "var(--text-primary)" }}>phone number</strong> (E.164 format, e.g. <code>+61400123456</code>) from the Twilio console. Share them with me here in the chat, or paste them into <code>/app/backend/.env</code> directly:
                <pre className="mt-3 p-3 rounded-lg text-xs overflow-x-auto" style={{ background: "rgba(0,0,0,0.4)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
{`TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token-here
TWILIO_PHONE_NUMBER=+61400123456`}
                </pre>
                After saving, your phone number is live. Test by texting "G'day" or calling it.
            </Step>

            <div className="tool-card mt-8">
                <div className="label-tiny mb-2">Costs (Australia)</div>
                <ul className="text-sm space-y-1" style={{ color: "var(--text-secondary)" }}>
                    <li>• Number rental: ~A$1.15/month</li>
                    <li>• Inbound SMS: ~A$0.01 each · Outbound SMS: ~A$0.04 each</li>
                    <li>• Inbound voice + Twilio speech-to-text: ~A$0.03/minute combined</li>
                    <li>• Polly Aussie voice "Russell" for replies: included</li>
                </ul>
                <p className="text-xs mt-3" style={{ color: "var(--text-muted)" }}>
                    Light personal use lands around A$3–5/month. Trial credit covers months of testing.
                </p>
            </div>

            {/* ============================================================ */}
            {/* TELEGRAM                                                     */}
            {/* ============================================================ */}
            <div className="mt-16 mb-8 flex items-center gap-3">
                <TelegramLogo size={28} weight="fill" style={{ color: "var(--accent)" }} />
                <h2 className="font-serif text-3xl" style={{ color: "var(--text-primary)" }}>
                    Telegram — free, no card
                </h2>
            </div>
            <p className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>
                Spin up a personal Telegram bot for Russell. Free forever, no phone number, no Twilio bill. Texts him from your pocket like any other contact.
            </p>

            {/* Telegram status card */}
            <div className="tool-card mb-8 flex items-center gap-4" data-testid="telegram-status-card">
                {tgLoading ? (
                    <span style={{ color: "var(--text-secondary)" }}>Checking…</span>
                ) : tg?.configured && tg?.bot?.username ? (
                    <>
                        <CheckCircle size={28} weight="fill" style={{ color: "var(--accent)" }} />
                        <div className="flex-1">
                            <div className="font-serif text-xl" style={{ color: "var(--text-primary)" }}>
                                Russell on Telegram: <span style={{ color: "var(--accent)" }}>@{tg.bot.username}</span>
                            </div>
                            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                                {tg?.webhook?.url
                                    ? <>Webhook live · <span className="font-mono text-xs">{tg.webhook.url}</span></>
                                    : "Bot token set. Click Register webhook below to go live."}
                                {tg?.webhook?.last_error_message && (
                                    <span style={{ color: "#FCA5A5" }}> · last error: {tg.webhook.last_error_message}</span>
                                )}
                            </div>
                        </div>
                        <a
                            href={`https://t.me/${tg.bot.username}`}
                            target="_blank"
                            rel="noreferrer"
                            className="btn-ghost text-xs flex items-center gap-1"
                            data-testid="telegram-open-chat"
                        >
                            Open chat <ArrowSquareOut size={12} />
                        </a>
                    </>
                ) : (
                    <>
                        <Warning size={28} weight="fill" style={{ color: "#FCA5A5" }} />
                        <div>
                            <div className="font-serif text-xl" style={{ color: "var(--text-primary)" }}>
                                Telegram bot not configured yet
                            </div>
                            <div className="text-sm" style={{ color: "var(--text-secondary)" }}>
                                Three quick steps below. About 90 seconds.
                            </div>
                        </div>
                    </>
                )}
            </div>

            <Step n="1" title="Create the bot with @BotFather">
                On Telegram, message <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>@BotFather</a>. Send <code>/newbot</code>. Give it a display name (e.g. "Russell") and a username ending in <code>bot</code> (e.g. <code>russell_thebartender_bot</code>). BotFather hands you a <strong style={{ color: "var(--text-primary)" }}>bot token</strong> that looks like <code>123456:ABC-DEF...</code>. Copy it.
            </Step>

            <Step n="2" title="Drop the token in .env">
                Paste your bot token into <code>/app/backend/.env</code> and restart the backend:
                <pre className="mt-3 p-3 rounded-lg text-xs overflow-x-auto" style={{ background: "rgba(0,0,0,0.4)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
{`TELEGRAM_BOT_TOKEN=123456:ABC-DEF_paste-your-bot-token-here`}
                </pre>
                Or just share it here in chat — I'll wire it in for you.
            </Step>

            <Step n="3" title="Register the webhook">
                Once the token is set, click the button. I'll tell Telegram where to send messages and generate a secret to verify them.
                <div className="mt-4">
                    <button
                        onClick={runTelegramSetup}
                        disabled={setupBusy || !tg?.configured}
                        className="btn-primary text-sm"
                        data-testid="telegram-register-webhook"
                    >
                        {setupBusy ? "Registering…" : tg?.webhook?.url ? "Re-register webhook" : "Register webhook with Telegram"}
                    </button>
                    <span className="ml-3 text-xs" style={{ color: "var(--text-muted)" }}>
                        Webhook URL: <span className="font-mono">{tgWebhook}</span>
                        <button
                            onClick={() => copy(tgWebhook, "Telegram webhook URL")}
                            className="ml-2 underline"
                            data-testid="copy-telegram-webhook"
                        >
                            copy
                        </button>
                    </span>
                </div>
            </Step>

            <div className="tool-card mt-4">
                <div className="label-tiny mb-2">Lock it to just you (recommended)</div>
                <p className="text-sm mb-2" style={{ color: "var(--text-secondary)" }}>
                    Anyone who finds your bot's username can message it. To keep Russell private, message your bot, then send <code>/whoami</code> — he'll reply with your chat ID. Add it to <code>.env</code>:
                </p>
                <pre className="p-3 rounded-lg text-xs overflow-x-auto" style={{ background: "rgba(0,0,0,0.4)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
{`TELEGRAM_ALLOWED_CHAT_IDS=123456789`}
                </pre>
                <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
                    Comma-separated for multiple. Leave blank to let anyone chat.
                </p>
            </div>

            <div className="tool-card mt-4">
                <div className="label-tiny mb-2">Costs</div>
                <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                    Free. No card. No phone number. Telegram doesn't charge for bot messages — your only cost is the LLM tokens (same as web chat).
                </p>
            </div>

            {/* ============================================================ */}
            {/* RASPBERRY PI                                                 */}
            {/* ============================================================ */}
            <div className="mt-16 mb-8 flex items-center gap-3">
                <Cpu size={28} weight="fill" style={{ color: "var(--accent)" }} />
                <h2 className="font-serif text-3xl" style={{ color: "var(--text-primary)" }}>
                    Raspberry Pi — voice in the room
                </h2>
            </div>
            <p className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>
                Always-on voice client for your Pi 4. Say <strong style={{ color: "var(--accent)" }}>"Hey Russell"</strong>, ask anything, hear Russell back in his own voice. Wake-word detection runs locally; STT and the brain stay in the cloud; TTS is local Piper (Aussie male, offline).
            </p>

            <div className="tool-card mb-4">
                <div className="label-tiny mb-2">Code lives at</div>
                <div className="text-sm font-mono" style={{ color: "var(--text-primary)" }}>
                    /app/pi_client/
                </div>
                <p className="text-xs mt-2" style={{ color: "var(--text-muted)" }}>
                    Full setup guide in <code>/app/pi_client/README.md</code>. Save the project to GitHub from the chat box to pull it onto your Pi.
                </p>
            </div>

            <Step n="1" title="Get the dependencies">
                <strong style={{ color: "var(--text-primary)" }}>Picovoice access key</strong> (free) — sign up at <a href="https://console.picovoice.ai/" target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>console.picovoice.ai</a>. Then train a custom "Hey Russell" wake-word in their console (~30 seconds, free) and download the <code>.ppn</code> file for <em>Raspberry Pi (arm64)</em>.
            </Step>

            <Step n="2" title="Grab a voice">
                Russell sounds like an Aussie bloke because of the <strong style={{ color: "var(--text-primary)" }}>en_AU-southern_english_male-medium</strong> Piper voice. Download from <a href="https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_AU/southern_english_male/medium" target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>HuggingFace</a> (~60MB, both .onnx and .onnx.json).
            </Step>

            <Step n="3" title="On the Pi">
                <pre className="mt-1 p-3 rounded-lg text-xs overflow-x-auto" style={{ background: "rgba(0,0,0,0.4)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
{`sudo apt install -y python3-venv libportaudio2 portaudio19-dev libsndfile1
cd /opt/russell && python3 -m venv venv && source venv/bin/activate
pip install -r requirements_pi.txt
cp .env.example .env  &&  nano .env   # paste keys + paths
./run.sh`}
                </pre>
            </Step>

            <Step n="4" title="Autostart on boot">
                <pre className="p-3 rounded-lg text-xs overflow-x-auto" style={{ background: "rgba(0,0,0,0.4)", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
{`sudo cp systemd/russell.service /etc/systemd/system/
sudo systemctl enable --now russell.service
sudo journalctl -u russell -f   # follow logs`}
                </pre>
            </Step>

            <div className="tool-card mt-4">
                <div className="label-tiny mb-2">Architecture</div>
                <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                    Wake word + recording + TTS all run on the Pi. Whisper STT + Claude brain stay in the cloud. <strong style={{ color: "var(--text-primary)" }}>session_id="main"</strong> across all four channels — Russell remembers what you told him on Telegram while you're standing in the kitchen.
                </p>
            </div>
        </div>
    );
}

function WebhookRow({ icon: Icon, label, url, onCopy, testid }) {
    return (
        <div className="flex items-center gap-3">
            <Icon size={18} style={{ color: "var(--accent)" }} />
            <div className="flex-1 min-w-0">
                <div className="label-tiny mb-1">{label}</div>
                <div className="text-sm font-mono truncate" style={{ color: "var(--text-primary)" }} title={url}>
                    {url}
                </div>
            </div>
            <button onClick={onCopy} className="btn-ghost text-xs flex items-center gap-1" data-testid={testid}>
                <Copy size={14} /> Copy
            </button>
        </div>
    );
}
