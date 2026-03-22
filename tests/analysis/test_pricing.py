"""Tests for pricing module: normalization, lookup, and cost computation."""

from vibelens.analysis.pricing import (
    compute_step_cost,
    compute_trajectory_cost,
    lookup_pricing,
    normalize_model_name,
)
from vibelens.models.trajectories import Agent, Metrics, Step, Trajectory


class TestNormalizeModelName:
    """Tests for normalize_model_name."""

    def test_exact_canonical_names(self):
        """Canonical names normalize to themselves."""
        assert normalize_model_name("claude-opus-4-6") == "claude-opus-4-6"
        assert normalize_model_name("gpt-5.4") == "gpt-5.4"
        assert normalize_model_name("gemini-2.5-pro") == "gemini-2.5-pro"
        assert normalize_model_name("o3") == "o3"
        assert normalize_model_name("o4-mini") == "o4-mini"
        print("All canonical names normalize correctly")

    def test_date_suffixes(self):
        """Date suffixes stripped via prefix matching."""
        assert normalize_model_name("claude-3-5-sonnet-20241022") == "claude-3-5-sonnet"
        assert normalize_model_name("claude-sonnet-4-6-20250514") == "claude-sonnet-4-6"
        assert normalize_model_name("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
        print("Date suffixes handled correctly")

    def test_gemini_path_prefixes(self):
        """Gemini path prefixes stripped before matching."""
        assert normalize_model_name("models/gemini-2.5-flash") == "gemini-2.5-flash"
        assert normalize_model_name("accounts/abc/models/gemini-2.5-pro") == "gemini-2.5-pro"
        assert normalize_model_name("models/gemini-2.0-flash") == "gemini-2.0-flash"
        print("Gemini path prefixes stripped correctly")

    def test_case_insensitive(self):
        """Case insensitive matching."""
        assert normalize_model_name("Claude-Opus-4-6") == "claude-opus-4-6"
        assert normalize_model_name("GPT-5.4-MINI") == "gpt-5.4-mini"
        assert normalize_model_name("GEMINI-2.5-FLASH") == "gemini-2.5-flash"
        print("Case insensitive matching works")

    def test_mini_before_base_ordering(self):
        """Mini/nano variants matched before base model."""
        assert normalize_model_name("gpt-5.4-mini") == "gpt-5.4-mini"
        assert normalize_model_name("gpt-5.4-nano") == "gpt-5.4-nano"
        assert normalize_model_name("gpt-4.1-mini") == "gpt-4.1-mini"
        assert normalize_model_name("gpt-4.1-nano") == "gpt-4.1-nano"
        # Base models still resolve
        assert normalize_model_name("gpt-5.4") == "gpt-5.4"
        assert normalize_model_name("gpt-4.1") == "gpt-4.1"
        print("Mini/nano ordering correct")

    def test_flash_lite_before_flash(self):
        """Flash-lite matched before flash."""
        assert normalize_model_name("gemini-2.5-flash-lite") == "gemini-2.5-flash-lite"
        assert normalize_model_name("gemini-2.5-flash") == "gemini-2.5-flash"
        print("Flash-lite ordering correct")

    def test_preview_suffixes(self):
        """Gemini preview tags handled via prefix matching."""
        assert normalize_model_name("gemini-2.5-flash-preview-04-17") == "gemini-2.5-flash"
        assert normalize_model_name("gemini-2.5-pro-preview") == "gemini-2.5-pro"
        print("Preview suffixes handled correctly")

    def test_unknown_models(self):
        """Unknown models return None."""
        assert normalize_model_name("some-random-model") is None
        assert normalize_model_name("totally-unknown-v99") is None
        print("Unknown models return None")

    def test_empty_and_none(self):
        """Empty string and None return None."""
        assert normalize_model_name("") is None
        assert normalize_model_name(None) is None

    def test_provider_slash_prefix(self):
        """Provider/model format strips provider prefix."""
        assert normalize_model_name("qwen/qwen3-max") == "qwen3-max"
        assert normalize_model_name("anthropic/claude-opus-4-6") == "claude-opus-4-6"
        assert normalize_model_name("openai/gpt-5.4") == "gpt-5.4"
        assert normalize_model_name("google/gemini-2.5-flash") == "gemini-2.5-flash"
        assert normalize_model_name("deepseek/deepseek-v3") == "deepseek-v3"
        assert normalize_model_name("meta-llama/llama-4-maverick") == "llama-4-maverick"

    def test_provider_colon_prefix(self):
        """Provider:model format strips provider prefix."""
        assert normalize_model_name("anthropic:claude-sonnet-4-5") == "claude-sonnet-4-5"
        assert normalize_model_name("openai:gpt-4.1-mini") == "gpt-4.1-mini"

    def test_nested_provider_prefix(self):
        """Multi-level provider paths strip all prefix segments."""
        assert normalize_model_name("org/anthropic/claude-opus-4-6") == "claude-opus-4-6"
        assert normalize_model_name("acme/qwen/qwen3-max") == "qwen3-max"

    def test_whitespace_trimmed(self):
        """Leading and trailing whitespace is stripped."""
        assert normalize_model_name("  claude-opus-4-6  ") == "claude-opus-4-6"
        assert normalize_model_name(" qwen/qwen3-max ") == "qwen3-max"
        assert normalize_model_name("\tgpt-5.4\n") == "gpt-5.4"

    def test_whitespace_only_returns_none(self):
        """Whitespace-only strings return None."""
        assert normalize_model_name("   ") is None
        assert normalize_model_name("\t\n") is None

    def test_provider_prefix_with_case_and_suffix(self):
        """Provider prefix combined with case variation and date suffix."""
        assert normalize_model_name("Anthropic/Claude-Sonnet-4-6-20250514") == "claude-sonnet-4-6"
        assert normalize_model_name("QWEN/QWEN3-MAX") == "qwen3-max"

    def test_unknown_provider_unknown_model(self):
        """Unknown provider with unknown model returns None."""
        assert normalize_model_name("acme/unknown-model") is None
        assert normalize_model_name("provider:unknown") is None

    def test_new_openai_models(self):
        """GPT-5.4 Pro and o3-pro resolve correctly."""
        assert normalize_model_name("gpt-5.4-pro") == "gpt-5.4-pro"
        assert normalize_model_name("o3-pro") == "o3-pro"
        # Ensure pro doesn't steal base gpt-5.4
        assert normalize_model_name("gpt-5.4") == "gpt-5.4"
        print("New OpenAI models normalize correctly")

    def test_xai_grok_models(self):
        """xAI Grok models resolve correctly."""
        assert normalize_model_name("grok-4.20-beta") == "grok-4.20-beta"
        assert normalize_model_name("grok-4") == "grok-4"
        assert normalize_model_name("grok-4.1-fast") == "grok-4.1-fast"
        # Date suffixes should work via prefix matching
        assert normalize_model_name("grok-4.20-beta-20260101") == "grok-4.20-beta"
        print("xAI Grok models normalize correctly")

    def test_deepseek_models(self):
        """DeepSeek models resolve correctly."""
        assert normalize_model_name("deepseek-v3") == "deepseek-v3"
        assert normalize_model_name("deepseek-v3-20260101") == "deepseek-v3"
        print("DeepSeek models normalize correctly")

    def test_mistral_models(self):
        """Mistral models resolve correctly with ordering."""
        assert normalize_model_name("magistral-medium") == "magistral-medium"
        assert normalize_model_name("mistral-large") == "mistral-large"
        assert normalize_model_name("mistral-medium-3.1") == "mistral-medium-3.1"
        assert normalize_model_name("codestral") == "codestral"
        assert normalize_model_name("mistral-small-4") == "mistral-small-4"
        # mistral-medium-3.1 shouldn't collide with mistral-medium prefix
        assert normalize_model_name("mistral-medium-3.1-latest") == "mistral-medium-3.1"
        print("Mistral models normalize correctly")

    def test_qwen_models(self):
        """Qwen models resolve correctly."""
        assert normalize_model_name("qwen3-max") == "qwen3-max"
        assert normalize_model_name("qwen3.5-plus") == "qwen3.5-plus"
        assert normalize_model_name("qwen3-coder-next") == "qwen3-coder-next"
        print("Qwen models normalize correctly")

    def test_kimi_models(self):
        """Moonshot Kimi models resolve with k2.5 before k2."""
        assert normalize_model_name("kimi-k2.5") == "kimi-k2.5"
        assert normalize_model_name("kimi-k2") == "kimi-k2"
        # Ensure k2.5 doesn't match k2 prefix
        assert normalize_model_name("kimi-k2.5-something") == "kimi-k2.5"
        print("Kimi models normalize correctly")

    def test_minimax_models(self):
        """MiniMax models resolve with m2.7 before m2.5."""
        assert normalize_model_name("minimax-m2.7") == "minimax-m2.7"
        assert normalize_model_name("minimax-m2.5") == "minimax-m2.5"
        print("MiniMax models normalize correctly")

    def test_glm_models(self):
        """Zhipu GLM models resolve with specificity ordering."""
        assert normalize_model_name("glm-5-code") == "glm-5-code"
        assert normalize_model_name("glm-5") == "glm-5"
        assert normalize_model_name("glm-4.7-flashx") == "glm-4.7-flashx"
        assert normalize_model_name("glm-4.7") == "glm-4.7"
        # Ensure code variant doesn't match base
        assert normalize_model_name("glm-5-code-v2") == "glm-5-code"
        print("GLM models normalize correctly")

    def test_seed_models(self):
        """ByteDance Seed models resolve correctly."""
        assert normalize_model_name("seed-2.0-pro") == "seed-2.0-pro"
        assert normalize_model_name("seed-2.0-lite") == "seed-2.0-lite"
        assert normalize_model_name("seed-2.0-mini") == "seed-2.0-mini"
        assert normalize_model_name("seed-2.0-code") == "seed-2.0-code"
        print("Seed models normalize correctly")

    def test_llama_models(self):
        """Meta Llama 4 models resolve correctly."""
        assert normalize_model_name("llama-4-maverick") == "llama-4-maverick"
        assert normalize_model_name("llama-4-scout") == "llama-4-scout"
        print("Llama models normalize correctly")

    def test_gemini_3_1_pro(self):
        """Gemini 3.1 Pro resolves correctly."""
        assert normalize_model_name("gemini-3.1-pro") == "gemini-3.1-pro"
        assert normalize_model_name("gemini-3.1-pro-preview") == "gemini-3.1-pro"
        assert normalize_model_name("models/gemini-3.1-pro") == "gemini-3.1-pro"
        print("Gemini 3.1 Pro normalizes correctly")


class TestLookupPricing:
    """Tests for lookup_pricing."""

    def test_exact_match(self):
        """Exact canonical name returns pricing."""
        pricing = lookup_pricing("claude-opus-4-6")
        assert pricing is not None
        assert pricing.input_per_mtok == 5.00
        assert pricing.output_per_mtok == 25.00
        print(f"Opus 4.6: in={pricing.input_per_mtok}, out={pricing.output_per_mtok}")

    def test_normalized_match(self):
        """Non-canonical name resolves via normalization."""
        pricing = lookup_pricing("claude-3-5-sonnet-20241022")
        assert pricing is not None
        assert pricing.input_per_mtok == 3.00
        print(f"3.5 Sonnet (with date): in={pricing.input_per_mtok}")

    def test_gemini_path_match(self):
        """Gemini model with path prefix resolves."""
        pricing = lookup_pricing("models/gemini-2.5-flash")
        assert pricing is not None
        assert pricing.input_per_mtok == 0.30
        print(f"Gemini 2.5 Flash (with path): in={pricing.input_per_mtok}")

    def test_new_providers_lookup(self):
        """New provider models resolve with correct pricing."""
        grok = lookup_pricing("grok-4")
        assert grok is not None
        assert grok.input_per_mtok == 3.00
        assert grok.output_per_mtok == 15.00

        ds = lookup_pricing("deepseek-v3")
        assert ds is not None
        assert ds.input_per_mtok == 0.28
        assert ds.output_per_mtok == 0.42

        mistral = lookup_pricing("mistral-large")
        assert mistral is not None
        assert mistral.input_per_mtok == 0.50

        glm = lookup_pricing("glm-5")
        assert glm is not None
        assert glm.input_per_mtok == 1.00

        seed = lookup_pricing("seed-2.0-pro")
        assert seed is not None
        assert seed.output_per_mtok == 2.37

        llama = lookup_pricing("llama-4-maverick")
        assert llama is not None
        assert llama.input_per_mtok == 0.15
        print("New provider lookups correct")

    def test_unknown_returns_none(self):
        """Unknown model returns None."""
        assert lookup_pricing("unknown-model") is None
        assert lookup_pricing(None) is None
        assert lookup_pricing("") is None
        print("Unknown/None/empty return None")


class TestComputeStepCost:
    """Tests for compute_step_cost."""

    def test_basic_arithmetic(self):
        """Cost computed correctly for a step with all token types."""
        step = Step(
            step_id="s1",
            source="agent",
            message="hello",
            model_name="claude-sonnet-4-6",
            metrics=Metrics(
                prompt_tokens=1000,
                completion_tokens=500,
                cached_tokens=200,
                cache_creation_tokens=100,
            ),
        )
        cost = compute_step_cost(step)
        assert cost is not None

        # (1000-200)*3.00 + 200*0.30 + 100*3.75 + 500*15.00
        # = 2400 + 60 + 375 + 7500 = 10335
        # / 1_000_000 = 0.010335
        expected = 0.010335
        assert abs(cost - expected) < 1e-6
        print(f"Step cost: ${cost:.6f} (expected ${expected:.6f})")

    def test_no_cache_tokens(self):
        """Cost computed correctly with no cache tokens."""
        step = Step(
            step_id="s1",
            source="agent",
            message="hello",
            model_name="gpt-5.4",
            metrics=Metrics(prompt_tokens=1000, completion_tokens=500),
        )
        cost = compute_step_cost(step)
        assert cost is not None

        # 1000*2.50 + 500*15.00 = 2500 + 7500 = 10000
        # / 1_000_000 = 0.01
        expected = 0.01
        assert abs(cost - expected) < 1e-6
        print(f"No-cache step cost: ${cost:.6f}")

    def test_no_metrics_returns_none(self):
        """Step without metrics returns None."""
        step = Step(step_id="s1", source="agent", message="hello")
        assert compute_step_cost(step) is None
        print("No-metrics returns None")

    def test_unknown_model_returns_none(self):
        """Step with unrecognized model returns None."""
        step = Step(
            step_id="s1",
            source="agent",
            message="hello",
            model_name="unknown-model",
            metrics=Metrics(prompt_tokens=100, completion_tokens=50),
        )
        assert compute_step_cost(step) is None
        print("Unknown model returns None")

    def test_session_model_fallback(self):
        """Uses session_model when step has no model_name."""
        step = Step(
            step_id="s1",
            source="agent",
            message="hello",
            metrics=Metrics(prompt_tokens=1000, completion_tokens=500),
        )
        cost = compute_step_cost(step, session_model="claude-haiku-4-5")
        assert cost is not None

        # (1000-0)*1.00 + 0*0.10 + 0*1.25 + 500*5.00 = 1000 + 2500 = 3500
        # / 1_000_000 = 0.0035
        expected = 0.0035
        assert abs(cost - expected) < 1e-6
        print(f"Fallback cost: ${cost:.6f}")

    def test_step_model_overrides_session(self):
        """Step model_name takes precedence over session_model."""
        step = Step(
            step_id="s1",
            source="agent",
            message="hello",
            model_name="claude-haiku-4-5",
            metrics=Metrics(prompt_tokens=1000, completion_tokens=500),
        )
        cost_haiku = compute_step_cost(step, session_model="claude-opus-4-6")
        assert cost_haiku is not None

        # Should use haiku pricing, not opus
        # (1000*1.00 + 500*5.00) / 1M = 0.0035
        expected = 0.0035
        assert abs(cost_haiku - expected) < 1e-6
        print(f"Step model override: ${cost_haiku:.6f}")


class TestComputeTrajectoryCost:
    """Tests for compute_trajectory_cost."""

    def test_sums_steps(self):
        """Trajectory cost sums step costs."""
        traj = Trajectory(
            session_id="t1",
            agent=Agent(name="claude-code", model_name="claude-sonnet-4-6"),
            steps=[
                Step(
                    step_id="s1",
                    source="user",
                    message="hi",
                    metrics=Metrics(prompt_tokens=100, completion_tokens=0),
                ),
                Step(
                    step_id="s2",
                    source="agent",
                    message="hello",
                    metrics=Metrics(prompt_tokens=200, completion_tokens=100),
                ),
            ],
        )
        cost = compute_trajectory_cost(traj)
        assert cost is not None
        assert cost > 0

        # s1: 100*3.00/1M = 0.0003
        # s2: 200*3.00/1M + 100*15.00/1M = 0.0006 + 0.0015 = 0.0021
        # total = 0.0024
        expected = 0.0024
        assert abs(cost - expected) < 1e-6
        print(f"Trajectory cost: ${cost:.6f}")

    def test_mixed_models(self):
        """Steps with different models priced correctly."""
        traj = Trajectory(
            session_id="t1",
            agent=Agent(name="claude-code", model_name="claude-sonnet-4-6"),
            steps=[
                Step(
                    step_id="s1",
                    source="agent",
                    message="hi",
                    model_name="claude-haiku-4-5",
                    metrics=Metrics(prompt_tokens=1000, completion_tokens=500),
                ),
                Step(
                    step_id="s2",
                    source="agent",
                    message="hello",
                    metrics=Metrics(prompt_tokens=1000, completion_tokens=500),
                ),
            ],
        )
        cost = compute_trajectory_cost(traj)
        assert cost is not None

        # s1 (haiku): (1000*1.00 + 500*5.00) / 1M = 0.0035
        # s2 (sonnet fallback): (1000*3.00 + 500*15.00) / 1M = 0.0105
        # total = 0.0140
        expected = 0.014
        assert abs(cost - expected) < 1e-6
        print(f"Mixed model cost: ${cost:.6f}")

    def test_no_priced_steps_returns_none(self):
        """All unknown models returns None."""
        traj = Trajectory(
            session_id="t1",
            agent=Agent(name="test"),
            steps=[
                Step(
                    step_id="s1",
                    source="agent",
                    message="hi",
                    model_name="unknown-model",
                    metrics=Metrics(prompt_tokens=100, completion_tokens=50),
                ),
            ],
        )
        assert compute_trajectory_cost(traj) is None
        print("No-priced-steps returns None")

    def test_partial_pricing(self):
        """Only priced steps contribute to total."""
        traj = Trajectory(
            session_id="t1",
            agent=Agent(name="test"),
            steps=[
                Step(
                    step_id="s1",
                    source="agent",
                    message="hi",
                    model_name="claude-haiku-4-5",
                    metrics=Metrics(prompt_tokens=1000, completion_tokens=500),
                ),
                Step(
                    step_id="s2",
                    source="agent",
                    message="hello",
                    model_name="unknown-model",
                    metrics=Metrics(prompt_tokens=1000, completion_tokens=500),
                ),
            ],
        )
        cost = compute_trajectory_cost(traj)
        assert cost is not None
        # Only s1 contributes: 0.0035
        expected = 0.0035
        assert abs(cost - expected) < 1e-6
        print(f"Partial pricing cost: ${cost:.6f}")
