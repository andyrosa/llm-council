"""3-stage LLM Council orchestration."""

import json
import os
import asyncio
import math
from typing import List, Dict, Any, Tuple, AsyncGenerator
from .openrouter import query_models_parallel, query_model, query_models_streaming
from .config import get_council_models_active, get_active_chairman_model, get_browse_capable_models, get_coding_capable_models

CHAIRMAN_INSTRUCTIONS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "chairman_instructions.json")


def load_chairman_prompt_override() -> str:
    """Load chairman prompt override from JSON file. Returns empty string if not present."""
    if not os.path.exists(CHAIRMAN_INSTRUCTIONS_PATH):
        return ""
    with open(CHAIRMAN_INSTRUCTIONS_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data.get("prompt", "")


async def stage1_collect_responses(user_query: str, web_search: bool = False, coding_mode: bool = False) -> List[Dict[str, Any]]:
    """
    Stage 1: Collect individual responses from all council models.

    Args:
        user_query: The user's question
        web_search: Whether to enable web search
        coding_mode: Whether coding mode is enabled

    Returns:
        List of dicts with 'model', 'response', 'elapsed_time', 'usage', and 'cost' keys
    """
    messages = [{"role": "user", "content": user_query}]
    models = get_council_models_active()
    browse_capable = get_browse_capable_models() if web_search else None
    coding_capable = get_coding_capable_models()
    
    # Filter out coding models unless coding_mode is set,
    # or web_search is set and the model can browse
    if not coding_mode:
        models = [
            m for m in models
            if m not in coding_capable or (web_search and browse_capable and m in browse_capable)
        ]

    # Query all models in parallel
    responses = await query_models_parallel(models, messages, web_search=web_search, web_search_models=browse_capable)

    # Calculate max duration from successful responses to set retry timeout
    successful_durations = [
        r['elapsed_time'] for r in responses.values() 
        if r is not None and r.get('elapsed_time') is not None
    ]
    # Default to 120s if no models succeeded, otherwise use max duration
    retry_timeout = max(successful_durations) if successful_durations else 120.0
    # Ensure a minimum reasonable timeout (e.g. 10s) even if models were super fast
    retry_timeout = max(retry_timeout, 10.0)

    # Retry once for models that did not respond
    failed_models = [model for model, response in responses.items() if response is None]
    retry_responses = {}
    if failed_models:
        print(f"Retrying failed models {failed_models} with timeout {retry_timeout}s")
        retry_responses = await query_models_parallel(failed_models, messages, timeout=retry_timeout, web_search=web_search, web_search_models=browse_capable)

    # Format results in original model order; keep first-attempt placeholder, add retry only if it responded
    stage1_results = []
    for model in models:
        first_response = responses.get(model)
        second_response = retry_responses.get(model)

        if first_response is not None:
            stage1_results.append({
                "model": model,
                "response": first_response.get('content', ''),
                "elapsed_time": first_response.get('elapsed_time'),
                "usage": first_response.get('usage'),
                "cost": first_response.get('cost'),
            })
        else:
            # First attempt failed; record placeholder
            stage1_results.append({
                "model": model,
                "response": "No response. Might retry.",
                "elapsed_time": None,
                "usage": None,
                "cost": None,
            })

            # Only store the retry if it produced content; annotate that it's the second attempt
            if second_response is not None:
                stage1_results.append({
                    "model": model,
                    "response": "Model did not reply on the first attempt. This is the second attempt\n" + second_response.get('content', ''),
                    "elapsed_time": second_response.get('elapsed_time'),
                    "usage": second_response.get('usage'),
                    "cost": second_response.get('cost'),
                })

    return stage1_results


async def stage1_collect_responses_streaming(
    user_query: str, 
    web_search: bool = False,
    majority_mode: bool = False,
    coding_mode: bool = False
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stage 1: Collect individual responses from all council models, streaming results.

    Args:
        user_query: The user's question
        web_search: Whether to enable web search
        majority_mode: If True, yield 'majority_reached' when 50%+ models have responded
        coding_mode: Whether coding mode is enabled

    Yields:
        Dicts with event type and data:
        - {'type': 'model_complete', 'model': str, 'response': dict, 'completed': int, 'total': int}
        - {'type': 'majority_reached', 'results': list} (if majority_mode=True)
        - {'type': 'stage_complete', 'results': list}
    """
    messages = [{"role": "user", "content": user_query}]
    models = get_council_models_active()
    browse_capable = get_browse_capable_models() if web_search else None
    coding_capable = get_coding_capable_models()
    
    # Filter out coding models unless coding_mode is set,
    # or web_search is set and the model can browse
    if not coding_mode:
        models = [
            m for m in models
            if m not in coding_capable or (web_search and browse_capable and m in browse_capable)
        ]
    
    total_models = len(models)
    majority_threshold = math.ceil(total_models / 2)
    
    results = {}  # model -> response dict
    completed_count = 0
    majority_yielded = False
    
    async for model, response, completed, total in query_models_streaming(models, messages, web_search=web_search, web_search_models=browse_capable):
        completed_count = completed
        
        if response is not None:
            result = {
                "model": model,
                "response": response.get('content', ''),
                "elapsed_time": response.get('elapsed_time'),
                "usage": response.get('usage'),
                "cost": response.get('cost'),
            }
            results[model] = result
            
            yield {
                'type': 'model_complete',
                'model': model,
                'response': result,
                'completed': completed_count,
                'total': total_models
            }
            
            # Check if majority threshold reached
            if majority_mode and not majority_yielded and len(results) >= majority_threshold:
                majority_yielded = True
                # Return results in original model order
                ordered_results = [results[m] for m in models if m in results]
                yield {
                    'type': 'majority_reached',
                    'results': ordered_results,
                    'completed': len(results),
                    'total': total_models
                }
        else:
            # Model failed
            yield {
                'type': 'model_failed',
                'model': model,
                'completed': completed_count,
                'total': total_models
            }
    
    # Build final results in original model order, including placeholders for failed models
    stage1_results = []
    for model in models:
        if model in results:
            stage1_results.append(results[model])
        else:
            stage1_results.append({
                "model": model,
                "response": "No response.",
                "elapsed_time": None,
                "usage": None,
                "cost": None,
            })
    
    yield {
        'type': 'stage_complete',
        'results': stage1_results
    }


async def stage2_collect_rankings_streaming(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    majority_mode: bool = False
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stage 2: Each model ranks the anonymized responses, streaming results.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1
        majority_mode: If True, yield 'majority_reached' when 50%+ models have responded

    Yields:
        Dicts with event type and data
    """
    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    messages = [{"role": "user", "content": ranking_prompt}]

    # Identify models that successfully responded in Stage 1
    successful_models = set()
    for result in stage1_results:
        if result.get('response') != "No response." and result.get('response') != "No response. Might retry.":
            successful_models.add(result['model'])

    # Only invite successful models to be judges
    judges = [m for m in get_council_models_active() if m in successful_models]
    total_judges = len(judges)
    majority_threshold = math.ceil(total_judges / 2)
    
    results = {}  # model -> ranking result
    majority_yielded = False

    async for model, response, completed, total in query_models_streaming(judges, messages):
        if response is not None:
            full_text = response.get('content', '')
            parsed = parse_ranking_from_text(full_text)
            result = {
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parsed,
                "elapsed_time": response.get('elapsed_time'),
                "cost": response.get('cost'),
            }
            results[model] = result
            
            yield {
                'type': 'model_complete',
                'model': model,
                'response': result,
                'completed': len(results),
                'total': total_judges
            }
            
            # Check if majority threshold reached
            if majority_mode and not majority_yielded and len(results) >= majority_threshold:
                majority_yielded = True
                ordered_results = [results[m] for m in judges if m in results]
                yield {
                    'type': 'majority_reached',
                    'results': ordered_results,
                    'label_to_model': label_to_model,
                    'completed': len(results),
                    'total': total_judges
                }
        else:
            yield {
                'type': 'model_failed',
                'model': model,
                'completed': completed,
                'total': total_judges
            }
    
    # Build final results
    stage2_results = [results[m] for m in judges if m in results]
    
    yield {
        'type': 'stage_complete',
        'results': stage2_results,
        'label_to_model': label_to_model
    }


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Stage 2: Each model ranks the anonymized responses.

    Args:
        user_query: The original user query
        stage1_results: Results from Stage 1

    Returns:
        Tuple of (rankings list, label_to_model mapping)
    """
    # Create anonymized labels for responses (Response A, Response B, etc.)
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    # Create mapping from label to model name
    label_to_model = {
        f"Response {label}": result['model']
        for label, result in zip(labels, stage1_results)
    }

    # Build the ranking prompt
    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    messages = [{"role": "user", "content": ranking_prompt}]

    # Identify models that successfully responded in Stage 1
    successful_models = set()
    for result in stage1_results:
        # Check if this is a real response, not the placeholder
        if result.get('response') != "No response. Might retry.":
            successful_models.add(result['model'])

    # Only invite successful models to be judges
    judges = [m for m in get_council_models_active() if m in successful_models]

    # Get rankings from all council models in parallel
    responses = await query_models_parallel(judges, messages)

    # Format results
    stage2_results = []
    for model, response in responses.items():
        if response is not None:
            full_text = response.get('content', '')
            parsed = parse_ranking_from_text(full_text)
            stage2_results.append({
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parsed,
                "elapsed_time": response.get('elapsed_time'),
                "cost": response.get('cost'),
            })

    return stage2_results, label_to_model


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes final response.

    Args:
        user_query: The original user query
        stage1_results: Individual model responses from Stage 1
        stage2_results: Rankings from Stage 2

    Returns:
        Dict with 'model' and 'response' keys
    """
    # Build comprehensive context for chairman
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    prompt_override = load_chairman_prompt_override()
    if prompt_override:
        chairman_prompt = prompt_override.format(
            user_query=user_query,
            stage1_text=stage1_text,
            stage2_text=stage2_text
        )
    else:
        chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

    messages = [{"role": "user", "content": chairman_prompt}]

    # Query the chairman model
    chairman_model = get_active_chairman_model()
    response = await query_model(chairman_model, messages)

    if response is None:
        # Fallback if chairman fails
        return {
            "model": chairman_model,
            "response": "Error: Unable to generate final synthesis.",
            "custom_chairman_instructions": bool(prompt_override),
        }

    return {
        "model": chairman_model,
        "response": response.get('content', ''),
        "elapsed_time": response.get('elapsed_time'),
        "cost": response.get('cost'),
        "custom_chairman_instructions": bool(prompt_override),
    }


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Args:
        ranking_text: The full text response from the model

    Returns:
        List of response labels in ranked order
    """
    import re

    # Look for "FINAL RANKING:" section
    if "FINAL RANKING:" in ranking_text:
        # Extract everything after "FINAL RANKING:"
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            # Try to extract numbered list format (e.g., "1. Response A")
            # This pattern looks for: number, period, optional space, "Response X"
            numbered_matches = re.findall(r'\d+\.\s*Response [A-Z]', ranking_section)
            if numbered_matches:
                # Extract just the "Response X" part
                result = []
                for m in numbered_matches:
                    match = re.search(r'Response [A-Z]', m)
                    if match:
                        result.append(match.group())
                return result

            # Fallback: Extract all "Response X" patterns in order
            matches = re.findall(r'Response [A-Z]', ranking_section)
            return matches

    # Fallback: try to find any "Response X" patterns in order
    matches = re.findall(r'Response [A-Z]', ranking_text)
    return matches


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
    stage1_results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all models.

    Args:
        stage2_results: Rankings from each model
        label_to_model: Mapping from anonymous labels to model names

    Returns:
        List of dicts with model name and average rank, sorted best to worst
    """
    from collections import defaultdict

    # Track positions for each model
    model_positions = defaultdict(list)

    # Track timing and cost per model from Stage 1 and Stage 2
    stage1_time_cost = defaultdict(lambda: {"elapsed_time": 0.0, "cost": 0.0})
    stage2_time_cost = defaultdict(lambda: {"elapsed_time": 0.0, "cost": 0.0})

    for result in stage1_results:
        model = result.get("model")
        if model is None:
            continue
        elapsed = result.get("elapsed_time")
        cost = result.get("cost")
        if elapsed is not None:
            stage1_time_cost[model]["elapsed_time"] += float(elapsed)
        if cost is not None:
            stage1_time_cost[model]["cost"] += float(cost)

    for ranking in stage2_results:
        ranking_text = ranking['ranking']
        model = ranking.get('model')
        if model is not None:
            elapsed = ranking.get('elapsed_time')
            cost = ranking.get('cost')
            if elapsed is not None:
                stage2_time_cost[model]["elapsed_time"] += float(elapsed)
            if cost is not None:
                stage2_time_cost[model]["cost"] += float(cost)

        # Parse the ranking from the structured format
        parsed_ranking = parse_ranking_from_text(ranking_text)

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    # Calculate average position for each model
    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            avg_rank = sum(positions) / len(positions)
            total_elapsed = stage1_time_cost[model]["elapsed_time"] + stage2_time_cost[model]["elapsed_time"]
            total_cost = stage1_time_cost[model]["cost"] + stage2_time_cost[model]["cost"]
            aggregate.append({
                "model": model,
                "average_rank": round(avg_rank, 2),
                "rankings_count": len(positions),
                "total_elapsed_time": round(total_elapsed, 2),
                "total_cost": round(total_cost, 2),
            })

    # Sort by average rank (lower is better)
    aggregate.sort(key=lambda x: x['average_rank'])

    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """
    Generate a short title for a conversation based on the first user message.

    Args:
        user_query: The first user message

    Returns:
        A short title (3-5 words)
    """
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]

    # Use gemini-2.5-flash for title generation (fast and cheap)
    response = await query_model("google/gemini-2.5-flash", messages, timeout=30.0)

    if response is None:
        # Fallback to a generic title
        return "New Conversation"

    title = response.get('content', 'New Conversation').strip()

    # Clean up the title - remove quotes, limit length
    title = title.strip('"\'')

    # Truncate if too long
    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(user_query: str) -> Tuple[List, List, Dict, Dict]:
    """
    Run the complete 3-stage council process.

    Args:
        user_query: The user's question

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
    """
    # Stage 1: Collect individual responses
    stage1_results = await stage1_collect_responses(user_query)

    # If no models responded successfully, return error
    if not stage1_results:
        return [], [], {
            "model": "error",
            "response": "All models failed to respond. Please try again."
        }, {}

    # Stage 2: Collect rankings
    stage2_results, label_to_model = await stage2_collect_rankings(user_query, stage1_results)

    # Calculate aggregate rankings
    aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model, stage1_results)

    # Stage 3: Synthesize final answer
    stage3_result = await stage3_synthesize_final(
        user_query,
        stage1_results,
        stage2_results
    )

    # Prepare metadata
    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings
    }

    return stage1_results, stage2_results, stage3_result, metadata
