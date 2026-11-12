import pytest
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / "billing_assistant" / ".env")
from google.adk.evaluation.agent_evaluator import AgentEvaluator


@pytest.mark.asyncio
@pytest.mark.parametrize("evalset", [
    "billing_assistant/billing_regression.evalset.json",
    "billing_assistant/bill_tools.evalset.json",
])
async def test_agent_evals(evalset):
    """Fails (non-zero exit) if any case misses the thresholds in test_config.json next to the evalset."""
    await AgentEvaluator.evaluate(
        agent_module="billing_assistant",
        eval_dataset_file_path_or_dir=evalset,
        num_runs=1,
    )