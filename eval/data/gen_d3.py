"""Dataset D3 Initializer: Emotion Evaluation Audio and Transcript Corpus.

Creates eval/data/d3/labels.csv with realistic English and Hinglish customer speech clips,
5-point valence scales, and dual annotator labels.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

SAMPLE_D3_CLIPS = [
    # Angry
    ("clip_001", "eval/data/d3/audio/clip_001.wav", "Yeh teesri baar call kar raha hoon aur mera router abhi tak replace nahi hua! Aap log fraud kar rahe hain!", "angry", 1, "angry", 1),
    ("clip_002", "eval/data/d3/audio/clip_002.wav", "I have been on hold for forty minutes and your agent hung up on me. Transfer me to a supervisor right now!", "angry", 1, "angry", 1),
    ("clip_003", "eval/data/d3/audio/clip_003.wav", "Paise poore lete ho har mahine aur connection adhe din band rehta hai! Stop lying to me!", "angry", 1, "frustrated", 2),
    ("clip_004", "eval/data/d3/audio/clip_004.wav", "Cancel my subscription immediately! I am not paying a single rupee for this useless service!", "angry", 1, "angry", 1),
    # Frustrated
    ("clip_005", "eval/data/d3/audio/clip_005.wav", "Shaam ko speed itni drop ho jati hai ki meri video calls attend nahi ho pa rahi hain. Please do something.", "frustrated", 2, "frustrated", 2),
    ("clip_006", "eval/data/d3/audio/clip_006.wav", "My monthly invoice has an extra roaming charge of 450 rupees that I never activated.", "frustrated", 2, "frustrated", 2),
    ("clip_007", "eval/data/d3/audio/clip_007.wav", "Technician ne subah ka time diya tha aur ab shaam ke paanch baj gaye hain, koi update nahi mila.", "frustrated", 2, "angry", 1),
    ("clip_008", "eval/data/d3/audio/clip_008.wav", "I keep getting automated payment failed alerts even though the money was debited from my bank.", "frustrated", 2, "frustrated", 2),
    ("clip_009", "eval/data/d3/audio/clip_009.wav", "Wi-Fi connection bedroom me baar baar disconnect ho jata hai, signal bahut weak hai.", "frustrated", 2, "sad", 2),
    # Sad / Disappointed
    ("clip_010", "eval/data/d3/audio/clip_010.wav", "Main bahut pareshan ho gaya hoon, pichle ek hafte seroz complaints kar raha hoon but no resolution.", "sad", 2, "sad", 2),
    ("clip_011", "eval/data/d3/audio/clip_011.wav", "I trusted your brand for my remote job, but this constant downtime is risking my employment.", "sad", 2, "frustrated", 2),
    ("clip_012", "eval/data/d3/audio/clip_012.wav", "Agar service theek nahi ho sakti toh bata dijiye, main dusra provider dekh leta hoon.", "sad", 2, "sad", 2),
    # Neutral
    ("clip_013", "eval/data/d3/audio/clip_013.wav", "Mera billing cycle kaunsi date ko reset hota hai please confirm kijiye.", "neutral", 3, "neutral", 3),
    ("clip_014", "eval/data/d3/audio/clip_014.wav", "Could you check whether optical fiber lines are available in Indiranagar 2nd stage?", "neutral", 3, "neutral", 3),
    ("clip_015", "eval/data/d3/audio/clip_015.wav", "Mujhe apna registered email address update karwana hai account pe.", "neutral", 3, "neutral", 3),
    ("clip_016", "eval/data/d3/audio/clip_016.wav", "What documents are required to transfer broadband connection ownership?", "neutral", 3, "neutral", 3),
    ("clip_017", "eval/data/d3/audio/clip_017.wav", "Ek baar mera current plan validity aur remaining data quota bata dijiye.", "neutral", 3, "calm", 3),
    # Calm
    ("clip_018", "eval/data/d3/audio/clip_018.wav", "Haan theek hai, aap ticket number note kara dijiye, main kal subah check kar lunga.", "calm", 4, "calm", 4),
    ("clip_019", "eval/data/d3/audio/clip_019.wav", "Understood. Please schedule the engineer inspection between 10 AM and 12 PM tomorrow.", "calm", 4, "calm", 4),
    ("clip_020", "eval/data/d3/audio/clip_020.wav", "Aapne steps explain kiye the, maine router restart kiya aur lights green ho gayi hain.", "calm", 4, "calm", 4),
    ("clip_021", "eval/data/d3/audio/clip_021.wav", "Koi jaldi nahi hai, jab team free ho tab schedule kar dena visit.", "calm", 4, "calm", 4),
    # Happy / Delighted
    ("clip_022", "eval/data/d3/audio/clip_022.wav", "Aapka voice bot bahut fast answer de raha hai, ticket do minute me raise ho gaya! Bahut badhiya.", "happy", 5, "happy", 5),
    ("clip_023", "eval/data/d3/audio/clip_023.wav", "The technician arrived right on time and replaced the faulty fiber cable. My speed is back to 300 Mbps, thanks!", "happy", 5, "happy", 5),
    ("clip_024", "eval/data/d3/audio/clip_024.wav", "Refund mere account me credit ho gaya hai. Aapki service aur promptness sach me bahut achhi hai.", "happy", 5, "happy", 5),
    ("clip_025", "eval/data/d3/audio/clip_025.wav", "Thank you so much! You resolved my problem on the first call itself without bouncing me around.", "happy", 5, "happy", 5),
]


def create_d3_dataset(out_file: str = "eval/data/d3/labels.csv") -> Path:
    out_p = Path(out_file)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "clip_id",
        "audio_path",
        "transcript",
        "annotator_1_label",
        "annotator_1_valence",
        "annotator_2_label",
        "annotator_2_valence",
    ]

    with open(out_p, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        for row in SAMPLE_D3_CLIPS:
            writer.writerow(row)

    print(f"Dataset D3 created with {len(SAMPLE_D3_CLIPS)} clips at: {out_p}")
    return out_p


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="eval/data/d3/labels.csv")
    args = parser.parse_args()
    create_d3_dataset(args.out)
