
import torch
from transformers import pipeline


class SentimentAnalyzer:

    MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"

    def __init__(self):
        self.device = 0 if torch.cuda.is_available() else -1

        self.classifier = pipeline(
            "text-classification",
            model=self.MODEL_NAME,
            device=self.device
        )

    def analyze(self, text):
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty.")

        result = self.classifier(
            text,
            truncation=True
        )[0]

        return {
            "text": text,
            "sentiment": result["label"].upper(),
            "confidence": round(result["score"], 4)
        }

    def analyze_batch(self, texts):
        valid_texts = [
            text for text in texts
            if isinstance(text, str) and text.strip()
        ]

        if not valid_texts:
            return []

        results = self.classifier(
            valid_texts,
            batch_size=8,
            truncation=True
        )

        return [
            {
                "text": text,
                "sentiment": result["label"].upper(),
                "confidence": round(result["score"], 4)
            }
            for text, result in zip(valid_texts, results)
        ]
