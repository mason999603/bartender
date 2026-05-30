# Custom wake-word models

Drop your trained openWakeWord `.onnx` file in here, then point `WAKE_WORD_MODEL`
in `/opt/russell/pi_client/.env` at its path. Example:

```
WAKE_WORD_MODEL=./keywords/hey_russell.onnx
```

## Training "Hey Russell" yourself (free, ~20 minutes)

openWakeWord ships a Google Colab notebook that trains a model in your browser
using their GPU. You don't record samples — TTS synthesises hundreds of variants
of the phrase and trains on those.

1. Open the official notebook:
   <https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb>
   *(this is openWakeWord's `automatic_model_training.ipynb` — bookmark
   <https://github.com/dscripka/openWakeWord> for the latest link)*

2. In the "Target phrase" cell, set:
   ```python
   target_phrase = "hey russell"
   ```
   You can train multiple variants in one go — e.g. `["hey russell", "russell"]`.

3. Click **Runtime → Run all**. Training takes 10-20 mins on a free Colab T4.

4. At the end the notebook downloads `hey_russell.onnx`. Copy it into this
   folder on the Pi:
   ```
   scp hey_russell.onnx pi@russell-pi:/opt/russell/pi_client/keywords/
   ```

5. Update `.env`:
   ```
   WAKE_WORD_MODEL=./keywords/hey_russell.onnx
   WAKE_WORD_THRESHOLD=0.5      # tune up if it false-fires
   ```

6. Restart Russell:
   ```
   sudo systemctl restart russell    # if you set up the service
   # OR
   pkill -f russell_pi_client.py && cd /opt/russell/pi_client && \
     source venv/bin/activate && \
     nohup python russell_pi_client.py > russell.log 2>&1 &
   ```

## Tuning the threshold

- **False fires** (it triggers when nobody said the wake word): bump
  `WAKE_WORD_THRESHOLD` up — try `0.6`, then `0.7`. Higher = stricter.
- **Won't fire** (you say it, nothing happens): drop the threshold down to
  `0.4` or even `0.3`. Or train with more pronunciation variants.

## Until you train your own

The default `hey_jarvis` model is a perfectly fine placeholder — short, two
syllables, low false-fire rate. Set `WAKE_WORD_MODEL=hey_jarvis` and you're
running on free, on-device wake word detection right now.
