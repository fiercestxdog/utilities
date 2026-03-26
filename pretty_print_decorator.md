# `@pretty_print` Decorator

A flexible decorator using [`rich`](https://github.com/Textualize/rich) that pretty-prints a function's return value inside a styled panel. Works with or without arguments.

## Dependencies

```
rich>=13.0.0
pip install rich==13.7.1
```

---

## Implementation

```python
import functools
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty

console = Console()

def pretty_print(_func=None, *, title=None, color="cyan", border="dim"):
    """
    Decorator that prints function return values in a Rich panel.

    Can be used with or without arguments:
        @pretty_print                        # default panel, cyan, dim border
        @pretty_print(color="green")         # custom color
        @pretty_print(title="LLM Output")    # custom title

    Args:
        title  (str):  Panel title. Defaults to the function name.
        color  (str):  Title text color. Any Rich color name. Default: "cyan".
        border (str):  Border style. Any Rich style string. Default: "dim".
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            console.print(Panel(
                Pretty(result),
                title=f"[bold {color}]{title or func.__name__}[/]",
                border_style=border
            ))
            return result
        return wrapper

    if _func is not None:        # used as @pretty_print  (no parens)
        return decorator(_func)
    return decorator             # used as @pretty_print(...) with args
```

---

## Usage

### No arguments — uses defaults
```python
@pretty_print
def get_response(prompt):
    return {"answer": "42", "confidence": 0.98}
```
```
╭─────────── get_response ───────────╮
│ {'answer': '42', 'confidence': 0.98} │
╰─────────────────────────────────────╯
```

### Custom color and border
```python
@pretty_print(color="green", border="bold")
def get_agent_plan(prompt):
    return ["step 1: search", "step 2: summarize", "step 3: respond"]
```

### Custom title
```python
@pretty_print(title="LLM Output")
def call_llm(prompt):
    return {"text": "Here is my response...", "tokens": 120}
```

---

## How It Works

The `_func=None` positional + keyword-only `*` pattern lets the decorator handle both call styles:

| Usage | What happens |
|-------|-------------|
| `@pretty_print` | Python passes the function as `_func` → wraps immediately |
| `@pretty_print(...)` | `_func` stays `None` → returns `decorator` to be applied next |

---

## Composing with Other Agent Decorators

Stacks cleanly with retry, timeout, and validation decorators:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@pretty_print(title="Agent Response", color="magenta")
@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def call_llm(prompt: str):
    ...
```

Applied bottom-up: retry wraps the raw call, pretty_print wraps the final result.
