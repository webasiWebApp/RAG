# PDF RAG Chat Tool (PostgreSQL pgvector & Gemini/OpenAI)

A premium web-based Question Answering (RAG) tool that parses PDF documents, indexes their vector embeddings into a Neon PostgreSQL database using `pgvector`, and provides a stunning, interactive glassmorphic chat frontend using Gemini or OpenAI models.

## Features

- **Premium Web Interface**: Clean, dark-themed, glassmorphic chat UI with slide-in message animations, pulse-thinking state skeleton loaders, and full markdown rendering support.
- **Persistent Vector Storage**: Integrates with a Neon PostgreSQL database via the `pgvector` extension to store chunk embeddings locally or in the cloud.
- **Default Document Loading**: Automatically indexes the default document `1.pdf` on server startup.
- **Dynamic PDF Ingestion**: Drag-and-drop or browse custom PDF files to parse, chunk, and embed them on the fly.
- **Dual LLM Compatibility**: Uses **Gemini 3.5 Flash** (recommended) or OpenAI GPT models based on the environment keys.
- **Citation Badges**: Every generated answer displays the exact source page numbers and matching document fragments.

## Prerequisites

- Python 3.8+
- Neon PostgreSQL connection string (with `pgvector` support)
- Gemini API Key (`GEMINI_API_KEY` or `GOOGLE_API_KEY`) or OpenAI API Key (`OPENAI_API_KEY`)

## Installation & Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/Pasindu9225/RAG.git
   cd RAG
   ```

2. **Set Up the Virtual Environment**:
   ```bash
   python -m venv .venv
   # Activate on Windows:
   .venv\Scripts\activate
   # Activate on macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**:
   Create a `.env` file in the project root folder:
   ```env
   # Database connection
   DATABASE_URL=postgresql://neondb_owner:npg_qZL64QcXlTIW@ep-rapid-glitter-avm08fx3-pooler.c-11.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require

   # LLM Providers (Add at least one)
   GEMINI_API_KEY=your_gemini_api_key
   # OR
   OPENAI_API_KEY=your_openai_api_key
   ```

## Usage

1. **Place Default PDF**:
   Place a PDF named `1.pdf` in the root folder. It will automatically load and index on server startup if it is not already indexed in the database.

2. **Start the Web Application**:
   Run the FastAPI backend server:
   ```bash
   python app.py
   ```

3. **Access the Chat Interface**:
   Open your browser and navigate to:
   [http://127.0.0.1:8000](http://127.0.0.1:8000)

4. **Interactive Controls**:
   - **Chat Tab**: Type your queries. Responses render Markdown, bold headers, code snippets, lists, and reference cards pointing to the source pages.
   - **Upload Documents Tab**: Import new PDFs directly via drag-and-drop.
   - **Sidebar**: Displays the list of all indexed documents in the database.

## Architecture

- **Backend**: FastAPI (Python) serving REST endpoints for uploads, chat queries, and document listing.
- **Database Schema**:
  - `pdfs`: Stores uploaded filename metadata.
  - `pdf_chunks`: Stores text chunks and their 384-dimension embeddings using the `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` model.
- **Frontend**: Single-page vanilla HTML/CSS/JS application with custom-built responsive layout elements and glassmorphic designs.
