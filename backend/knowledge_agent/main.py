from pathlib import Path

from backend.knowledge_agent.knowledge_agent import KnowledgeAgent


def main():

    # =========================================================
    # PROJECT ROOT
    # =========================================================

    project_root = Path(__file__).resolve().parents[2]

    # =========================================================
    # DOCUMENT PATH
    # =========================================================

    document_path = (
        project_root
        / "backend"
        / "knowledge_agent"
        / "data"
        / "documents"
        / "sample.pdf"
    )

    # =========================================================
    # INITIALIZE KNOWLEDGE AGENT
    # =========================================================

    agent = KnowledgeAgent()

    # =========================================================
    # LOAD / INDEX KNOWLEDGE BASE
    # =========================================================

    print("\nLoading Knowledge Base...\n")

    agent.ingest(
        str(document_path)
    )

    # =========================================================
    # INTERACTIVE QUESTION LOOP
    # =========================================================

    print("\n" + "=" * 70)
    print("KNOWLEDGE AGENT")
    print("=" * 70)

    print("\nAsk questions about the uploaded documents.")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:

        try:

            question = input("Question: ").strip()

        except KeyboardInterrupt:

            print("\n\nExiting Knowledge Agent.")
            break

        except EOFError:

            print("\n\nExiting Knowledge Agent.")
            break

        # -----------------------------------------------------
        # Ignore empty input
        # -----------------------------------------------------

        if not question:
            continue

        # -----------------------------------------------------
        # Exit
        # -----------------------------------------------------

        if question.lower() in {
            "exit",
            "quit",
            "q"
        }:

            print("\nExiting Knowledge Agent.")
            break

        # -----------------------------------------------------
        # Ask Knowledge Agent
        # -----------------------------------------------------

        try:

            result = agent.ask(question)

            # =================================================
            # ANSWER
            # =================================================

            print("\n" + "=" * 70)
            print("ANSWER")
            print("=" * 70)

            print(
                result["answer"]
            )

            # =================================================
            # SOURCES
            # =================================================

            print("\n" + "-" * 70)
            print("SOURCES")
            print("-" * 70)

            if result["sources"]:

                for source in result["sources"]:

                    file_name = Path(
                        source["source"]
                    ).name

                    page_start = source[
                        "page_start"
                    ]

                    page_end = source[
                        "page_end"
                    ]

                    if page_start == page_end:

                        print(
                            f"- {file_name} "
                            f"(Page {page_start})"
                        )

                    else:

                        print(
                            f"- {file_name} "
                            f"(Pages {page_start}-{page_end})"
                        )

            else:

                print("No sources available.")

            print()

        except Exception as e:

            print(
                "\nError while processing question:"
            )

            print(e)

            print()


if __name__ == "__main__":
    main()