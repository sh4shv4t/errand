"""Delegate two errands with the Python SDK. Run `errand up` (or `errand serve`) first.

    python examples/quickstart.py
"""

import json

from errand import seed
from errand.client import Errand

# Uses ERRAND_API_KEY if set, otherwise the local demo Sender's key.
key = None
try:
    key = seed.load_keys()["senders"]["snd_alan"]["api_key"]
except KeyError:
    pass
e = Errand(api_key=key)

print("Who would get a math errand?")
for r in e.recommend("math.final-answer", preset="cheapest")["runners"]:
    print(f"  {r['name']:8} ${r['price_usd']:.4f}  pass~{r['expected_pass_rate']:.0%}  p95 {r['p95_latency_ms']} ms")

r = e.send_math("A shirt costs $60. It is discounted by 25%. What is the sale price in dollars?", expected="45")
print(f"\nmath -> {r['answer']} ({r['verdict']}) by {r['runner']['name']}, paid ${r['total_usd']:.5f}, saved ${r['saved_usd']:.5f}")

# Demo Runners are simulated and only know the built-in tasks; register a real model to send anything.
task = seed.taskbank.items("code.python.tests", "demo")[0]
r = e.send_code(task["function_name"], task["spec"], task["tests"])
print(f"code -> {r['status']} ({r['detail']}) by {r['runner']['name'] if r['runner'] else 'nobody'}")

print("\nwallet:", json.dumps(e.wallet()["balances"]))
