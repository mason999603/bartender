import React, { useEffect, useState } from "react";
import { api, API } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Toaster, toast } from "sonner";
import { Copy, Phone, ChatText, CheckCircle, Warning } from "@phosphor-icons/react";

export default function PhonePage() {
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get("/twilio/status")
            .then((r) => setStatus(r.data))
            .catch(() => setStatus(null))
            .finally(() => setLoading(false));
    }, []);

    const smsWebhook = `${API}/twilio/sms`;
    const voiceWebhook = `${API}/twilio/voice`;

    const copy = (text, label) => {
        navigator.clipboard.writeText(text);
        toast.success(`Copied ${label}`);
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
                eyebrow="Telephony"
                title="Russell on the line"
                subtitle="Set up a real phone number you can text and call. One brain across web, SMS and phone."
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

            {/* Webhook URLs */}
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
