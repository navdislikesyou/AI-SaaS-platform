import os

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from pathlib import Path

from backend.knowledge_agent.knowledge_agent import KnowledgeAgent


def main():

    pdf_path = (
        Path(__file__).parent
        / "data"
        / "documents"
        / "sample.pdf"
    )

    print("=" * 60)
    print("          ENTERPRISE KNOWLEDGE AGENT")
    print("=" * 60)

    agent = KnowledgeAgent()

    print("\nLoading Knowledge Base...\n")

    agent.ingest(str(pdf_path))

    print("Knowledge Base Ready!")
    print("=" * 60)

    while True:

        question = input("\nQuestion (type 'exit' to quit): ")

        if question.lower() == "exit":
            print("\nThank you for using the Knowledge Agent!\n")
            break

        answer, sources = agent.ask(question)

        print("\n" + "=" * 60)
        print("QUESTION")
        print("-" * 60)
        print(question)

        print("\nANSWER")
        print("-" * 60)
        print(answer)

        print("\nSOURCES")
        print("-" * 60)

        shown = set()

        for source in sources:

            key = (
                source["source"],
                source["page"],
            )

            if key in shown:
                continue

            shown.add(key)

            print(
                f"{Path(source['source']).name} (Page {source['page']})"
            )

        print("=" * 60)


if __name__ == "__main__":
    main()