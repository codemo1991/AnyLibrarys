# 文档上传与语义搜索

## 整体架构
- es存储精确文本
- tika提取文本
- milvus存储向量
- minio存储文件
- streamlit 前端展示

## 目录划分
- /test 测试目录
- /upload.py 文档上传与语义搜索
- /requirements.txt 依赖
- /docker-compose.yml docker 文件 启动minio、milvus、elasticsearch

## 环境准备
- 启动docker-desktop
  - docker-compose down -v [minio、milvus、elasticsearch] 删除容器
  - docker-compose up -d [minio、milvus、elasticsearch] 启动容器
- 执行docker-compose.yml 启动minio、milvus、elasticsearch
- 执行 pip install -r requirements.txt 安装依赖
- streamlit run ./upload.py 启动程序

