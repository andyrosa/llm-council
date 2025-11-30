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
    timeout: float = 120.0
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds

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

    except Exception as e:
        print(f"Error querying model {model}: {e}")
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    import asyncio

    # Create tasks for all models
    tasks = [query_model(model, messages) for model in models]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return {model: response for model, response in zip(models, responses)}
