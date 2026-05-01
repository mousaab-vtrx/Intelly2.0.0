import os
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

def main():
    root_dir = Path(__file__).resolve().parent
    docs_dir = root_dir / "external-resources" / "docs"
    db_path = root_dir / "chroma_db"
    
    # 1. Load Documents
    print("Loading documents...")
    documents = []
    
    pdf_path = docs_dir / "uv_reactor_documentation.pdf"
    if pdf_path.exists():
        pdf_loader = PyPDFLoader(str(pdf_path))
        documents.extend(pdf_loader.load())
        print(f"Loaded {pdf_path.name}")
    else:
        print(f"Warning: {pdf_path.name} not found.")

    txt_path = docs_dir / "maintenance_sop.txt"
    if txt_path.exists():
        txt_loader = TextLoader(str(txt_path))
        documents.extend(txt_loader.load())
        print(f"Loaded {txt_path.name}")
    else:
        print(f"Warning: {txt_path.name} not found.")

    if not documents:
        print("No documents found. Exiting.")
        return

    # 2. Split Documents into chunks
    print(f"Splitting {len(documents)} pages/files into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Generated {len(chunks)} chunks.")

    # 3. Embed and persist to ChromaDB
    print("Initializing embedding model...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    print(f"Adding chunks to vector database at {db_path}...")
    vectorstore = Chroma(
        persist_directory=str(db_path),
        embedding_function=embeddings
    )
    
    # Add documents (this appends to the existing database by default)
    vectorstore.add_documents(chunks)
    
    print("Successfully added documents to the database!")

if __name__ == "__main__":
    main()
