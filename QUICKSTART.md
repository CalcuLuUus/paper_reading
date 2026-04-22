# Quickstart: 从零搭建飞书论文分析器

这份文档是给“第一次接触这个项目的人”准备的。

你最终会得到这样一个效果：

1. 你在飞书多维表格里新建一条记录。
2. 你上传 PDF，或者粘贴 arXiv 链接。
3. 飞书自动调用你的后端服务。
4. 后端读取论文，调用 OpenAI 兼容模型分析。
5. 8 个分析模块自动回填到表格里。

如果你现在对代码一头雾水，按这份文档从上到下做，不需要先理解源码。

## 1. 先理解这套东西由什么组成

这个项目一共只有 4 个部分：

- 飞书多维表格：你平时使用的界面，负责上传 PDF、贴 arXiv 链接、展示结果。
- 飞书自动化：当记录变化时，自动发一个 HTTP 请求给你的服务。
- API 服务：接收飞书请求，把任务放进队列。
- Worker：真正去下载论文、调用模型、写回分析结果。

你可以把它理解成：

```text
飞书表格 -> 飞书自动化 -> API 服务 -> Worker -> 模型分析 -> 回写飞书表格
```

## 2. 准备工作

开始前你需要有这些东西：

- 一台能跑 Python 的机器
- Python 3.11 或更高版本
- 一个飞书开放平台应用
- 一个 OpenAI 兼容 API
- 一个能被飞书访问到的 HTTP 地址

最后一项很重要。

如果你本地电脑直接跑服务，飞书是访问不到 `localhost` 的。你需要：

- 部署到云服务器，或者
- 用 `ngrok` / `cloudflared` 之类工具把本地端口暴露成公网 URL

第一版建议你直接用：

- 本地开发：`cloudflared` 或 `ngrok`
- 长期运行：云服务器 + `systemd` / Docker

## 3. 在飞书里先把表搭好

先新建一个多维表格，然后创建这些字段。

### 输入字段

- `论文标题/备注`
- `PDF附件`
- `arXiv链接`

### 输出字段

- `0_摘要翻译`
- `1_方法动机`
- `2_方法设计`
- `3_与其他方法对比`
- `4_实验表现与优势`
- `5_学习与应用`
- `6_总结`
- `7_关键词领域`

### 系统字段

- `分析状态`
- `错误信息`
- `来源类型`
- `来源哈希`
- `论文ID`
- `最后分析时间`

建议：

- 输出字段全部用“多行文本”
- 系统字段也用文本即可

## 4. 创建飞书开放平台应用

你需要一个飞书应用，让后端能读取和更新多维表格。

在飞书开放平台里：

1. 创建企业自建应用。
2. 记录这两个值：
   - `App ID`
   - `App Secret`
3. 给应用开通多维表格相关权限。
4. 把这个应用安装到你的飞书空间。
5. 确保这个应用对目标多维表格有访问权限。

你后面会把 `App ID` 和 `App Secret` 写到 `.env` 里。

## 5. 拿到表格 ID

你还需要两个 ID：

- `base_token`
- `table_id`

通常从多维表格 URL 或开放平台调试里可以拿到。

你最终需要把它们填到环境变量：

- `FEISHU_BASE_TOKEN`
- `FEISHU_TABLE_ID`

## 6. 准备 OpenAI 兼容模型

你需要 3 个值：

- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

例如：

```env
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-xxxx
OPENAI_MODEL=gpt-4.1-mini
```

如果你用的是兼容 OpenAI 的别家服务，也可以直接替换 `BASE_URL` 和 `MODEL`。

## 7. 在本地启动项目

进入项目目录后执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

然后编辑 `.env`。

最少要改这些：

```env
FEISHU_APP_ID=你的_app_id
FEISHU_APP_SECRET=你的_app_secret
FEISHU_BASE_TOKEN=你的_base_token
FEISHU_TABLE_ID=你的_table_id
WEBHOOK_SHARED_SECRET=你自己定义的一个随机字符串

OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=你的_api_key
OPENAI_MODEL=gpt-4.1-mini
```

## 8. 启动两个进程

这个项目不是只启动一个命令就完了。

你需要同时启动：

### 终端 1：API 服务

```bash
uvicorn paper_analyzer.main:app --host 0.0.0.0 --port 8000
```

### 终端 2：Worker

```bash
python -m paper_analyzer.services.worker
```

如果这两个都没报错，说明后端基本启动成功了。

你可以先测试：

```bash
curl http://127.0.0.1:8000/healthz
```

看到下面结果就对了：

```json
{"status":"ok"}
```

## 9. 把本地服务暴露给飞书

如果你是本地开发，需要把 `8000` 端口暴露到公网。

例如用 `cloudflared`：

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

它会给你一个公网地址，例如：

```text
https://xxxx.trycloudflare.com
```

后面飞书自动化里要填的 webhook 地址就是：

```text
https://xxxx.trycloudflare.com/webhooks/feishu/bitable-record
```

## 10. 在飞书里配置自动化

回到你的多维表格，新增一条自动化。

### 触发条件

- 记录新增或修改
- 只监控这两个字段：
  - `PDF附件`
  - `arXiv链接`

### 执行动作

- 发送 HTTP 请求

### 请求地址

```text
POST https://你的域名/webhooks/feishu/bitable-record
```

### 请求体

把下面这个 JSON 作为模板：

```json
{
  "base_token": "你的_base_token",
  "table_id": "你的_table_id",
  "record_id": "{{record_id}}",
  "changed_fields": ["arXiv链接"],
  "secret": "你在.env里设置的WEBHOOK_SHARED_SECRET"
}
```

注意：

- `secret` 必须和 `.env` 里的 `WEBHOOK_SHARED_SECRET` 一致
- `record_id` 要用飞书自动化变量
- `changed_fields` 如果飞书不方便动态传，也可以先写固定值，服务端仍会重新读取整条记录

## 11. 第一次验证

现在做一次最小测试。

### 方法 A：贴 arXiv 链接

在 `arXiv链接` 里填一个链接，例如：

```text
https://arxiv.org/abs/2401.01234
```

### 方法 B：上传 PDF

直接在 `PDF附件` 里上传一篇论文 PDF。

然后观察系统列：

- `分析状态` 先变成 `排队中`
- 然后变成 `分析中`
- 最后变成 `已完成`

成功后，8 个输出字段会一次性回填。

## 12. 如果失败，先看哪里

最常见的问题只有这几类。

### 1. 飞书调不到你的服务

现象：

- 自动化执行失败
- 飞书提示请求超时或无法连接

排查：

- 你的公网 URL 是否可访问
- API 服务是否真的在运行
- 路由是否写成 `/webhooks/feishu/bitable-record`

### 2. `secret` 不对

现象：

- webhook 返回 401

排查：

- 飞书自动化里的 `secret`
- `.env` 里的 `WEBHOOK_SHARED_SECRET`

这两个必须完全一致。

### 3. 飞书应用权限不够

现象：

- 能触发，但后端读取/写回表格失败

排查：

- 应用是否安装到当前飞书空间
- 是否有多维表格读写权限
- 是否对目标表有访问权限

### 4. PDF 解析失败

现象：

- `错误信息` 里提示文本过少或不支持 OCR

原因：

- 你上传的是扫描版 PDF

v1 不支持 OCR，所以只支持“能直接复制文本”的学术 PDF。

### 5. 模型调用失败

现象：

- 任务进入失败状态
- `错误信息` 里提到模型超时、401、429 或 5xx

排查：

- `OPENAI_API_KEY` 是否正确
- `OPENAI_BASE_URL` 是否正确
- `OPENAI_MODEL` 是否存在
- 额度是否足够

## 13. 你真正需要改的文件只有哪些

第一次上手时，你只需要关心这些文件：

- `.env`
- `README.md`
- `QUICKSTART.md`

如果你只是“想把系统跑起来”，源码可以先不看。

## 14. 如果你要继续部署到线上

建议下一步做这三件事：

1. 把服务部署到一台固定服务器，不要长期依赖本地穿透。
2. 用进程管理工具托管 API 和 Worker。
3. 把日志、异常告警、数据库备份补上。

## 15. 最短上手路径

如果你只想最快验证一次，按这个最短路径做：

1. 建飞书表，建好所有字段。
2. 创建飞书应用，拿到 `App ID` 和 `App Secret`。
3. 拿到 `base_token` 和 `table_id`。
4. 填 `.env`。
5. 启动 API。
6. 启动 Worker。
7. 用 `cloudflared` 暴露 `8000` 端口。
8. 配飞书自动化 webhook。
9. 往表里贴一个 arXiv 链接。
10. 看 `分析状态` 是否变成 `已完成`。

做到这一步，整套链路就打通了。

