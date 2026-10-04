from langchain_ollama import ChatOllama

llm = ChatOllama(
    model="qwen3:8b",
    temperature=0,
)

response = llm.invoke(
    "In one sentence, explain what Retrieval-Augmented Generation (RAG) is."
)

print(response.content)