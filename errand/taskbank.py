"""Built-in tasks with known answers, written for Errand.

Splits:
  exam     onboarding exam every new Runner takes per lane
  mystery  hidden tasks mixed into traffic to keep ratings honest
  demo     public tasks used by `errand demo` and the dashboard "try it" form
"""

from __future__ import annotations

import random

MATH = [
    # demo
    dict(id="m01", split="demo", answer="42", problem="A bakery sells muffins in boxes of 6. Priya buys 9 boxes and gives away 12 muffins. How many muffins does she have left?"),
    dict(id="m02", split="demo", answer="18", problem="A train travels 216 km in 12 hours at a constant speed. What is its speed in km per hour?"),
    dict(id="m03", split="demo", answer="7", problem="Solve for x: 3x + 14 = 35."),
    dict(id="m04", split="demo", answer="120", problem="In how many different orders can 5 distinct books be placed on a shelf?"),
    dict(id="m05", split="demo", answer="45", problem="A shirt costs $60. It is discounted by 25%. What is the sale price in dollars?"),
    dict(id="m06", split="demo", answer="1225", problem="What is the sum of the integers from 1 to 49 inclusive?"),
    dict(id="m07", split="demo", answer="0.25", problem="Two fair coins are tossed. What is the probability that both land heads? Give a decimal."),
    dict(id="m08", split="demo", answer="96", problem="A rectangle has a perimeter of 40 cm and one side of length 12 cm. What is its area in square cm?"),
    dict(id="m09", split="demo", answer="13", problem="A right triangle has legs of length 5 and 12. How long is the hypotenuse?"),
    dict(id="m10", split="demo", answer="64", problem="A bacteria colony doubles every hour. It starts with 2 cells. How many cells are there after 5 hours?"),
    dict(id="m11", split="demo", answer="48", problem="Leo is 4 times as old as his daughter. In 6 years he will be 3 times as old as her. How old is Leo now?"),
    dict(id="m12", split="demo", answer="210", problem="How many ways can a committee of 4 people be chosen from 10 people?"),
    # exam
    dict(id="m13", split="exam", answer="15", problem="A tank fills at 3 liters per minute and drains at 1 liter per minute. How many minutes to put 30 liters in an empty tank?"),
    dict(id="m14", split="exam", answer="11", problem="What is the smallest prime number greater than 7?"),
    dict(id="m15", split="exam", answer="3", problem="The mean of four numbers is 5. Three of them are 4, 7 and 6. What is the fourth number?"),
    dict(id="m16", split="exam", answer="81", problem="Compute 3 to the power of 4."),
    dict(id="m17", split="exam", answer="24", problem="A car uses 6 liters of fuel per 100 km. How many liters does it use on a 400 km trip?"),
    dict(id="m18", split="exam", answer="5", problem="Solve for n: 2^(n+1) = 64."),
    dict(id="m19", split="exam", answer="6", problem="Three workers paint a fence in 10 hours. How many hours would 5 workers take at the same rate?"),
    dict(id="m20", split="exam", answer="0.5", problem="A die is rolled. What is the probability of getting an even number? Give a decimal."),
    # mystery
    dict(id="m21", split="mystery", answer="28", problem="A school has 7 classes with 32 students each. 196 students go on a trip. How many students stay behind?"),
    dict(id="m22", split="mystery", answer="9", problem="Solve for y: 5y - 17 = 28."),
    dict(id="m23", split="mystery", answer="720", problem="How many ways can 6 runners finish a race if there are no ties?"),
    dict(id="m24", split="mystery", answer="22", problem="What is the remainder when 2023 is divided by 23?"),
    dict(id="m25", split="mystery", answer="300", problem="A store marks up a $240 item by 25%. What is the new price in dollars?"),
    dict(id="m26", split="mystery", answer="78", problem="What is the sum of the first 12 positive integers?"),
    dict(id="m27", split="mystery", answer="50", problem="A square has a diagonal of length 10. What is its area?"),
    dict(id="m28", split="mystery", answer="10", problem="The ratio of cats to dogs at a shelter is 3:5. There are 40 animals. How many more dogs than cats are there?"),
    dict(id="m29", split="mystery", answer="1000", problem="What is 10 cubed?"),
    dict(id="m30", split="mystery", answer="35", problem="A phone plan costs $20 per month plus $0.05 per text. Ana sends 300 texts. What is her bill in dollars?"),
    dict(id="m31", split="mystery", answer="12", problem="What is the greatest common divisor of 36 and 84?"),
    dict(id="m32", split="mystery", answer="0.75", problem="What is 3/4 written as a decimal?"),
]

CODE = [
    dict(id="c01", split="demo", function_name="is_palindrome",
         spec="Return True if the string s reads the same forwards and backwards, ignoring case and non-alphanumeric characters.",
         tests="assert is_palindrome('A man, a plan, a canal: Panama')\nassert not is_palindrome('errand')\nassert is_palindrome('')",
         reference="def is_palindrome(s):\n    t = [c.lower() for c in s if c.isalnum()]\n    return t == t[::-1]\n"),
    dict(id="c02", split="demo", function_name="fizzbuzz",
         spec="Return a list of strings for 1..n: 'Fizz' for multiples of 3, 'Buzz' for multiples of 5, 'FizzBuzz' for both, else the number as a string.",
         tests="assert fizzbuzz(5) == ['1','2','Fizz','4','Buzz']\nassert fizzbuzz(15)[-1] == 'FizzBuzz'",
         reference="def fizzbuzz(n):\n    out = []\n    for i in range(1, n + 1):\n        s = ('Fizz' if i % 3 == 0 else '') + ('Buzz' if i % 5 == 0 else '')\n        out.append(s or str(i))\n    return out\n"),
    dict(id="c03", split="demo", function_name="word_counts",
         spec="Given a string, return a dict mapping each lowercase word to how many times it appears. Words are separated by whitespace; strip the punctuation .,!? from each word.",
         tests="assert word_counts('The cat. the hat!') == {'the': 2, 'cat': 1, 'hat': 1}\nassert word_counts('') == {}",
         reference="def word_counts(s):\n    out = {}\n    for w in s.split():\n        w = w.strip('.,!?').lower()\n        if w:\n            out[w] = out.get(w, 0) + 1\n    return out\n"),
    dict(id="c04", split="demo", function_name="merge_intervals",
         spec="Given a list of [start, end] intervals, merge all overlapping intervals and return them sorted by start.",
         tests="assert merge_intervals([[1,3],[2,6],[8,10]]) == [[1,6],[8,10]]\nassert merge_intervals([[5,7],[1,2]]) == [[1,2],[5,7]]\nassert merge_intervals([]) == []",
         reference="def merge_intervals(xs):\n    out = []\n    for s, e in sorted(xs):\n        if out and s <= out[-1][1]:\n            out[-1][1] = max(out[-1][1], e)\n        else:\n            out.append([s, e])\n    return out\n"),
    dict(id="c05", split="exam", function_name="second_largest",
         spec="Return the second largest distinct value in a list of integers, or None if it does not exist.",
         tests="assert second_largest([3, 1, 4, 4, 2]) == 3\nassert second_largest([7]) is None\nassert second_largest([5, 5]) is None",
         reference="def second_largest(xs):\n    u = sorted(set(xs))\n    return u[-2] if len(u) >= 2 else None\n"),
    dict(id="c06", split="exam", function_name="run_length",
         spec="Run-length encode a string: 'aaabcc' becomes 'a3b1c2'.",
         tests="assert run_length('aaabcc') == 'a3b1c2'\nassert run_length('') == ''\nassert run_length('z') == 'z1'",
         reference="def run_length(s):\n    out, i = [], 0\n    while i < len(s):\n        j = i\n        while j < len(s) and s[j] == s[i]:\n            j += 1\n        out.append(f'{s[i]}{j - i}')\n        i = j\n    return ''.join(out)\n"),
    dict(id="c07", split="exam", function_name="flatten",
         spec="Flatten an arbitrarily nested list of integers into a single list, preserving order.",
         tests="assert flatten([1, [2, [3, 4]], 5]) == [1, 2, 3, 4, 5]\nassert flatten([]) == []",
         reference="def flatten(xs):\n    out = []\n    for x in xs:\n        if isinstance(x, list):\n            out.extend(flatten(x))\n        else:\n            out.append(x)\n    return out\n"),
    dict(id="c08", split="exam", function_name="valid_brackets",
         spec="Return True if every bracket in the string ()[]{} is properly closed and nested. Ignore other characters.",
         tests="assert valid_brackets('a(b[c]{d})')\nassert not valid_brackets('(]')\nassert not valid_brackets('((')",
         reference="def valid_brackets(s):\n    pairs = {')': '(', ']': '[', '}': '{'}\n    st = []\n    for c in s:\n        if c in '([{':\n            st.append(c)\n        elif c in pairs:\n            if not st or st.pop() != pairs[c]:\n                return False\n    return not st\n"),
    dict(id="c09", split="mystery", function_name="chunk",
         spec="Split a list into consecutive chunks of size n. The last chunk may be shorter.",
         tests="assert chunk([1,2,3,4,5], 2) == [[1,2],[3,4],[5]]\nassert chunk([], 3) == []",
         reference="def chunk(xs, n):\n    return [xs[i:i + n] for i in range(0, len(xs), n)]\n"),
    dict(id="c10", split="mystery", function_name="roman_to_int",
         spec="Convert a Roman numeral string (I, V, X, L, C, D, M with subtractive notation) to an integer.",
         tests="assert roman_to_int('MCMXCIV') == 1994\nassert roman_to_int('IX') == 9\nassert roman_to_int('LVIII') == 58",
         reference="def roman_to_int(s):\n    v = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}\n    total = 0\n    for i, c in enumerate(s):\n        if i + 1 < len(s) and v[c] < v[s[i + 1]]:\n            total -= v[c]\n        else:\n            total += v[c]\n    return total\n"),
    dict(id="c11", split="mystery", function_name="dedupe_keep_order",
         spec="Remove duplicates from a list while keeping the first occurrence order.",
         tests="assert dedupe_keep_order([3,1,3,2,1]) == [3,1,2]\nassert dedupe_keep_order([]) == []",
         reference="def dedupe_keep_order(xs):\n    seen, out = set(), []\n    for x in xs:\n        if x not in seen:\n            seen.add(x)\n            out.append(x)\n    return out\n"),
    dict(id="c12", split="mystery", function_name="transpose",
         spec="Transpose a rectangular matrix given as a list of rows.",
         tests="assert transpose([[1,2,3],[4,5,6]]) == [[1,4],[2,5],[3,6]]\nassert transpose([]) == []",
         reference="def transpose(m):\n    return [list(r) for r in zip(*m)]\n"),
]


def math_payload(item: dict, with_answer: bool = False) -> dict:
    p = {"problem": item["problem"]}
    if with_answer:
        p["expected"] = item["answer"]
    return p


def code_payload(item: dict) -> dict:
    return {"spec": item["spec"], "function_name": item["function_name"], "tests": item["tests"]}


def items(lane: str, split: str) -> list[dict]:
    bank = MATH if lane == "math.final-answer" else CODE
    return [i for i in bank if i["split"] == split]


def payload_for(lane: str, item: dict, with_answer: bool = True) -> dict:
    return math_payload(item, with_answer) if lane == "math.final-answer" else code_payload(item)


def sample(lane: str, split: str, k: int, rng: random.Random | None = None) -> list[dict]:
    pool = items(lane, split)
    rng = rng or random
    return rng.sample(pool, min(k, len(pool)))


def lookup(lane: str, payload: dict) -> dict | None:
    """Find a bank item matching a payload (used by simulated runners)."""
    if lane == "math.final-answer":
        text = (payload.get("problem") or "").strip()
        return next((i for i in MATH if i["problem"] == text), None)
    name = payload.get("function_name")
    return next((i for i in CODE if i["function_name"] == name), None)
