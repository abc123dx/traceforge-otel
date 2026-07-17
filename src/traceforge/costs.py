"""可配置的 Token 成本估算。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CostModelError(ValueError):
    """成本模型文档无效时抛出。"""


@dataclass(frozen=True, slots=True)
class PriceRate:
    """每百万输入与输出 Token 的美元费率。"""

    input_per_1m: float
    output_per_1m: float


@dataclass(frozen=True, slots=True)
class CostModel:
    """支持精确、前缀与通配符匹配的模型价格映射。"""

    name: str
    rates: dict[str, PriceRate]

    @classmethod
    def from_path(cls, path: Path) -> CostModel:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CostModelError(f"无法读取成本模型 {path}：{exc}") from exc
        if not isinstance(payload, dict):
            raise CostModelError("成本模型必须是 JSON 对象。")
        return cls.from_dict(payload, fallback_name=path.stem)

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        fallback_name: str = "custom",
    ) -> CostModel:
        raw_models = payload.get("models", payload)
        if not isinstance(raw_models, dict):
            raise CostModelError("'models' 必须是 JSON 对象。")
        name_value = payload.get("name", fallback_name)
        name = str(name_value)
        rates: dict[str, PriceRate] = {}
        for model, raw_rate in raw_models.items():
            if model in {"name", "currency"} and "models" not in payload:
                continue
            if not isinstance(model, str) or not isinstance(raw_rate, dict):
                raise CostModelError(f"模型 {model!r} 的费率必须是对象。")
            try:
                input_rate = float(raw_rate["input_per_1m"])
                output_rate = float(raw_rate["output_per_1m"])
            except (KeyError, TypeError, ValueError) as exc:
                raise CostModelError(
                    f"模型 {model!r} 的费率需要数字类型的 input_per_1m 和 output_per_1m。"
                ) from exc
            if input_rate < 0 or output_rate < 0:
                raise CostModelError(f"模型 {model!r} 的费率不能为负数。")
            rates[model] = PriceRate(input_rate, output_rate)
        if not rates:
            raise CostModelError("成本模型中没有费率。")
        return cls(name=name, rates=rates)

    @classmethod
    def demo(cls) -> CostModel:
        """仅供合成演示模型使用的价格。"""

        return cls(
            name="demo-rates",
            rates={"demo-agent-1": PriceRate(input_per_1m=1.25, output_per_1m=5.0)},
        )

    def resolve(self, model: str) -> PriceRate | None:
        if model in self.rates:
            return self.rates[model]
        prefixes = sorted(
            (pattern[:-1] for pattern in self.rates if pattern.endswith("*")),
            key=len,
            reverse=True,
        )
        for prefix in prefixes:
            if model.startswith(prefix):
                return self.rates[f"{prefix}*"]
        return self.rates.get("*")

    def estimate(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        rate = self.resolve(model)
        if rate is None:
            return None
        return (input_tokens * rate.input_per_1m + output_tokens * rate.output_per_1m) / 1_000_000
