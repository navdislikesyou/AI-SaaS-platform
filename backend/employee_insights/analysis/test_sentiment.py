from backend.employee_insights.analysis.sentiment_analyzer import SentimentAnalyzer


analyzer = SentimentAnalyzer()

samples = [
    "Navneet did an excellent job completing the project.",
    "The employee consistently misses deadlines.",
    "The meeting is scheduled for Monday.",
    "The manager appreciated his dedication and hard work.",
    "The submitted work contained several serious mistakes.",
    "Although the work was late, the final result was excellent."
]

results = analyzer.analyze_batch(samples)

print("\nSENTIMENT ANALYSIS RESULTS")
print("=" * 70)

for result in results:
    print(f"\nText: {result['text']}")
    print(f"Sentiment: {result['sentiment']}")
    print(f"Confidence: {result['confidence']}")