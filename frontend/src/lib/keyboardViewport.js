/**
 * Keyboard-awareness helper for iOS/Android PWAs.
 *
 * Two independent signals — either one triggers hide-the-nav mode:
 *   1. `visualViewport.height` shrinks below 75% of window.innerHeight → keyboard is up
 *   2. A text input / textarea is focused → hide nav even if the viewport didn't shrink
 *      (some iOS versions don't shrink the viewport promptly)
 */
export function initKeyboardAwareViewport() {
    if (typeof window === "undefined") return;

    const root = document.documentElement;
    let vvOpen = false;
    let focusOpen = false;

    const applyState = () => {
        const open = vvOpen || focusOpen;
        root.classList.toggle("keyboard-open", open);
    };

    // Signal 1 — visual viewport shrink
    if (window.visualViewport) {
        const vv = window.visualViewport;
        const evaluate = () => {
            const ratio = vv.height / window.innerHeight;
            const nowOpen = ratio < 0.75;
            if (nowOpen === vvOpen) return;
            vvOpen = nowOpen;
            if (nowOpen) {
                root.style.setProperty("--keyboard-height", `${window.innerHeight - vv.height}px`);
            } else {
                root.style.removeProperty("--keyboard-height");
            }
            applyState();
        };
        vv.addEventListener("resize", evaluate);
        vv.addEventListener("scroll", evaluate);
    }

    // Signal 2 — text field focus. This is the reliable one on iOS Safari PWA.
    const TEXT_INPUT_TYPES = new Set(["text", "search", "email", "url", "tel", "password", "number", ""]);
    const isTextField = (el) => {
        if (!el) return false;
        if (el.tagName === "TEXTAREA") return true;
        if (el.tagName === "INPUT") {
            return TEXT_INPUT_TYPES.has((el.getAttribute("type") || "").toLowerCase());
        }
        return el.isContentEditable === true;
    };

    window.addEventListener("focusin", (e) => {
        if (isTextField(e.target)) {
            focusOpen = true;
            applyState();
        }
    });
    window.addEventListener("focusout", () => {
        // Wait a tick — if focus is moving to another text field, keep the class.
        setTimeout(() => {
            focusOpen = isTextField(document.activeElement);
            applyState();
        }, 100);
    });
}
