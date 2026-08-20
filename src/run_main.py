from __future__ import annotations

import runpy

import gemini
from gemini_runtime import generate_post as resilient_generate_post


# main.py imports generate_post from the gemini module. Patch that symbol before
# loading main so the existing production pipeline gains retries and fallback
# without changing its business logic.
gemini.generate_post = resilient_generate_post

runpy.run_path("src/main.py", run_name="__main__")
