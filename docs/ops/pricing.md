# Pricing & FX

`agentic_engine.core.pricing` holds a per-region pricing table and a
USD-bridged FX converter.

## API

```python
from agentic_engine import estimate, convert, REGION_PRICING

cost = estimate("qwen-plus",
                prompt_tokens=2_000_000,
                completion_tokens=500_000,
                region="cn",
                target_currency="USD")
# {'model': 'qwen-plus', 'region': 'cn', 'currency': 'USD', 'cost': 0.42}

# Direct currency conversion (USD bridge)
convert(100.0, "CNY", "SGD")
```

## Regions

| Region | Currency | Source                              |
|--------|----------|-------------------------------------|
| `cn`   | CNY      | Bailian Hangzhou price page         |
| `sg`   | USD      | Model Studio Singapore price page   |
| `us`   | USD      | DashScope International (fallback)  |

`REGION_PRICING[region][model]` returns `(in_per_million, out_per_million, currency)`.

## Updating the table

The pricing table is hardcoded with the snapshot date in the docstring.
Update by editing `REGION_PRICING` and `_FX` in `pricing.py`, then bump
the patch version. There is **no** runtime fetch — we never want a
flaky network call to inflate billing reports.
