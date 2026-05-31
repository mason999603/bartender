# Custom wake-word models for Russell

Drop your trained openWakeWord `.onnx` file in here, then point `WAKE_WORD_MODEL`
in `/opt/russell/pi_client/.env` at its path. Example:

```
WAKE_WORD_MODEL=./keywords/hey_russell.onnx
```

## Training "Hey Russell" yourself — free, ~30 minutes

openWakeWord's `automatic_model_training.ipynb` notebook trains a custom wake-word
model in your browser using Google Colab's free GPU. You don't record any audio
yourself — TTS synthesises hundreds of voice variants of "Hey Russell" and trains
on those. The author has confirmed models trained on 100% synthetic data still
perform well on real voices.

### Step-by-step

**1. Open the official training notebook in Colab**

   <https://colab.research.google.com/github/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb>

   *(That's the live `automatic_model_training.ipynb` from the openWakeWord
   GitHub repo, opened directly in Colab. Sign in with any Google account.)*

**2. Switch the runtime to GPU** (training is ~3× faster)

   - Top menu: **Runtime** → **Change runtime type** → set **Hardware accelerator** to **T4 GPU** (free tier) → Save.

**3. Run all the setup cells in order**

   - Click **Runtime** → **Run all**.
   - First ~10 cells install dependencies and download pre-trained backbones. Let it run.

**4. Find the "Configure target phrase" cell and edit it**

   Look for a cell that defines the target phrase. Set it to:
   ```python
   target_phrase = ["hey russell", "hey russel"]
   ```
   *(Including the misspelling "russel" — single L — catches cases where the TTS
   pronounces it slightly differently. Doesn't hurt.)*

   Also tune these if you see them in the same cell:
   ```python
   model_name = "hey_russell"
   n_samples = 5000           # leave at default if shown — more = better
   n_samples_val = 1000       # validation samples
   ```

**5. Click Run all again** so it re-runs from the config cell down

   Training itself takes 15-25 minutes on the free T4. You'll see loss/accuracy
   numbers tick down in the output. Don't close the tab — Colab times out idle sessions.

**6. Download the trained model**

   When training finishes, the notebook auto-downloads `hey_russell.onnx` to your
   computer. If it doesn't auto-download, look for a cell at the bottom that
   says something like `files.download(...)`.

**7. Copy the .onnx to the Pi**

   From your laptop/PC where the file landed:
   ```bash
   scp ~/Downloads/hey_russell.onnx pi@russell-pi:/opt/russell/pi_client/keywords/
   ```

**8. Update `.env` on the Pi**

   ```bash
   ssh pi@russell-pi
   nano /opt/russell/pi_client/.env
   ```
   Change:
   ```
   WAKE_WORD_MODEL=hey_jarvis
   ```
   to:
   ```
   WAKE_WORD_MODEL=./keywords/hey_russell.onnx
   WAKE_WORD_THRESHOLD=0.5
   ```

**9. Restart Russell**

   ```bash
   sudo systemctl restart russell
   sudo journalctl -u russell -f
   ```
   You should see `Listening for wake word './keywords/hey_russell.onnx'…`.
   Now say "Hey Russell" and watch for `Wake word fired.` in the log.

## Tuning the threshold

- **False fires** (it triggers when nobody said the wake word, e.g. while music is
  playing): bump `WAKE_WORD_THRESHOLD` up — try `0.6`, then `0.7`. Higher = stricter.
- **Won't fire** (you say "Hey Russell" and nothing happens): drop the threshold
  down to `0.4` or even `0.3`. If it's still bad, retrain with more pronunciation
  variants in the `target_phrase` list (e.g. add `"hey russ", "russell"`).

## Until you train your own

The default `hey_jarvis` model is a perfectly fine placeholder — short, two
syllables, low false-fire rate. Set `WAKE_WORD_MODEL=hey_jarvis` and you're
running on free, on-device wake word detection right now.
