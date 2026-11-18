import gc
import torch
from transformers import pipeline


DISTILBERT = "distilbert/distilbert-base-uncased-finetuned-sst-2-english"

ROBERTA = "cardiffnlp/twitter-roberta-base-sentiment-latest"

device = 0 if torch.cuda.is_available() else -1

samples = [
    "Navneet did an excellent job completing the project.",
    "The employee consistently misses deadlines.",
    "The meeting is scheduled for Monday.",
    "The manager appreciated his dedication and hard work.",
    "The submitted work contained several serious mistakes.",
    "Although the work was late, the final result was excellent.",
    "Please find the attached monthly report.",
    "Thank you for helping the team complete the assignment.",
    "The employee failed to follow the instructions.",
    "The quarterly review will take place next week.",
    "His performance has improved significantly.",
    "We are still waiting for the pending deliverables.",
    "The presentation was neither particularly good nor bad.",
    "I appreciate your efforts, but several errors remain.",
    "The employee demonstrated outstanding leadership."
]


def load_model(model_name):
    return pipeline(
        "text-classification",
        model=model_name,
        device=device
    )


def main():

    print("\nLoading DistilBERT...")
    distilbert = load_model(DISTILBERT)

    distilbert_results = distilbert(
        samples,
        batch_size=8,
        truncation=True
    )

    del distilbert
    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    print("\nLoading CardiffNLP RoBERTa...")
    roberta = load_model(ROBERTA)

    roberta_results = roberta(
        samples,
        batch_size=8,
        truncation=True
    )

    print("\nMODEL COMPARISON")
    print("=" * 100)

    for i, text in enumerate(samples):

        d = distilbert_results[i]
        r = roberta_results[i]

        print(f"\nText: {text}")

        print(
            f"DistilBERT: {d['label']} "
            f"({d['score']:.4f})"
        )

        print(
            f"RoBERTa: {r['label']} "
            f"({r['score']:.4f})"
        )

        print("-" * 100)


if __name__ == "__main__":
    main()