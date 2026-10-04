from langchain_ollama import ChatOllama


class LocalLLM:

    def __init__(self, model="llama3.1:8b", base_url=None):

        options = {
            "model": model,
            "temperature": 0,
        }

        if base_url:
            options["base_url"] = base_url

        self.llm = ChatOllama(**options)

    def generate(self, prompt):

        response = self.llm.invoke(prompt)

        return response.content.strip()