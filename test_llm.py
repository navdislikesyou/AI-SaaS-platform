from langchain_ollama import ChatOllama

llm = ChatOllama(
    model="llama3.1:8b",
    temperature=0,
)

response = llm.invoke("Say hello in one sentence.")

print(response.content)