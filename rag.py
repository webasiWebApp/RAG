import os
import warnings
from typing import List
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel

load_dotenv()
os.environ["TOKENIZERS_PARALLELISM"] = "false"

warnings.filterwarnings('ignore')

def load_pdf(file_path: str) -> List[Document]:
    try:
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        return documents
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
        return []
    except Exception as e:
        print(f"Error loading PDF: {e}")
        return []

def split_documents(documents: List[Document], chunk_size: int = 500, chunk_overlap: int =100) -> List[Document]:
    """
    Split documents into smaller chunks.
    
    Args:
        documents (List[Document]): Input documents
        chunk_size (int): Size of each text chunk
        chunk_overlap (int): Number of characters to overlap between chunks
    
    Returns:
        List[Document]: Split documents
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, 
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""]
    )
    return text_splitter.split_documents(documents)

def create_vector_store(documents: List[Document], embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'):
    """
    Create a vector store from documents.
    
    Args:
        documents (List[Document]): Input documents
        embedding_model (str): Hugging Face embedding model to use
    
    Returns:
        Chroma: Vector store
    """
    try:
        embeddings = HuggingFaceEmbeddings(model_name=embedding_model)
        return Chroma.from_documents(documents, embeddings)
    except Exception as e:
        print(f"Error creating vector store: {e}")
        return None

def create_qa_chain(vector_store, model: str = None):
    """
    Create a question-answering chain using modern LCEL.
    
    Args:
        vector_store: Vector store to use as retriever
        model (str): Model name to use
    
    Returns:
        dict-like Runnable: Question-answering chain
    """
    try:
        # Check if Google/Gemini API key is available
        google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if google_key:
            # Set GOOGLE_API_KEY in env because ChatGoogleGenerativeAI expects it
            os.environ["GOOGLE_API_KEY"] = google_key
            from langchain_google_genai import ChatGoogleGenerativeAI
            model_name = model or "gemini-3.5-flash"
            print(f"Using Gemini model: {model_name}")
            llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.1)
        else:
            model_name = model or "gpt-3.5-turbo"
            print(f"Using OpenAI model: {model_name}")
            llm = ChatOpenAI(model_name=model_name, temperature=0.1)

        retriever = vector_store.as_retriever(
            search_type="similarity", 
            search_kwargs={"k": 3}  # Retrieve top 3 most similar chunks
        )

        # Define a prompt template
        prompt = ChatPromptTemplate.from_template(
            "Answer the question based only on the following context:\n{context}\n\nQuestion: {question}"
        )

        # Helper function to format retrieved documents
        def format_docs(docs):
            return "\n\n".join(doc.page_content for doc in docs)

        # Construct the modern LCEL chain to return BOTH result and source_documents
        # to match the old RetrievalQA behavior
        qa_chain = RunnableParallel(
            {
                "context": (lambda x: x["query"]) | retriever,
                "question": lambda x: x["query"]
            }
        ) | {
            "result": (
                lambda x: {
                    "context": format_docs(x["context"]),
                    "question": x["question"]
                }
            ) | prompt | llm | StrOutputParser(),
            "source_documents": lambda x: x["context"]
        }

        return qa_chain

    except Exception as e:
        print(f"Error creating QA chain: {e}")
        return None


def main():
    # PDF file path
    pdf_path = "ICT.pdf"
    
    print(f"Loading {pdf_path}... This may take a moment for large files.")
    # Load PDF
    documents = load_pdf(pdf_path)
    if not documents:
        print("No Document was found.")
        return
    
    print(f"Splitting document into chunks...")
    # Split documents
    split_docs = split_documents(documents)
    
    print(f"Creating vector store using sentence-transformers...")
    # Create vector store
    vector_store = create_vector_store(split_docs)
    if not vector_store:
        print("Failed to create vector store.")
        return
    
    print(f"Initializing QA chain with OpenAI GPT model...")
    # Create QA chain
    qa_chain = create_qa_chain(vector_store)
    if not qa_chain:
        print("Failed to initialize QA chain.")
        return
    
    print("\nRAG Pipeline ready! Type your question below (or type 'exit' to quit).")
    while True:
        try:
            query = input("\nQuestion: ").strip()
            if not query:
                continue
            if query.lower() in ['exit', 'quit']:
                print("Goodbye!")
                break
                
            print("Searching and generating answer...")
            response = qa_chain.invoke({"query": query})
            
            print("\nAnswer:", response['result'])
            print("\nSource Documents:")
            for doc in response['source_documents']:
                page_num = doc.metadata.get('page')
                page_str = str(page_num + 1) if isinstance(page_num, int) else 'N/A'
                content_preview = doc.page_content[:200].replace('\n', ' ')
                print(f"- Page {page_str}: {content_preview}...")
        
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error processing query: {e}")

if __name__ == "__main__":
    main()