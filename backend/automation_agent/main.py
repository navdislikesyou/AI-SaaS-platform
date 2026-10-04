from app.core.config import get_settings
from automation_agent.automation_agent import AutomationAgent
from automation_agent.llm.local_llm import LocalLLM


def main():

    settings = get_settings()

    print("=" * 60)
    print("      ENTERPRISE AUTOMATION AGENT")
    print("=" * 60)

    agent = AutomationAgent(
        llm=LocalLLM(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
        ),
    )

    while True:

        instruction = input(
            "\nEnter your instruction (or type 'exit'): "
        )

        if instruction.lower() == "exit":
            break

        meeting, recipients, email = agent.execute(
            instruction
        )

        print("\n" + "=" * 60)

        print("MEETING DETAILS")
        print("-" * 60)

        print(f"Title : {meeting['title']}")
        print(f"Date  : {meeting['date']}")
        print(f"Time  : {meeting['time']}")
        print(f"Venue : {meeting['venue']}")

        print("\nRECIPIENTS")
        print("-" * 60)

        for person in recipients:

            print(
                f"{person['name']} <{person['email']}>"
            )

        print("\nSUBJECT")
        print("-" * 60)

        print(
            f"{meeting['title']} Meeting Invitation"
        )

        print("\nEMAIL")
        print("-" * 60)

        print(email)

        print("\nSTATUS")
        print("-" * 60)

        print("✓ Email Generated Successfully")
        print("✓ Ready to Send")

        print("=" * 60)


if __name__ == "__main__":
    main()