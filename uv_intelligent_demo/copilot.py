import os
from pathlib import Path
from typing import Tuple, List

from langchain_mistralai import ChatMistralAI
from langchain_community.chat_models import ChatOllama
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

def _build_llm():
    api_key = os.getenv("MISTRAL_API_KEY")
    if api_key:
        return ChatMistralAI(mistral_api_key=api_key, model="mistral-large-latest")
    else:
        # Fallback to local Ollama
        return ChatOllama(model="mistral")

def answer_question(root_path: Path | str, query: str) -> Tuple[str, List[str]]:
    llm = _build_llm()
    
    db_path = Path(root_path) / "uv_intelligent_demo" / "chroma_db"
    
    try:
        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        vectorstore = Chroma(persist_directory=str(db_path), embedding_function=embeddings)
        docs = vectorstore.similarity_search(query, k=4)
        
        context = "\n\n".join([doc.page_content for doc in docs])
        # Try to make sources unique and presentable
        sources = list(dict.fromkeys([doc.metadata.get("source", "Unknown Document") for doc in docs]))
    except Exception as e:
        context = f"Error retrieving context: {e}"
        sources = []
        
    prompt = (
        f"You are an AI Copilot assisting a UV reactor operator.\n"
        f"Use the following retrieved context to help answer the user's query.\n"
        f"If the context doesn't contain the answer, say so.\n\n"
        f"Context:\n{context}\n\n"
        f"Query:\n{query}"
    )
    
    response = llm.invoke(prompt)
    return response.content, sources
