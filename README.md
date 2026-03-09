# Dify 多 Agent 中转服务

统一中转服务，支持多个 Dify Workflow Agent。

## 架构

```
                    ┌─────────────────────────────────────┐
                    │       中转服务 (FastAPI)             │
                    │                                     │
   请求 ──────────► │  /api/painpoint   → Agent 1        │──► Dify (Token A)
                    │                    (痛点分析)        │
                    │                                     │
                    │  /api/investment  → Agent 2        │──► Dify (Token B)
                    │                    (投研助手)        │
                    └─────────────────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

编辑 `.env` 文件，配置各 Agent 的 API Key：

```env
# Dify API 地址
DIFY_API_BASE_URL=http://localhost/v1

# Agent 1: 痛点分析助手
AGENT_PAINPOINT_API_KEY=app-xxxxxxxxxx
AGENT_PAINPOINT_INPUT_KEY=painpoint

# Agent 2: 智能投研助手
AGENT_INVESTMENT_API_KEY=app-yyyyyyyyyy
AGENT_INVESTMENT_INPUT_KEY=query
```

### 3. 启动服务

```bash
python main.py
```

## API 接口

### 通用接口

| 接口 | 方法 | 说明 |
|-----|------|-----|
| `/health` | GET | 健康检查 |
| `/agents` | GET | 列出所有 Agent 及配置状态 |

### Agent 1: 痛点分析助手

| 接口 | 方法 | 说明 |
|-----|------|-----|
| `/api/painpoint` | POST | 同步分析痛点 |
| `/api/painpoint/stream` | POST | 流式分析痛点 |

**请求示例：**

```bash
curl -X POST http://localhost:8000/api/painpoint \
  -H "Content-Type: application/json" \
  -d '{"query": "用户经常忘记密码"}'
```

### Agent 2: 智能投研助手

| 接口 | 方法 | 说明 |
|-----|------|-----|
| `/api/investment` | POST | 同步投研分析 |
| `/api/investment/stream` | POST | 流式投研分析 |

**请求示例：**

```bash
curl -X POST http://localhost:8000/api/investment \
  -H "Content-Type: application/json" \
  -d '{"query": "分析腾讯2024年财报"}'
```

### 响应格式

```json
{
    "workflow_run_id": "xxx",
    "task_id": "xxx",
    "status": "succeeded",
    "outputs": {
        "output_field": "结构化返回数据"
    },
    "elapsed_time": 2.5,
    "total_tokens": 150
}
```

## 添加新 Agent

### 1. 在 `.env` 中添加配置

```env
# Agent 3: 新助手
AGENT_NEW_API_KEY=app-zzzzzzzzzz
AGENT_NEW_INPUT_KEY=input_field_name
```

### 2. 在 `main.py` 中注册 Agent

```python
# 在 AGENTS 字典中添加
AGENTS = {
    # ... 现有 Agent
    "new": AgentConfig(
        name="新助手",
        api_key=os.getenv("AGENT_NEW_API_KEY", ""),
        input_key=os.getenv("AGENT_NEW_INPUT_KEY", "input"),
        description="新助手描述",
    ),
}
```

### 3. 添加路由

```python
new_router = APIRouter(prefix="/api/new", tags=["新助手"])

@new_router.post("", response_model=WorkflowResponse)
async def handle_new(request: BaseRequest):
    return await call_dify_workflow(
        agent_id="new",
        input_value=request.query,
        user_id=request.user_id,
    )

app.include_router(new_router)
```

## API 文档

启动服务后访问：

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 项目结构

```
dify_test/
├── main.py           # FastAPI 主应用（多 Agent 支持）
├── requirements.txt  # Python 依赖
├── .env             # 环境变量配置
├── .env.example     # 环境变量示例
├── .gitignore       # Git 忽略文件
└── README.md        # 说明文档
```
