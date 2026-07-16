/**
 * Keyboard-awareness helper for iOS/Android PWAs.
 *
 * When the on-screen keyboard opens, `window.visualViewport.height` shrinks
 * relative to `window.innerHeight`. We use that to toggle `keyboard-open` on
 * <html>, which CSS uses to hide the bottom tab bar and trim padding so the
 * chat composer isn't crushed against the keyboard.
 *
 * The threshold (0.75) is intentionally generous — even short keyboards on
 * small phones with the QuickType bar shrink the viewport by 30-40%. False
 * positives from browser UI (like Safari's address bar sliding) rarely dip
 * below 25%.
 */
export function initKeyboardAwareViewport() {
    if (typeof window === "undefined" || !window.visualViewport) return;

    const root = document.documentElement;
    const vv = window.visualViewport;
    let keyboardOpen = false;

    const evaluate = () => {
        const ratio = vv.height / window.innerHeight;
        const nowOpen = ratio < 0.75;
        if (nowOpen === keyboardOpen) return;
        keyboardOpen = nowOpen;
        if (nowOpen) {
            root.classList.add("keyboard-open");
            root.style.setProperty("--keyboard-height", `${window.innerHeight - vv.height}px`);
        } else {
            root.classList.remove("keyboard-open");
            root.style.removeProperty("--keyboard-height");
        }
    };

    vv.addEventListener("resize", evaluate);
    vv.addEventListener("scroll", evaluate);
    // Fallback trigger on focus (some browsers don't fire resize immediately)
    window.addEventListener("focusin", () => setTimeout(evaluate, 250));
    window.addEventListener("focusout", () => setTimeout(evaluate, 250));
}
