import asyncio
import logging
import threading
from flask import Blueprint, jsonify, request

from esp32_server.auth import require_api_key
from esp32_server.utils import (
    convert_task_to_esp32_format,
    convert_tasks_to_esp32_format,
    get_stats_from_tasks
)
from microsoft_todo_client import MicrosoftTodoDirectClient

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)


def run_async(coro):
    """在同步上下文中运行异步协程"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def run_async_with_client(client, coro):
    """运行异步协程并自动关闭客户端 session"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        if client and client.session and not client.session.closed:
            loop.run_until_complete(client.close())
        loop.close()


def get_todo_client():
    """获取新的 TODO 客户端实例（token 在全局缓存中共享）"""
    return MicrosoftTodoDirectClient()


@api_bp.route('/')
def index():
    """首页 - API 文档"""
    return jsonify({
        "message": "ESP32 TODO API Server",
        "version": "1.0",
        "endpoints": {
            "GET /api/todos": "获取所有 TODO 项",
            "GET /api/todos/<id>": "获取指定 TODO 项",
            "POST /api/todos": "创建新 TODO 项",
            "PUT /api/todos/<id>": "更新 TODO 项",
            "DELETE /api/todos/<id>": "删除 TODO 项",
            "POST /api/todos/<id>/complete": "标记 TODO 为完成",
            "POST /api/todos/<id>/uncomplete": "标记 TODO 为未完成",
            "GET /api/stats": "获取统计信息"
        }
    })


@api_bp.route('/api/todos', methods=['GET'])
@require_api_key
def get_todos():
    """获取 TODO 项"""
    try:
        client = get_todo_client()
        status = request.args.get('status')
        limit = request.args.get('limit', type=int, default=10)
        
        async def fetch_todos():
            lists_result = await client.get_task_lists()
            if "value" not in lists_result or not lists_result["value"]:
                return [], None
            
            list_id = None
            for task_list in lists_result["value"]:
                if task_list.get("wellknownListName") == "defaultList":
                    list_id = task_list["id"]
                    break
            if not list_id:
                list_id = lists_result["value"][0]["id"]
            
            if status == 'active' or status == 'notStarted':
                filter_query = "status ne 'completed'"
            elif status == 'completed':
                filter_query = "status eq 'completed'"
            else:
                filter_query = None
            
            endpoint = f"/me/todo/lists/{list_id}/tasks?$top={limit}"
            if filter_query:
                endpoint += f"&$filter={filter_query}"
            
            tasks_result = await client._make_request("GET", endpoint)
            
            if "value" in tasks_result:
                tasks = tasks_result["value"]
                for task in tasks:
                    task["listId"] = list_id
                return tasks, list_id
            return [], list_id
        
        tasks, list_id = run_async_with_client(client, fetch_todos())
        esp32_tasks = convert_tasks_to_esp32_format(tasks)
        
        return jsonify({"value": esp32_tasks, "count": len(esp32_tasks), "listId": list_id})
        
    except Exception as e:
        logger.error(f"获取任务失败: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/api/todos/<path:todo_id>', methods=['GET'])
@require_api_key
def get_todo(todo_id):
    """获取指定 TODO 项"""
    try:
        client = get_todo_client()
        
        async def fetch_todo():
            tasks = await client.list_todos()
            for task in tasks:
                if task.get('id') == todo_id:
                    return task
            return None
        
        task = run_async_with_client(client, fetch_todo())
        
        if task:
            return jsonify(convert_task_to_esp32_format(task))
        return jsonify({"error": "TODO not found"}), 404
        
    except Exception as e:
        logger.error(f"获取任务失败: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/api/todos', methods=['POST'])
@require_api_key
def create_todo():
    """创建新 TODO 项"""
    try:
        data = request.json
        client = get_todo_client()
        
        async def create():
            result = await client.create_todo(
                title=data.get('title', ''),
                description=data.get('body', ''),
                due_date=data.get('dueDate'),
                reminder_date=data.get('reminderDate'),
                reminder_time=data.get('reminderTime')
            )
            return result
        
        result = run_async_with_client(client, create())
        
        if "error" in result:
            return jsonify(result), 400
        
        return jsonify(convert_task_to_esp32_format(result)), 201
        
    except Exception as e:
        logger.error(f"创建任务失败: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/api/todos/<path:todo_id>', methods=['PUT'])
@require_api_key
def update_todo(todo_id):
    """更新 TODO 项"""
    try:
        data = request.json
        client = get_todo_client()
        
        async def update():
            result = await client.update_todo(
                todo_id=todo_id,
                title=data.get('title'),
                description=data.get('body'),
                due_date=data.get('dueDate'),
                reminder_date=data.get('reminderDate'),
                reminder_time=data.get('reminderTime')
            )
            return result
        
        result = run_async_with_client(client, update())
        
        if "error" in result:
            return jsonify(result), 404 if "找不到" in result.get("error", "") else 400
        
        return jsonify(convert_task_to_esp32_format(result))
        
    except Exception as e:
        logger.error(f"更新任务失败: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/api/todos/<path:todo_id>', methods=['DELETE'])
@require_api_key
def delete_todo(todo_id):
    """删除 TODO 项"""
    try:
        client = get_todo_client()
        
        async def delete():
            result = await client.delete_todo(todo_id)
            return result
        
        result = run_async_with_client(client, delete())
        
        if "error" in result:
            return jsonify(result), 404
        
        return jsonify({"message": "TODO deleted", "id": todo_id})
        
    except Exception as e:
        logger.error(f"删除任务失败: {e}")
        return jsonify({"error": str(e)}), 500


@api_bp.route('/api/todos/<path:todo_id>/complete', methods=['POST'])
@require_api_key
def complete_todo(todo_id):
    """标记 TODO 为完成 - 异步模式"""
    data = request.json or {}
    list_id = data.get('listId') or request.args.get('listId')
    
    logger.info(f"收到完成任务请求, todo_id: {todo_id}, list_id: {list_id}")
    
    def background_complete():
        try:
            client = get_todo_client()
            
            async def do_complete():
                nonlocal list_id
                if not list_id:
                    lists_result = await client.get_task_lists()
                    if "value" in lists_result and lists_result["value"]:
                        for task_list in lists_result["value"]:
                            if task_list.get("wellknownListName") == "defaultList":
                                list_id = task_list["id"]
                                break
                        if not list_id:
                            list_id = lists_result["value"][0]["id"]
                
                if list_id:
                    result = await client.update_task(list_id, todo_id, status="completed")
                    logger.info(f"后台完成任务成功: {result.get('id', todo_id)}")
                else:
                    logger.error("后台完成任务失败: 找不到列表ID")
            
            run_async_with_client(client, do_complete())
        except Exception as e:
            logger.error(f"后台完成任务异常: {e}")
    
    thread = threading.Thread(target=background_complete, daemon=True)
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "任务完成请求已接收",
        "id": todo_id,
        "listId": list_id or ""
    })


@api_bp.route('/api/todos/<path:todo_id>/uncomplete', methods=['POST'])
@require_api_key
def uncomplete_todo(todo_id):
    """标记 TODO 为未完成 - 异步模式"""
    data = request.json or {}
    list_id = data.get('listId') or request.args.get('listId')
    
    logger.info(f"收到取消完成任务请求, todo_id: {todo_id}, list_id: {list_id}")
    
    def background_uncomplete():
        try:
            client = get_todo_client()
            
            async def do_uncomplete():
                nonlocal list_id
                if not list_id:
                    lists_result = await client.get_task_lists()
                    if "value" in lists_result and lists_result["value"]:
                        for task_list in lists_result["value"]:
                            if task_list.get("wellknownListName") == "defaultList":
                                list_id = task_list["id"]
                                break
                        if not list_id:
                            list_id = lists_result["value"][0]["id"]
                
                if list_id:
                    result = await client.update_task(list_id, todo_id, status="notStarted")
                    logger.info(f"后台取消完成任务成功: {result.get('id', todo_id)}")
                else:
                    logger.error("后台取消完成任务失败: 找不到列表ID")
            
            run_async_with_client(client, do_uncomplete())
        except Exception as e:
            logger.error(f"后台取消完成任务异常: {e}")
    
    thread = threading.Thread(target=background_uncomplete, daemon=True)
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "取消完成请求已接收",
        "id": todo_id,
        "listId": list_id or ""
    })


@api_bp.route('/api/stats', methods=['GET'])
@require_api_key
def get_stats():
    """获取统计信息"""
    try:
        client = get_todo_client()
        
        async def fetch_stats():
            tasks = await client.list_todos()
            return tasks
        
        tasks = run_async_with_client(client, fetch_stats())
        stats = get_stats_from_tasks(tasks)
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return jsonify({"error": str(e)}), 500
