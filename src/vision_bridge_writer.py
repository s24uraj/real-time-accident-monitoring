import json
import time
from datetime import datetime
from pathlib import Path


OUT_FILE = Path("vision_state.json")


def write_state(accident_prob: float, sequence_risk_prob: float, label: str) -> None:
  payload = {
      "accident_prob": max(0.0, min(1.0, accident_prob)),
      "sequence_risk_prob": max(0.0, min(1.0, sequence_risk_prob)),
      "label": label,
      "updated_at": datetime.now().isoformat(timespec="seconds"),
  }
  OUT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main():
  # Replace this loop with your actual DenseNet161 + LSTM inference outputs.
  # Example:
  # accident_prob = densenet_predict(frame)
  # sequence_risk_prob = lstm_predict(sequence_features)
  print("Writing demo predictions to vision_state.json. Press Ctrl+C to stop.")
  t = 0
  while True:
    t += 1
    if t % 20 < 5:
      write_state(0.08, 0.15, "non_accident")
    elif t % 20 < 12:
      write_state(0.42, 0.63, "risk_rising")
    else:
      write_state(0.95, 0.88, "accident")
    time.sleep(1)


if __name__ == "__main__":
  main()
