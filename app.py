import os
import urllib.parse
from contextlib import asynccontextmanager
import psycopg2
from psycopg2.extras import DictCursor
from pgvector.psycopg2 import register_vector
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import warnings
from typing import List

# Import LangChain items
from langchain_community.document_loaders import PyPDFLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

load_dotenv()
os.environ["TOKENIZERS_PARALLELISM"] = "false"
warnings.filterwarnings('ignore')

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise ValueError("DATABASE_URL not found in environment")

# Load embedding model globally
print("Loading multilingual embedding model...")
embedding_model = HuggingFaceEmbeddings(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')

def get_db_connection():
    conn = psycopg2.connect(DB_URL)
    register_vector(conn)
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Enable pgvector extension
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        conn.commit()
        
        # Create pdfs table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pdfs (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) UNIQUE NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        
        # Create pdf_chunks table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pdf_chunks (
                id SERIAL PRIMARY KEY,
                pdf_id INT REFERENCES pdfs(id) ON DELETE CASCADE,
                page_number INT NOT NULL,
                content TEXT NOT NULL,
                embedding VECTOR(384) NOT NULL
            );
        """)
        conn.commit()
        
        # Create index on embedding
        cur.execute("CREATE INDEX IF NOT EXISTS pdf_chunks_embedding_idx ON pdf_chunks USING hnsw (embedding vector_cosine_ops);")
        conn.commit()
        print("Database initialized successfully.")
    except Exception as e:
        print("Error initializing database:", e)
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def index_pdf_file(file_path: str, filename: str):
    """
    Load, chunk, embed, and store a PDF file into Neon DB.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check if already exists
        cur.execute("SELECT id FROM pdfs WHERE filename = %s", (filename,))
        row = cur.fetchone()
        if row:
            print(f"File '{filename}' is already indexed.")
            return row[0]
            
        # Add to pdfs table
        cur.execute("INSERT INTO pdfs (filename) VALUES (%s) RETURNING id", (filename,))
        pdf_id = cur.fetchone()[0]
        conn.commit()
        
        print(f"Parsing PDF: {file_path}")
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        
        # Split documents
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=100,
            separators=["\n\n", "\n", " ", ""]
        )
        split_docs = text_splitter.split_documents(documents)
        print(f"Generated {len(split_docs)} chunks. Generating embeddings...")
        
        # Insert chunks and embeddings
        for doc in split_docs:
            page_num = doc.metadata.get("page", 0)
            content = doc.page_content
            
            # Embed content locally
            vector = embedding_model.embed_query(content)
            
            cur.execute("""
                INSERT INTO pdf_chunks (pdf_id, page_number, content, embedding)
                VALUES (%s, %s, %s, %s)
            """, (pdf_id, page_num, content, vector))
            
        conn.commit()
        print(f"Successfully indexed '{filename}'.")
        return pdf_id
    except Exception as e:
        print(f"Error indexing PDF {filename}:", e)
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

# Startup sync for 1.pdf
def sync_default_pdf():
    pdf_path = "1.pdf"
    if os.path.exists(pdf_path):
        print(f"Found default PDF: {pdf_path}. Indexing if needed...")
        try:
            index_pdf_file(pdf_path, "1.pdf")
        except Exception as e:
            print("Failed to index default PDF:", e)
    else:
        print(f"Default PDF '{pdf_path}' not found in root directory.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB on startup
    init_db()
    # Sync default 1.pdf if it exists
    sync_default_pdf()
    yield

app = FastAPI(lifespan=lifespan)

class QueryRequest(BaseModel):
    query: str

@app.post("/api/chat")
async def chat(request: QueryRequest):
    query_text = request.query.strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
        
    try:
        # 1. Embed query locally
        query_vector = embedding_model.embed_query(query_text)
        
        # 2. Query Neon DB for top chunks
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        
        # Perform cosine similarity search (pgvector <=>)
        cur.execute("""
            SELECT c.content, c.page_number, p.filename
            FROM pdf_chunks c
            JOIN pdfs p ON c.pdf_id = p.id
            ORDER BY c.embedding <=> %s::vector
            LIMIT 5
        """, (query_vector,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        if not rows:
            return {
                "result": "No document content was found in the database. Please upload a PDF first.",
                "source_documents": []
            }
            
        # Format context for Gemini
        context_parts = []
        source_docs = []
        for row in rows:
            context_parts.append(row["content"])
            source_docs.append({
                "page_number": row["page_number"] + 1,
                "filename": row["filename"],
                "content_preview": row["content"][:200]
            })
            
        context_text = "\n\n".join(context_parts)
        
        # 3. Initialize model and generate answer
        google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if google_key:
            os.environ["GOOGLE_API_KEY"] = google_key
            llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0.1)
            print("Using Gemini model for chat response")
        else:
            # Fallback to OpenAI
            llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0.1)
            print("Using OpenAI model for chat response")
            
        prompt = ChatPromptTemplate.from_template(
            "Answer the question based only on the following context:\n{context}\n\nQuestion: {question}"
        )
        
        chain = prompt | llm | StrOutputParser()
        result_text = chain.invoke({"context": context_text, "question": query_text})
        
        return {
            "result": result_text,
            "source_documents": source_docs
        }
    except Exception as e:
        print("Error in /api/chat:", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
    temp_path = f"temp_{file.filename}"
    try:
        # Save upload temporarily
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        # Index the file into DB
        index_pdf_file(temp_path, file.filename)
        return {"status": "success", "filename": file.filename}
    except Exception as e:
        print(f"Error in /api/upload for {file.filename}:", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.get("/api/documents")
async def get_documents():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    try:
        cur.execute("SELECT filename, uploaded_at FROM pdfs ORDER BY uploaded_at DESC")
        rows = cur.fetchall()
        docs = [{"filename": row["filename"], "uploaded_at": row["uploaded_at"].strftime("%Y-%m-%d %H:%M")} for row in rows]
        return docs
    except Exception as e:
        print("Error in /api/documents:", e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

# Serve static files
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
