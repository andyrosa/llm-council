"""OpenRouter API client for making LLM requests."""

import httpx
import time
import asyncio
from typing import List, Dict, Any, Optional
from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL


async def get_generation_cost(generation_id: str, timeout: float = 10.0) -> Optional[float]:
    """
    Query OpenRouter for the cost of a generation.
    
    Args:
        generation_id: The generation ID from the response
        timeout: Request timeout in seconds
        
    Returns:
        Cost in dollars, or None if unavailable
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    }
    
    # Wait a moment for stats to be available
    await asyncio.sleep(0.5)
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"https://openrouter.ai/api/v1/generation?id={generation_id}",
                headers=headers
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('data', {}).get('total_cost')
    except Exception as e:
        print(f"Error fetching generation cost: {e}")
    return None


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    web_search: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds
        web_search: Whether to enable web search (uses native engine)

    Returns:
        Response dict with 'content', 'elapsed_time', 'cost', and optional 'reasoning_details', or None if failed
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
    }

    if web_search:
        payload["plugins"] = [{"id": "web", "engine": "native"}]

    try:
        start_time = time.time()
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            elapsed_time = time.time() - start_time

            data = response.json()
            message = data['choices'][0]['message']
            usage = data.get('usage', {})
            generation_id = data.get('id')

            # Fetch cost asynchronously
            cost = None
            if generation_id:
                cost = await get_generation_cost(generation_id)
                if cost is not None:
                    cost = round(cost, 2)

            return {
                'content': message.get('content'),
                'reasoning_details': message.get('reasoning_details'),
                'elapsed_time': round(elapsed_time, 2),
                'usage': usage,
                'cost': cost,
            }

    except httpx.HTTPStatusError as e:
        print(f"Error querying model {model}: HTTP {e.response.status_code} - {e.response.text}")
        return None
    except httpx.TimeoutException as e:
        print(f"Error querying model {model}: Request timed out after {timeout}s")
        return None
    except Exception as e:
        print(f"Error querying model {model}: {type(e).__name__}: {str(e)}")
        return None


async def query_models_streaming(
    models: List[str],
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    web_search: bool = False,
    web_search_models: set = None
):
    """
    Query multiple models in parallel, yielding results as each model completes.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model
        timeout: Request timeout in seconds
        web_search: Whether to enable web search (global flag)
        web_search_models: Set of model IDs that support web search. If provided and web_search is True,
                          only these models will have web_search enabled.

    Yields:
        Tuple of (model, response_dict or None, completed_count, total_count)
    """
    import asyncio

    # Create named tasks for all models - store model name with each task
    tasks = {}
    for model in models:
        # Enable web search only if global flag is on AND model supports it (or no filter provided)
        model_web_search = web_search and (web_search_models is None or model in web_search_models)
        task = asyncio.create_task(query_model(model, messages, timeout=timeout, web_search=model_web_search))
        tasks[task] = model
    
    total_count = len(models)
    completed_count = 0
    pending = set(tasks.keys())
    
    # Use as_completed to yield results as they finish
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            model = tasks[task]
            completed_count += 1
            try:
                result = task.result()
                yield (model, result, completed_count, total_count)
            except Exception as e:
                print(f"Task for {model} raised exception: {e}")
                yield (model, None, completed_count, total_count)


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    web_search: bool = False,
    web_search_models: set = None
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model
        timeout: Request timeout in seconds
        web_search: Whether to enable web search (global flag)
        web_search_models: Set of model IDs that support web search. If provided and web_search is True,
                          only these models will have web_search enabled.

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    import asyncio

    # Create tasks for all models with per-model web search setting
    tasks = []
    for model in models:
        model_web_search = web_search and (web_search_models is None or model in web_search_models)
        tasks.append(query_model(model, messages, timeout=timeout, web_search=model_web_search))

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return {model: response for model, response in zip(models, responses)}
