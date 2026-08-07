from langchain_ollama import ChatOllama


class LocalLLM:

    def __init__(self):

        self.llm = ChatOllama(
            model="llama3.1:8b",
            temperature=0,
        )

    def generate(self, prompt):

        response = self.llm.invoke(prompt)

        return response.content.strip()