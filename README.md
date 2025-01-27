# Universal Library
## **Document Upload and Search System**

## Overall Concept
With the existence of vast amounts of documents and materials, many scenarios require tracking documents based on specific sentences or images, along with interpreting document content. In traditional search operations, combining search engines and vector queries with LLM can achieve many unexpected extended functionalities.

## Architecture
- Elasticsearch: Stores precise text, provides accurate queries
- Apache Tika: Extracts text from various document formats
- Milvus: Stores vector data, provides vector similarity search
- Minio: Stores files, provides file upload and download capabilities
- Streamlit: Frontend interface

## Directory Structure
- /test: Testing directory
- /upload.py: Document upload and semantic search, program entry point
- /requirements.txt: Dependency definitions
- /docker-compose.yml: Docker configuration file for launching Minio, Milvus, Elasticsearch, and Kibana

## Environment Setup
- Start docker-desktop
  - docker-compose down -v [minio, milvus, elasticsearch] to remove containers
  - docker-compose up -d [minio, milvus, elasticsearch] to start containers
- Execute docker-compose.yml to launch Minio, Milvus, and Elasticsearch
- Run `pip install -r requirements.txt` to install dependencies
- Execute `streamlit run ./upload.py` to start the application

