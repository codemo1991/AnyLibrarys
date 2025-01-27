import streamlit as st
from fastapi import FastAPI, HTTPException, UploadFile, File
from pymilvus import Collection, CollectionSchema, FieldSchema, DataType, Index, connections, utility
from sentence_transformers import SentenceTransformer
import numpy as np
from elasticsearch import Elasticsearch
from minio import Minio
from tika import parser
import os
import tempfile
import hashlib
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ✅ **初始化 MinIO**
MINIO_SERVER = os.getenv("MINIO_SERVER")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
BUCKET_NAME = os.getenv("BUCKET_NAME")

minio_client = Minio(
    MINIO_SERVER,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)
if not minio_client.bucket_exists(BUCKET_NAME):
    minio_client.make_bucket(BUCKET_NAME)

# ✅ **初始化 Elasticsearch**
ES_HOST = os.getenv("ES_HOST")
es = Elasticsearch(ES_HOST)
INDEX_NAME = os.getenv("ES_INDEX_NAME")

# 创建索引映射
index_mapping = {
    "mappings": {
        "properties": {
            "filename": {"type": "text"},
            "content": {"type": "text"},
            "file_url": {"type": "text"},
            "milvus_id": {"type": "long"},
            "file_md5": {"type": "keyword"}  # 添加md5字段
        }
    }
}

# 检查索引是否存在,不存在则创建
if not es.indices.exists(index=INDEX_NAME):
    es.indices.create(index=INDEX_NAME, body=index_mapping)

# ✅ **连接 Milvus**
connections.connect(
    host=os.getenv("MILVUS_HOST"),
    port=os.getenv("MILVUS_PORT")
)

# ✅ **创建 Collection**
collection_name = os.getenv("MILVUS_COLLECTION")
VECTOR_DIM = int(os.getenv("VECTOR_DIM"))

fields = [
    FieldSchema(name="id", dtype=DataType.INT64,
                is_primary=True, auto_id=True),
    FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=VECTOR_DIM)
]

schema = CollectionSchema(fields, description="Document embeddings for search")

# **检查 Collection 是否存在**
if utility.has_collection(collection_name):
    collection = Collection(name=collection_name)
    print(f"✅ Collection '{collection_name}' already exists.")
else:
    collection = Collection(name=collection_name, schema=schema)
    print(f"✅ Collection '{collection_name}' created.")

# ✅ **创建索引**
index_params = {
    "index_type": "IVF_FLAT",
    "metric_type": "L2",
    "params": {"nlist": 1024}
}
collection.create_index(field_name="vector", index_params=index_params)

# ✅ **加载 Collection**
collection.load()

# ✅ **初始化文本嵌入模型**
model = SentenceTransformer(os.getenv("MODEL_NAME"))


# ✅ **Streamlit UI**
st.title("📄 文档管理 & 语义搜索")

# ✅ **上传文件部分**
st.header("📤 文档上传")
uploaded_file = st.file_uploader("选择文件", type=['txt', 'pdf', 'doc', 'docx'])

if uploaded_file is not None:
    if st.button("上传文件"):
        with st.spinner('🔄 正在上传文件...'):
            temp_path = None
            try:
                # 创建临时文件
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                    file_content = uploaded_file.getbuffer()
                    tmp_file.write(file_content)
                    temp_path = tmp_file.name
                    
                    # 计算文件MD5
                    file_md5 = hashlib.md5(file_content).hexdigest()

                    # 检查是否存在同名且MD5相同的文件
                    # 检查文件是否已存在
                    es_result = es.search(index=INDEX_NAME, query={
                        "bool": {
                            "must": [
                                {"match": {"filename": uploaded_file.name}},
                                {"match": {"file_md5": file_md5}}
                            ]
                        }
                    })
                    
                    
                    if es_result["hits"]["total"]["value"] > 0:
                        st.success("✅ 文件已存在，无需重复上传!")
                    else:
                        # ✅ **存入 MinIO**
                        minio_client.fput_object(
                            BUCKET_NAME, uploaded_file.name, temp_path)
                        file_url = f"http://{MINIO_SERVER}/{BUCKET_NAME}/{uploaded_file.name}"

                        # ✅ **提取文本**
                        text = parser.from_file(temp_path).get("content", "").strip()
                        if not text:
                            st.error("❌ 无法提取文件内容")
                        else:
                            # ✅ **生成向量**
                            vector = model.encode(text).tolist()

                            # ✅ **存入 Milvus**
                            insert_result = collection.insert([[vector]])
                            milvus_id = insert_result.primary_keys[0]  # 获取插入的ID

                            # ✅ **存入 Elasticsearch**
                            document = {
                                "filename": uploaded_file.name,
                                "content": text,
                                "file_url": file_url,
                                "milvus_id": milvus_id,
                                "file_md5": file_md5
                            }
                            es.index(index=INDEX_NAME, document=document)

                            st.success("✅ 文件上传成功!")

            except Exception as e:
                st.error(f"⚠ 处理文件时出错: {str(e)}")
            finally:
                # 确保临时文件存在且没有被其他进程使用时再删除
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except PermissionError:
                        # 如果文件正在被使用，记录错误但不中断程序
                        print(f"Warning: Could not delete temporary file {temp_path}")


# ✅ **搜索部分**
st.header("🔍 文档搜索")
search_query = st.text_input("输入搜索关键词")

if st.button("🔍 搜索") and search_query:
    with st.spinner('⏳ 正在搜索...'):
        try:
            # ✅ **Elasticsearch 搜索**
            es_query = {
                "query": {
                    "match": {"content": search_query}
                },
                "_source": ["filename", "file_url", "content", "file_md5"],
                "size": 10,
                "highlight": {
                    "fields": {
                        "content": {
                            "fragment_size": 100,  # 减小为100字符
                            "number_of_fragments": 1,
                            "pre_tags": [""],
                            "post_tags": [""]
                        }
                    }
                }
            }
            es_results = es.search(index=INDEX_NAME, body=es_query)

            # ✅ **Milvus 向量搜索**
            query_vector = model.encode(search_query).tolist()
            search_results = collection.search(
                data=[query_vector], 
                anns_field="vector", 
                param={"metric_type": "L2", "params": {"nprobe": 10}},
                limit=5,
                output_fields=["id"]
            )
            milvus_ids = [result.entity.get("id") for result in search_results[0]]

            # ✅ **显示搜索结果**
            st.subheader("📌 搜索结果")

            # **Elasticsearch 结果**
            st.write("📄 文本匹配结果:")
            for hit in es_results["hits"]["hits"]:
                st.write(f"📂 文件名: {hit['_source']['filename']}")
                st.write(f"🔗 文件链接: {hit['_source']['file_url']}")
                # 安全获取file_md5字段
                file_md5 = hit['_source'].get('file_md5', '未知')
                st.write(f"📝 文件MD5: {file_md5}")
                
                # 获取匹配内容的上下文
                content = hit['_source']['content']
                highlight = hit.get('highlight', {}).get('content', [''])[0]
                
                if highlight:
                    start_pos = content.find(highlight)
                    if start_pos != -1:
                        context_start = max(0, start_pos - 50)  # 减小为50字符
                        context_end = min(len(content), start_pos + len(highlight) + 50)  # 减小为50字符
                        context = content[context_start:context_end]
                        
                        if context_start > 0:
                            context = "..." + context
                        if context_end < len(content):
                            context = context + "..."
                            
                        st.write("📝 相关内容:")
                        st.text(context)
                
                st.write("---")

            # **Milvus 结果**
            st.write("🔍 向量相似度结果:")
            for milvus_id in milvus_ids:
                # 通过ES查询获取对应文档内容
                es_query = {
                    "query": {
                        "term": {
                            "milvus_id": milvus_id
                        }
                    },
                    "_source": ["filename", "content", "file_md5"]
                }
                es_result = es.search(index=INDEX_NAME, body=es_query)
                if es_result["hits"]["hits"]:
                    doc = es_result["hits"]["hits"][0]["_source"]
                    content = doc["content"]
                    filename = doc["filename"]
                    # 安全获取file_md5字段
                    file_md5 = doc.get('file_md5', '未知')
                    
                    # 找到最相关的段落（这里简单地取中间部分作为示例）
                    content_len = len(content)
                    if content_len > 100:  # 如果内容超过100字符
                        start = max(0, content_len//2 - 50)
                        end = min(content_len, content_len//2 + 50)
                        context = "..." + content[start:end] + "..."
                    else:
                        context = content
                        
                    st.write(f"📂 文件名: {filename}")
                    st.write(f"📝 文件MD5: {file_md5}")
                    st.write("📝 相关内容:")
                    st.text(context)
                    st.write("---")

        except Exception as e:
            st.error(f"⚠ 搜索时出错: {str(e)}")
