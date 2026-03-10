import os
import uuid
import base64
import asyncio
from pathlib import Path
from typing import Optional, Any, Literal
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, HTTPException, APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

load_dotenv()

DIFY_API_BASE_URL = os.getenv("DIFY_API_BASE_URL", "http://localhost/v1")


@dataclass
class AgentConfig:
    """Agent 配置"""
    name: str
    api_key: str
    input_key: str
    description: str
    app_type: Literal["workflow", "chat"] = "workflow"


AGENTS = {
    "painpoint": AgentConfig(
        name="痛点分析助手",
        api_key=os.getenv("AGENT_PAINPOINT_API_KEY", ""),
        input_key=os.getenv("AGENT_PAINPOINT_INPUT_KEY", "painpoint"),
        description="分析用户痛点，返回解决方案",
        app_type=os.getenv("AGENT_PAINPOINT_TYPE", "workflow"),
    ),
    "investment": AgentConfig(
        name="智能投研助手",
        api_key=os.getenv("AGENT_INVESTMENT_API_KEY", ""),
        input_key=os.getenv("AGENT_INVESTMENT_INPUT_KEY", "company"),
        description="智能投研分析，提供投资建议",
        app_type=os.getenv("AGENT_INVESTMENT_TYPE", "chat"),
    ),
}


class BaseRequest(BaseModel):
    """基础请求模型"""
    query: str
    user_id: Optional[str] = "default_user"
    conversation_id: Optional[str] = None


class PainPointRequest(BaseRequest):
    """痛点分析请求"""
    pass


class InvestmentRequest(BaseRequest):
    """投研分析请求"""
    pass


class AgentResponse(BaseModel):
    """统一响应模型"""
    status: str
    outputs: Optional[dict[str, Any]] = None
    answer: Optional[str] = None
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    task_id: Optional[str] = None
    elapsed_time: Optional[float] = None
    total_tokens: Optional[int] = None


http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=120.0)
    yield
    await http_client.aclose()


app = FastAPI(
    title="Dify 多 Agent 中转服务",
    description="统一中转服务，支持多个 Dify Agent（Workflow 和 Chat 类型）",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def call_dify_agent(
    agent_id: str,
    input_value: str,
    user_id: str,
    conversation_id: Optional[str] = None,
    stream: bool = False,
) -> dict | StreamingResponse:
    """
    通用 Dify Agent 调用函数，支持 Workflow 和 Chat 类型
    """
    import json as json_lib
    
    agent = AGENTS.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 不存在")
    
    if not agent.api_key or agent.api_key.startswith("your_"):
        raise HTTPException(
            status_code=500,
            detail=f"Agent '{agent.name}' 的 API Key 未配置"
        )
    
    headers = {
        "Authorization": f"Bearer {agent.api_key}",
        "Content-Type": "application/json",
    }
    
    is_agent_chat = agent.app_type == "chat"
    
    if agent.app_type == "workflow":
        endpoint = f"{DIFY_API_BASE_URL}/workflows/run"
        payload = {
            "inputs": {
                agent.input_key: input_value,
            },
            "response_mode": "streaming" if stream else "blocking",
            "user": user_id,
        }
    else:
        endpoint = f"{DIFY_API_BASE_URL}/chat-messages"
        payload = {
            "inputs": {
                agent.input_key: input_value,
            },
            "query": input_value,
            "response_mode": "streaming",
            "user": user_id,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
    
    if stream or is_agent_chat:
        if stream:
            async def event_generator():
                try:
                    async with http_client.stream(
                        "POST",
                        endpoint,
                        headers=headers,
                        json=payload,
                    ) as response:
                        async for line in response.aiter_lines():
                            if line:
                                yield f"{line}\n\n"
                except Exception as e:
                    yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
            
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
            )
        else:
            try:
                full_answer = ""
                conversation_id_result = ""
                message_id_result = ""
                
                async with http_client.stream(
                    "POST",
                    endpoint,
                    headers=headers,
                    json=payload,
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json_lib.loads(line[6:])
                                event = data.get("event", "")
                                
                                if event == "agent_message" or event == "message":
                                    full_answer += data.get("answer", "")
                                    if not conversation_id_result:
                                        conversation_id_result = data.get("conversation_id", "")
                                    if not message_id_result:
                                        message_id_result = data.get("message_id", "")
                                elif event == "message_end":
                                    if not conversation_id_result:
                                        conversation_id_result = data.get("conversation_id", "")
                                    if not message_id_result:
                                        message_id_result = data.get("message_id", "")
                            except json_lib.JSONDecodeError:
                                pass
                
                return {
                    "status": "succeeded",
                    "answer": full_answer,
                    "outputs": {"answer": full_answer},
                    "conversation_id": conversation_id_result,
                    "message_id": message_id_result,
                }
                
            except httpx.TimeoutException:
                raise HTTPException(status_code=504, detail="Dify API 请求超时")
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Dify API 错误: {e.response.text}"
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")
    
    try:
        response = await http_client.post(
            endpoint,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        
        if agent.app_type == "workflow":
            workflow_data = data.get("data", {})
            return {
                "status": workflow_data.get("status", "succeeded"),
                "outputs": workflow_data.get("outputs"),
                "workflow_run_id": data.get("workflow_run_id", ""),
                "task_id": data.get("task_id", ""),
                "elapsed_time": workflow_data.get("elapsed_time"),
                "total_tokens": workflow_data.get("total_tokens"),
            }
        else:
            return {
                "status": "succeeded",
                "answer": data.get("answer", ""),
                "outputs": {"answer": data.get("answer", "")},
                "conversation_id": data.get("conversation_id", ""),
                "message_id": data.get("message_id", ""),
            }
        
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Dify API 请求超时")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Dify API 错误: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


# ==========================================
# 通用接口
# ==========================================

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "service": "dify-multi-agent-proxy"}


@app.get("/agents")
async def list_agents():
    """列出所有可用的 Agent"""
    return {
        agent_id: {
            "name": agent.name,
            "description": agent.description,
            "type": agent.app_type,
            "configured": bool(agent.api_key and not agent.api_key.startswith("your_")),
        }
        for agent_id, agent in AGENTS.items()
    }


# ==========================================
# Agent 1: 痛点分析助手 (Workflow)
# ==========================================

painpoint_router = APIRouter(prefix="/api/painpoint", tags=["痛点分析助手"])


@painpoint_router.post("", response_model=AgentResponse)
async def analyze_pain_point(request: PainPointRequest):
    """分析用户痛点，返回结构化解决方案"""
    result = await call_dify_agent(
        agent_id="painpoint",
        input_value=request.query,
        user_id=request.user_id,
        stream=False,
    )
    return result


@painpoint_router.post("/stream")
async def analyze_pain_point_stream(request: PainPointRequest):
    """流式分析用户痛点"""
    return await call_dify_agent(
        agent_id="painpoint",
        input_value=request.query,
        user_id=request.user_id,
        stream=True,
    )


app.include_router(painpoint_router)


# ==========================================
# Agent 2: 智能投研助手 (Chat)
# ==========================================

investment_router = APIRouter(prefix="/api/investment", tags=["智能投研助手"])


@investment_router.post("", response_model=AgentResponse)
async def analyze_investment(request: InvestmentRequest):
    """智能投研分析"""
    result = await call_dify_agent(
        agent_id="investment",
        input_value=request.query,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        stream=False,
    )
    return result


@investment_router.post("/stream")
async def analyze_investment_stream(request: InvestmentRequest):
    """流式投研分析"""
    return await call_dify_agent(
        agent_id="investment",
        input_value=request.query,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
        stream=True,
    )


app.include_router(investment_router)


# ==========================================
# AI 创意生成器 (生图 / 生视频) — APIMart
# ==========================================

APIMART_BASE = "https://api.apimart.ai/v1"
GENERATE_API_KEY = os.getenv("GENERATE_API_KEY", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

MODEL_NAME_MAP = {
    "seedream-5.0-lite": "doubao-seedream-5-0-lite",
    "seedream-4.5":      "doubao-seedance-4-5",
    "seedream-4":        "doubao-seedance-4-0",
    "nano-banana-pro":   "gemini-3-pro-image-preview",
    "nano-banana":       "gemini-2.5-flash-image-preview",
    "nano-banana-2":     "gemini-3.1-flash-image-preview",
    "4o-image":          "gpt-4o-image",
    "flux-kontext":      "flux-kontext-pro",
    "flux-2":            "flux-2",
    "sora-2":            "sora-2",
    "sora-2-pro":        "sora-2-pro",
    "veo-3.1":           "veo-3",
    "wan-2.6":           "wan-2.6",
    "seedance-1.0-pro":  "doubao-seedance-1-0-pro",
    "seedance-1.5-pro":  "doubao-seedance-1-5-pro",
    "hailuo-02":         "minimax-hailuo-02",
    "hailuo-2.3":        "minimax-hailuo-2.3",
    "kling-v2.6":        "kling-v2.6",
    "vidu-q3-pro":       "vidu-q3-pro",
}

AVATAR_MODELS = {
    "seedream-5.0-lite", "seedream-4.5", "seedream-4",
    "nano-banana-pro", "nano-banana", "nano-banana-2",
    "4o-image", "flux-kontext", "flux-2",
}
VIDEO_MODELS = {
    "sora-2", "sora-2-pro", "veo-3.1", "wan-2.6",
    "seedance-1.0-pro", "seedance-1.5-pro",
    "hailuo-02", "hailuo-2.3", "kling-v2.6", "vidu-q3-pro",
}



def _apimart_headers():
    return {
        "Authorization": f"Bearer {GENERATE_API_KEY}",
        "Content-Type": "application/json",
    }


@app.get("/uploads/{filename}")
async def serve_upload(filename: str):
    """Serve uploaded images so APIMart can fetch them."""
    fpath = UPLOADS_DIR / filename
    if not fpath.exists():
        raise HTTPException(status_code=404)
    return FileResponse(fpath)


@app.post("/api/generate")
async def generate_creative(
    image: UploadFile = File(...),
    prompt: str = Form(""),
    model: str = Form("seedream-5.0-lite"),
    mode: str = Form("avatar"),
):
    """
    Submit a generation task to APIMart. Returns a task_id for polling.
    """
    if not GENERATE_API_KEY:
        raise HTTPException(status_code=500, detail="GENERATE_API_KEY 未配置，请在 .env 中填写")

    all_models = AVATAR_MODELS | VIDEO_MODELS
    if model not in all_models:
        raise HTTPException(status_code=400, detail=f"不支持的模型: {model}")

    api_model = MODEL_NAME_MAP.get(model, model)
    image_bytes = await image.read()

    b64 = base64.b64encode(image_bytes).decode()
    image_ref = f"data:image/jpeg;base64,{b64}"

    if mode == "avatar":
        payload = {
            "model": api_model,
            "prompt": prompt or "3D cartoon style character",
            "size": "1:1",
            "n": 1,
            "image_urls": [image_ref],
        }
        endpoint = f"{APIMART_BASE}/images/generations"
    else:
        payload = {
            "model": api_model,
            "prompt": prompt or "Animated video from photo",
            "duration": 5,
            "aspect_ratio": "16:9",
            "image_urls": [image_ref],
        }
        endpoint = f"{APIMART_BASE}/videos/generations"

    resp = await http_client.post(endpoint, headers=_apimart_headers(), json=payload)
    data = resp.json()

    if resp.status_code != 200 or "error" in data:
        err = data.get("error", {})
        raise HTTPException(
            status_code=resp.status_code or 500,
            detail=err.get("message", f"APIMart 请求失败: {data}"),
        )

    task_id = data.get("data", [{}])[0].get("task_id")
    if not task_id:
        raise HTTPException(status_code=500, detail=f"未获取到 task_id: {data}")

    return {"task_id": task_id, "model": model, "mode": mode}


@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str):
    """
    Poll APIMart task status. Returns status + result when completed.
    """
    if not GENERATE_API_KEY:
        raise HTTPException(status_code=500, detail="GENERATE_API_KEY 未配置")

    resp = await http_client.get(
        f"{APIMART_BASE}/tasks/{task_id}",
        headers=_apimart_headers(),
        params={"language": "zh"},
    )
    data = resp.json()

    if resp.status_code != 200 or "error" in data:
        err = data.get("error", {})
        raise HTTPException(
            status_code=resp.status_code or 500,
            detail=err.get("message", f"查询失败: {data}"),
        )

    task = data.get("data", {})
    result = {
        "status": task.get("status", "pending"),
        "progress": task.get("progress", 0),
    }

    if task.get("status") == "completed":
        task_result = task.get("result", {})
        images = task_result.get("images", [])
        videos = task_result.get("videos", [])
        if images:
            urls = images[0].get("url", [])
            result["image_url"] = urls[0] if urls else None
        if videos:
            urls = videos[0].get("url", [])
            result["video_url"] = urls[0] if urls else None
            result["thumbnail_url"] = task_result.get("thumbnail_url")
        result["actual_time"] = task.get("actual_time")

    if task.get("status") == "failed":
        err = task.get("error", {})
        result["error"] = err.get("message", "生成失败")

    return result


# ==========================================
# 前端静态文件服务
# ==========================================

@app.get("/")
async def serve_frontend():
    """服务前端首页"""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/painpoint.html")
async def serve_painpoint():
    """服务痛点分析页面"""
    return FileResponse(FRONTEND_DIR / "painpoint.html")


@app.get("/investment.html")
async def serve_investment():
    """服务投研分析页面"""
    return FileResponse(FRONTEND_DIR / "investment.html")


@app.get("/knowledge-base.html")
async def serve_knowledge_base():
    """服务企业知识库自服务页面"""
    return FileResponse(FRONTEND_DIR / "knowledge-base.html")


@app.get("/copywriting.html")
async def serve_copywriting():
    """服务多语言文案助手页面"""
    return FileResponse(FRONTEND_DIR / "copywriting.html")


@app.get("/video-generator.html")
async def serve_video_generator():
    """服务视频生成器页面"""
    return FileResponse(FRONTEND_DIR / "video-generator.html")


@app.get("/customer-service.html")
async def serve_customer_service():
    """服务智能客服助手页面"""
    return FileResponse(FRONTEND_DIR / "customer-service.html")


@app.get("/index.html")
async def serve_index():
    """服务首页"""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/logo.png")
async def serve_logo():
    """服务 Logo"""
    logo_path = FRONTEND_DIR / "logo.png"
    if not logo_path.exists():
        logo_path = BASE_DIR / "logo.png"
    return FileResponse(logo_path)


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ==========================================
# 启动入口
# ==========================================

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    print(f"\n[*] YUNI AI Agent Platform Starting...")
    print(f"[API] http://{host}:{port}/docs")
    print(f"[Web] http://{host}:{port}/")
    print(f"")
    
    uvicorn.run("main:app", host=host, port=port, reload=True)
