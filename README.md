# 飞书多维表格论文分析器 v1

这是一个给飞书多维表格用的论文自动分析服务。

你在表里上传 PDF 或粘贴 arXiv 链接后，系统会自动：

1. 触发 webhook
2. 解析论文内容
3. 调用 OpenAI 兼容模型
4. 把 8 个中文分析模块回填到多维表格

## 先看哪里

如果你是第一次接手这个项目，不要先看代码，先看这里：

- 从零部署指南：[QUICKSTART.md](./QUICKSTART.md)
- 环境变量模板：[.env.example](./.env.example)

## 这个项目适合谁

- 已经在用飞书多维表格做文献管理
- 想在表格中直接得到论文分析结果
- 想兼容 OpenAI 官方或其他 OpenAI 兼容模型服务

## 功能概览

- 输入支持：
  - `arXiv链接`
  - 文本型 `PDF附件`
- 输出字段：
  - `0_摘要翻译`
  - `1_方法动机`
  - `2_方法设计`
  - `3_与其他方法对比`
  - `4_实验表现与优势`
  - `5_学习与应用`
  - `6_总结`
  - `7_关键词领域`
- 系统字段：
  - `分析状态`
  - `错误信息`
  - `来源类型`
  - `来源哈希`
  - `论文ID`
  - `最后分析时间`

## 技术结构

```text
Feishu Bitable -> Automation Webhook -> FastAPI -> SQLite Queue -> Worker -> LLM -> Bitable Writeback
```

## 本地开发

安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

启动 API：

```bash
uvicorn paper_analyzer.main:app --host 0.0.0.0 --port 8000
```

启动 Worker：

```bash
python -m paper_analyzer.services.worker
```

健康检查：

```bash
curl http://127.0.0.1:8000/healthz
```

## 测试

这个环境下 `pytest` 的默认 capture 插件会触发段错误，所以请这样跑：

```bash
python3 -m pytest -p no:capture
```

## 限制

- v1 不支持 OCR
- 不抓 DOI/出版社网页
- 只覆盖 arXiv 和可提取文本的 PDF
- 默认数据库是 SQLite，适合单实例部署
